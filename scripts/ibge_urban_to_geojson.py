"""
Converte a mancha urbana IBGE (Áreas Urbanizadas 2019) para GeoJSON WGS84.

Fonte oficial:
  https://geoftp.ibge.gov.br/organizacao_do_territorio/tipologias_do_territorio/
  areas_urbanizadas_do_brasil/2019/Shapefile/AreasUrbanizadas2019_Brasil.zip

Recorta para o estado de São Paulo usando o bounding box da malha DER (se existir).

Uso:
    python scripts/ibge_urban_to_geojson.py
    python scripts/ibge_urban_to_geojson.py --download
    python scripts/ibge_urban_to_geojson.py --uf SP
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
IBGE_ZIP_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/"
    "tipologias_do_territorio/areas_urbanizadas_do_brasil/2019/Shapefile/"
    "AreasUrbanizadas2019_Brasil.zip"
)
TMP_DIR = ROOT / "data" / "ibge_tmp"
OUT_PATH = ROOT / "data" / "ibge_mancha_urbana.geojson"
MALHA_PATH = ROOT / "data" / "malha_rodoviaria.geojson"
SP_BBOX_FALLBACK = (-53.5, -25.5, -44.0, -19.5)  # min_lon, min_lat, max_lon, max_lat


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


def download_zip(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / "AreasUrbanizadas2019_Brasil.zip"
    print(f"Baixando {IBGE_ZIP_URL} ...")
    urlretrieve(IBGE_ZIP_URL, zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    print(f"Extraido em {dest}")
    return dest


def find_shp(base: Path) -> Path:
    matches = sorted(base.rglob("*.shp"))
    if not matches:
        sys.exit(f"Nenhum .shp encontrado em {base}")
    return matches[0]


def _bbox_from_malha() -> tuple[float, float, float, float]:
    if not MALHA_PATH.exists():
        return SP_BBOX_FALLBACK
    data = json.loads(MALHA_PATH.read_text(encoding="utf-8"))
    min_lon = min_lat = float("inf")
    max_lon = max_lat = float("-inf")
    for feat in data.get("features", []):
        bb = feat.get("bbox")
        if bb and len(bb) == 4:
            min_lon = min(min_lon, bb[0])
            min_lat = min(min_lat, bb[1])
            max_lon = max(max_lon, bb[2])
            max_lat = max(max_lat, bb[3])
            continue
        coords = feat.get("geometry", {}).get("coordinates")
        if not coords:
            continue
        flat = coords
        while flat and isinstance(flat[0][0], (list, tuple)):
            flat = flat[0]
        for lon, lat in flat:
            min_lon = min(min_lon, lon)
            min_lat = min(min_lat, lat)
            max_lon = max(max_lon, lon)
            max_lat = max(max_lat, lat)
    if min_lon == float("inf"):
        return SP_BBOX_FALLBACK
    pad = 0.05
    return (min_lon - pad, min_lat - pad, max_lon + pad, max_lat + pad)


def _bbox_intersects(
    feat_bbox: tuple[float, float, float, float],
    clip: tuple[float, float, float, float],
) -> bool:
    a_min_lon, a_min_lat, a_max_lon, a_max_lat = feat_bbox
    b_min_lon, b_min_lat, b_max_lon, b_max_lat = clip
    return not (
        a_max_lon < b_min_lon
        or a_min_lon > b_max_lon
        or a_max_lat < b_min_lat
        or a_min_lat > b_max_lat
    )


def convert(*, uf: str | None) -> None:
    import shapefile
    from pyproj import CRS, Transformer

    shp = find_shp(TMP_DIR)
    prj = shp.with_suffix(".prj")
    if not prj.exists():
        sys.exit(f"Arquivo .prj nao encontrado ao lado de {shp}")

    clip_bbox = _bbox_from_malha()
    uf_norm = (uf or "").strip().upper()
    if uf_norm and uf_norm != "SP":
        print(f"AVISO: recorte automatico otimizado para SP; UF={uf_norm} usa bbox da malha DER.")

    src_crs = CRS.from_wkt(prj.read_text(encoding="utf-8"))
    dst_crs = CRS.from_epsg(4326)
    tr = Transformer.from_crs(src_crs, dst_crs, always_xy=True)

    reader = shapefile.Reader(str(shp))
    field_names = [f[0] for f in reader.fields[1:]]

    features: list[dict] = []
    skipped_clip = 0

    for sr in reader.iterShapeRecords():
        rec = dict(zip(field_names, sr.record))
        shp_obj = sr.shape
        if shp_obj.shapeType not in (3, 5, 15, 18, 31):
            continue

        parts = list(shp_obj.parts) + [len(shp_obj.points)]
        rings: list[list[list[float]]] = []
        for i in range(len(parts) - 1):
            ring_pts = shp_obj.points[parts[i]: parts[i + 1]]
            ring: list[list[float]] = []
            for pt in ring_pts:
                lon, lat = tr.transform(pt[0], pt[1])
                ring.append([round(lon, 7), round(lat, 7)])
            if len(ring) >= 4:
                rings.append(ring)

        if not rings:
            continue

        lons = [c[0] for c in rings[0]]
        lats = [c[1] for c in rings[0]]
        feat_bbox = (min(lons), min(lats), max(lons), max(lats))
        if not _bbox_intersects(feat_bbox, clip_bbox):
            skipped_clip += 1
            continue

        if len(rings) == 1:
            geom = {"type": "Polygon", "coordinates": [rings[0]]}
        else:
            geom = {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}

        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "densidade": str(rec.get("Densidade") or ""),
                "tipo": str(rec.get("Tipo") or ""),
                "comparacao": str(rec.get("Comparacao") or ""),
            },
        })

    geojson = {"type": "FeatureCollection", "features": features}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(geojson, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"OK: {len(features)} poligonos urbanos gravados em {OUT_PATH}")
    if skipped_clip:
        print(f"  ({skipped_clip} poligonos fora do recorte SP ignorados)")


def main() -> None:
    parser = argparse.ArgumentParser(description="IBGE mancha urbana -> GeoJSON (recorte SP)")
    parser.add_argument("--download", action="store_true", help="Baixa o ZIP do IBGE antes")
    parser.add_argument("--uf", default="SP", help="UF alvo (default: SP)")
    args = parser.parse_args()

    check_deps()
    if args.download or not any(TMP_DIR.rglob("*.shp")):
        download_zip(TMP_DIR)
    convert(uf=args.uf)


if __name__ == "__main__":
    main()
