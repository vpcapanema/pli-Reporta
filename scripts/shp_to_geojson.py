"""
Converte MALHA_RODOVIARIA.shp (SIRGAS 2000 Polycônica) para GeoJSON WGS84.

Uso:
    python scripts/shp_to_geojson.py

Saída: data/malha_rodoviaria.geojson
"""
# pylint: disable=import-error  # shapefile e pyproj ficam no venv do projeto
from __future__ import annotations

import json
import sys
from pathlib import Path

# ── Caminhos ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
SHP_PATH = ROOT / "data" / "shp_tmp" / "MALHA_RODOVIARIA.shp"
SHP_FALLBACK = ROOT / "data" / "Sistema Rodoviário Estadual" / "MALHA_RODOVIARIA.shp"
OUT_PATH = ROOT / "data" / "malha_rodoviaria.geojson"


def check_deps() -> None:
    missing = []
    for lib in ("shapefile", "pyproj"):
        try:
            __import__(lib)
        except ImportError:
            missing.append(lib)
    if missing:
        sys.exit(f"Dependências faltando: {', '.join(missing)}\n"
                 f"Instale com:  python -m pip install pyshp pyproj")


def map_highway(rodovia: str, tipo_pista: str, perimetro_u: str) -> str:
    """
    Mapeia atributos DER → tipo OSM highway para uso em HIGHWAY_FACTOR.

    TipoPista (DER)  | Rodovia       | PerimetroU | → highway
    ─────────────────┼───────────────┼────────────┼──────────
    DUP              | BR-xxx        | qualquer   | motorway
    DUP              | SP-xxx        | qualquer   | trunk
    PAV/CIM/ASF/BLO  | BR-xxx        | qualquer   | trunk
    PAV/CIM/ASF/BLO  | SP-xxx        | Não        | primary
    PAV/CIM/ASF/BLO  | SP-xxx        | Sim        | secondary
    TER/TERRA/PED    | qualquer      | qualquer   | track
    default          | qualquer      | qualquer   | primary
    """
    rod = str(rodovia or "").strip().upper()
    tipo = str(tipo_pista or "").strip().upper()
    urb = str(perimetro_u or "").strip().lower() in ("sim", "s", "yes", "y")
    fed = rod.startswith("BR") or rod.startswith("BR-")

    if tipo == "DUP":
        return "motorway" if fed else "trunk"
    if tipo in ("PAV", "CIM", "ASF", "BLO", "CCPB", "TSD"):
        if fed:
            return "trunk"
        return "secondary" if urb else "primary"
    if tipo in ("TER", "TERRA", "PED", "PEDREIRA", "REC"):
        return "track"
    return "primary"


def convert() -> None:
    import shapefile                    # pyshp
    from pyproj import CRS, Transformer

    if not SHP_PATH.exists() and SHP_FALLBACK.exists():
        shp_base = SHP_FALLBACK
    elif SHP_PATH.exists():
        shp_base = SHP_PATH
    else:
        sys.exit(f"Shapefile não encontrado: {SHP_PATH}\n"
                 "Extraia o ZIP em data/shp_tmp/ ou use data/Sistema Rodoviário Estadual/.")

    prj_path = shp_base.with_suffix(".prj")
    if not prj_path.exists():
        sys.exit(f"Arquivo .prj não encontrado ao lado de {shp_base}")

    src_crs = CRS.from_wkt(prj_path.read_text(encoding="utf-8"))
    dst_crs = CRS.from_epsg(4326)       # WGS84
    tr = Transformer.from_crs(src_crs, dst_crs, always_xy=True)

    reader = shapefile.Reader(str(shp_base))
    field_names = [f[0] for f in reader.fields[1:]]

    features: list[dict] = []
    skipped = 0

    for sr in reader.iterShapeRecords():
        rec = dict(zip(field_names, sr.record))
        shp = sr.shape

        highway = map_highway(
            rec.get("Rodovia", ""),
            rec.get("TipoPista", ""),
            rec.get("PerimetroU", ""),
        )

        # Segmenta em partes (PolylineZ pode ser multi-parte)
        pts = shp.points
        parts = list(shp.parts) + [len(pts)]
        lines: list[list[list[float]]] = []

        for i in range(len(parts) - 1):
            segment = pts[parts[i]: parts[i + 1]]
            coords: list[list[float]] = []
            for pt in segment:
                lon, lat = tr.transform(pt[0], pt[1])
                coords.append([round(lon, 7), round(lat, 7)])
            if len(coords) >= 2:
                lines.append(coords)

        if not lines:
            skipped += 1
            continue

        if len(lines) == 1:
            geom: dict = {"type": "LineString", "coordinates": lines[0]}
        else:
            geom = {"type": "MultiLineString", "coordinates": lines}

        all_coords = [c for ln in lines for c in ln]
        lons = [c[0] for c in all_coords]
        lats = [c[1] for c in all_coords]
        bbox = [min(lons), min(lats), max(lons), max(lats)]

        features.append({
            "type": "Feature",
            "bbox": bbox,
            "geometry": geom,
            "properties": {
                "highway":           highway,
                "rodovia":           str(rec.get("Rodovia", "") or ""),
                "denominacao":       str(rec.get("Denominaca", "") or ""),
                "tipo_rodoviario":   str(rec.get("TipoRodovi", "") or ""),
                "municipio":         str(rec.get("Municipio", "") or ""),
                "cod_regional":      str(rec.get("CodRegiona", "") or ""),
                "sede_regional":     str(rec.get("SedeRegion", "") or ""),
                "residencia":        str(rec.get("Residencia", "") or ""),
                "sede_residencia":   str(rec.get("SedeReside", "") or ""),
                "tipo_pista":        str(rec.get("TipoPista", "") or ""),
                "perimetro_urbano":  str(rec.get("PerimetroU", "") or ""),
                "administra":        str(rec.get("Administra", "") or ""),
                "jurisdicao":        str(rec.get("Jurisdicao", "") or ""),
            },
        })

    geojson = {"type": "FeatureCollection", "features": features}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(geojson, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"OK: {len(features)} features gravadas em {OUT_PATH}")
    if skipped:
        print(f"  ({skipped} geometrias sem pontos ignoradas)")

    # Resumo dos tipos de highway gerados
    from collections import Counter
    hw_counts = Counter(f["properties"]["highway"] for f in features)
    print("\nDistribuição highway:")
    for hw, n in sorted(hw_counts.items(), key=lambda x: -x[1]):
        print(f"  {hw:12s}  {n:5d}")


if __name__ == "__main__":
    check_deps()
    convert()
