"""Utilidades geográficas leves — sem dependência de banco espacial."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância grande-círculo em metros."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bbox_filter(features: Iterable[dict], bbox: tuple[float, float, float, float]) -> list[dict]:
    """Filtra features por bounding box [minLon, minLat, maxLon, maxLat]."""
    min_lon, min_lat, max_lon, max_lat = bbox
    out: list[dict] = []
    for f in features:
        coords = f.get("geometry", {}).get("coordinates")
        if not coords:
            continue
        lon, lat = coords[0], coords[1]
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            out.append(f)
    return out


# --------------------------------------------------------------------------- #
# Snap simples a um GeoJSON local de vias.
# Estrutura esperada: FeatureCollection com LineString/MultiLineString.
# Cada feature pode ter properties.osm_id e properties.highway.
# Mantemos um cache em memória.
# --------------------------------------------------------------------------- #

_ROADS_CACHE: dict[str, list[dict]] = {}


def _load_roads(path: str) -> list[dict]:
    if path in _ROADS_CACHE:
        return _ROADS_CACHE[path]
    p = Path(path)
    if not p.exists():
        _ROADS_CACHE[path] = []
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    feats: list[dict] = []
    for f in data.get("features", []):
        geom = f.get("geometry") or {}
        if geom.get("type") not in ("LineString", "MultiLineString"):
            continue
        feats.append(f)
    _ROADS_CACHE[path] = feats
    return feats


def _segments(feature: dict) -> Iterable[tuple[tuple[float, float], tuple[float, float]]]:
    geom = feature["geometry"]
    if geom["type"] == "LineString":
        coords = geom["coordinates"]
        for a, b in zip(coords, coords[1:]):
            yield (a[1], a[0]), (b[1], b[0])  # (lat, lon)
    else:
        for line in geom["coordinates"]:
            for a, b in zip(line, line[1:]):
                yield (a[1], a[0]), (b[1], b[0])


def _point_to_segment_m(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    """Distância aproximada ponto-segmento em metros via projeção planar local."""
    # Projeção equirretangular ancorada em p — aceitável em escalas curtas.
    lat0 = math.radians(p[0])
    sx = math.cos(lat0) * EARTH_RADIUS_M
    sy = EARTH_RADIUS_M

    def to_xy(q: tuple[float, float]) -> tuple[float, float]:
        return (math.radians(q[1] - p[1]) * sx, math.radians(q[0] - p[0]) * sy)

    px, py = 0.0, 0.0
    ax, ay = to_xy(a)
    bx, by = to_xy(b)
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def nearest_road(
    lat: float, lon: float, roads_path: str, max_m: float = 200.0
) -> tuple[float, dict | None]:
    """Devolve (distância em metros, feature mais próxima) ou (inf, None)."""
    feats = _load_roads(roads_path)
    if not feats:
        return float("inf"), None
    best = float("inf")
    best_feat: dict | None = None
    p = (lat, lon)
    for f in feats:
        # Filtro grosseiro por bbox da feature, se disponível.
        bb = f.get("bbox")
        if bb and len(bb) == 4:
            if not (bb[0] - 0.01 <= lon <= bb[2] + 0.01 and bb[1] - 0.01 <= lat <= bb[3] + 0.01):
                continue
        for a, b in _segments(f):
            d = _point_to_segment_m(p, a, b)
            if d < best:
                best = d
                best_feat = f
                if best < max_m * 0.1:  # já bom o bastante
                    break
    return best, best_feat
