"""Materializa features em data/camadas-do-sistema/ (pontos e polígonos)."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..models import Report
from .geometry_sync import point_geometry_geojson, polygon_geometry_geojson
from .layer_schema import build_full_layer_properties

ROOT = Path(__file__).resolve().parent.parent.parent
BASE = ROOT / "data" / "camadas-do-sistema"

_locks: dict[str, threading.Lock] = {}
_lock_guard = threading.Lock()


def layer_filename(interaction_type: str, category_id: str) -> str:
    return f"{interaction_type}__{category_id}.geojson"


def _file_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _lock_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def _empty_collection(interaction_type: str, category_id: str, *, role: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": layer_filename(interaction_type, category_id).replace(".geojson", ""),
        "metadata": {
            "interaction_type": interaction_type,
            "category_id": category_id,
            "geometry_role": role,
        },
        "features": [],
    }


def _read_collection(path: Path, *, interaction_type: str, category_id: str, role: str) -> dict:
    if not path.exists():
        return _empty_collection(interaction_type, category_id, role=role)
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".geojson.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _feature_id(feature: dict[str, Any]) -> str | None:
    props = feature.get("properties") or {}
    return feature.get("id") or props.get("ID") or props.get("id")


def _upsert_feature(path: Path, feature: dict[str, Any], *, interaction_type: str, category_id: str, role: str) -> None:
    rid = _feature_id(feature)
    if not rid:
        return
    with _file_lock(path):
        coll = _read_collection(path, interaction_type=interaction_type, category_id=category_id, role=role)
        features = [
            f for f in coll.get("features", [])
            if _feature_id(f) != rid
        ]
        features.append(feature)
        coll["features"] = features
        _atomic_write(path, coll)


def point_feature(rep: Report) -> dict[str, Any] | None:
    geom = point_geometry_geojson(rep)
    if not geom:
        return None
    return {
        "type": "Feature",
        "id": rep.id,
        "geometry": geom,
        "properties": build_full_layer_properties(rep),
    }


def polygon_feature(rep: Report) -> dict[str, Any] | None:
    geom = polygon_geometry_geojson(rep)
    if not geom:
        return None
    return {
        "type": "Feature",
        "id": rep.id,
        "geometry": geom,
        "properties": build_full_layer_properties(rep),
    }


def publish_report(rep: Report) -> None:
    """Upsert do reporte nos arquivos GeoJSON de ponto e polígono."""
    itype = rep.interaction_type
    cat = rep.category

    pf = point_feature(rep)
    if pf:
        path = BASE / "pontos" / layer_filename(itype, cat)
        _upsert_feature(path, pf, interaction_type=itype, category_id=cat, role="ponto")

    polyf = polygon_feature(rep)
    if polyf:
        path = BASE / "poligonos" / layer_filename(itype, cat)
        _upsert_feature(path, polyf, interaction_type=itype, category_id=cat, role="poligono")
