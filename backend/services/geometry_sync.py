"""Sincroniza geometrias PostGIS a partir de lat/lon (ponto + polígono 10 m)."""
from __future__ import annotations

import json
import math
from typing import Any

from shapely.geometry import Point, mapping, shape

from ..config import settings
from ..models import Report

_USE_POSTGIS = not settings.database_url.startswith("sqlite")
IMPACT_BUFFER_M = 10.0


def buffer_point_meters(lon: float, lat: float, meters: float = IMPACT_BUFFER_M):
    """Buffer métrico em WGS84 (pyproj se disponível; senão aproximação em graus)."""
    pt = Point(lon, lat)
    try:
        from pyproj import Transformer  # pylint: disable=import-error
        from shapely.ops import transform

        aeqd = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +units=m"
        to_local = Transformer.from_crs("EPSG:4326", aeqd, always_xy=True).transform
        to_wgs = Transformer.from_crs(aeqd, "EPSG:4326", always_xy=True).transform
        local_pt = transform(to_local, pt)
        buffered = local_pt.buffer(meters, quad_segs=24)
        return transform(to_wgs, buffered)
    except Exception:  # noqa: BLE001 — fallback dev/test sem pyproj
        deg = meters / 111_320.0
        if abs(lat) > 85:
            deg = min(deg, 0.01)
        return pt.buffer(deg, quad_segs=16)


def _polygon_from_report(rep: Report):
    """Polígono de impacto: GeoJSON explícito (polígono) ou buffer de 10 m no ponto."""
    if rep.geometry_geojson:
        try:
            geom = shape(json.loads(rep.geometry_geojson))
            if geom.geom_type in ("Polygon", "MultiPolygon"):
                return geom
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    if rep.lat is None or rep.lon is None:
        return None
    if math.isnan(rep.lat) or math.isnan(rep.lon):
        return None
    return buffer_point_meters(rep.lon, rep.lat, IMPACT_BUFFER_M)


def point_geometry_geojson(rep: Report) -> dict[str, Any] | None:
    if rep.lat is None or rep.lon is None:
        return None
    if math.isnan(rep.lat) or math.isnan(rep.lon):
        return None
    return {"type": "Point", "coordinates": [rep.lon, rep.lat]}


def polygon_geometry_geojson(rep: Report) -> dict[str, Any] | None:
    if _USE_POSTGIS and rep.geom_polygon is not None:
        from geoalchemy2.shape import to_shape  # pylint: disable=import-error

        return mapping(to_shape(rep.geom_polygon))
    poly = _polygon_from_report(rep)
    return mapping(poly) if poly is not None else None


def sync_report_point(rep: Report) -> None:
    """Grava apenas geom_point (antes da resposta ao usuário)."""
    if not _USE_POSTGIS:
        return

    from geoalchemy2.shape import from_shape  # pylint: disable=import-error

    if rep.lat is not None and rep.lon is not None and not (
        math.isnan(rep.lat) or math.isnan(rep.lon)
    ):
        rep.geom_point = from_shape(Point(rep.lon, rep.lat), srid=4326)
    else:
        rep.geom_point = None


def sync_report_polygon(rep: Report) -> None:
    """Grava geom_polygon com buffer de 10 m (após resposta ao usuário)."""
    if not _USE_POSTGIS:
        return

    from geoalchemy2.shape import from_shape  # pylint: disable=import-error

    poly = _polygon_from_report(rep)
    rep.geom_polygon = from_shape(poly, srid=4326) if poly is not None else None


def sync_report_geometry(rep: Report) -> None:
    """Compat: ponto + polígono (scripts de seed e testes)."""
    sync_report_point(rep)
    sync_report_polygon(rep)
