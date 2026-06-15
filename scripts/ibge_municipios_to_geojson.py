"""
Converte limites municipais para GeoJSON WGS84 (recorte SP).

Fontes (em ordem de preferência):
1. Shapefile local DER: data/dradt_mvw_lml_municipio_a_2021/
2. Download IBGE Malha Municipal 2024 (--download --uf SP)

Saída: data/ibge_municipios_sp.geojson

Uso:
    python scripts/ibge_municipios_to_geojson.py
    python scripts/ibge_municipios_to_geojson.py --download --uf SP
"""
# pylint: disable=import-error
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parent.parent
LOCAL_SHP = ROOT / "data" / "dradt_mvw_lml_municipio_a_2021" / "dradt_mvw_lml_municipio_a_2021.shp"
TMP_DIR = ROOT / "data" / "ibge_municipios_tmp"
OUT_PATH = ROOT / "data" / "ibge_municipios_sp.geojson"
IBGE_UF_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_municipais/municipio_2024/UFs/{uf}/{uf}_Municipios_2024.zip"
)


def check_deps() -> None:
    missing = []
    for lib in ("shapefile", "pyproj"):
        try:
            __import__(lib)
        except ImportError:
            missing.append(lib)
    if missing:
        sys.exit(
            f"Dependencias faltando: {', '.join(missing)}\n"
            "Instale com: python -m pip install pyshp pyproj"
        )


def download_zip(uf: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    url = IBGE_UF_URL.format(uf=uf.upper())
    zip_path = dest / f"{uf.upper()}_Municipios_2024.zip"
    print(f"Baixando {url} ...")
    urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    print(f"Extraido em {dest}")
    return dest


def find_shp(base: Path) -> Path:
    matches = sorted(base.rglob("*.shp"))
    if not matches:
        sys.exit(f"Nenhum .shp encontrado em {base}")
    return matches[0]


def _ring_to_wgs84(ring: list, tr) -> list[list[float]]:
    out: list[list[float]] = []
    for pt in ring:
        lon, lat = tr.transform(pt[0], pt[1])
        out.append([round(lon, 7), round(lat, 7)])
    return out


def _shape_to_geom(shp, tr) -> dict | None:
    pts = shp.points
    parts = list(shp.parts) + [len(pts)]
    polys: list = []

    for i in range(len(parts) - 1):
        ring_pts = pts[parts[i]: parts[i + 1]]
        if len(ring_pts) < 3:
            continue
        ring = _ring_to_wgs84(ring_pts, tr)
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        polys.append([ring])

    if not polys:
        return None
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def _municipio_name(rec: dict) -> str:
    for key in ("NM_MUN", "nm_mun", "nome", "name", "municipio", "NM_MUNICIP"):
        val = rec.get(key)
        if val:
            return str(val).strip()
    return ""


def convert_shp(shp_path: Path, out_path: Path) -> None:
    import shapefile
    from pyproj import CRS, Transformer

    prj_path = shp_path.with_suffix(".prj")
    if prj_path.exists():
        src_crs = CRS.from_wkt(prj_path.read_text(encoding="utf-8"))
    else:
        src_crs = CRS.from_epsg(4674)
    tr = Transformer.from_crs(src_crs, CRS.from_epsg(4326), always_xy=True)

    reader = shapefile.Reader(str(shp_path), encoding="latin-1")
    field_names = [f[0] for f in reader.fields[1:]]

    features: list[dict] = []
    skipped = 0

    for sr in reader.iterShapeRecords():
        rec = dict(zip(field_names, sr.record))
        geom = _shape_to_geom(sr.shape, tr)
        if not geom:
            skipped += 1
            continue

        nome = _municipio_name(rec)
        geocodigo = str(rec.get("CD_MUN") or rec.get("geocodigo") or rec.get("GEOCODIGO") or "").strip()

        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "nm_mun": nome,
                "municipio": nome,
                "geocodigo": geocodigo or None,
            },
        })

    geojson = {"type": "FeatureCollection", "features": features}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(geojson, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"OK: {len(features)} municipios gravados em {out_path}")
    if skipped:
        print(f"  ({skipped} geometrias ignoradas)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Limites municipais -> GeoJSON (SP)")
    parser.add_argument("--download", action="store_true", help="Baixa malha IBGE 2024 da UF")
    parser.add_argument("--uf", default="SP", help="UF alvo (default: SP)")
    parser.add_argument(
        "--output",
        default=str(OUT_PATH),
        help=f"Caminho de saida (default: {OUT_PATH})",
    )
    args = parser.parse_args()
    out_path = Path(args.output)

    check_deps()

    if args.download:
        base = download_zip(args.uf, TMP_DIR)
        shp_path = find_shp(base)
    elif LOCAL_SHP.exists():
        print(f"Usando shapefile local: {LOCAL_SHP}")
        shp_path = LOCAL_SHP
    elif any(TMP_DIR.rglob("*.shp")):
        shp_path = find_shp(TMP_DIR)
    else:
        sys.exit(
            "Nenhuma fonte encontrada.\n"
            "  Rode com --download --uf SP\n"
            f"  ou coloque shapefile em {LOCAL_SHP.parent}/"
        )

    convert_shp(shp_path, out_path)


if __name__ == "__main__":
    main()
