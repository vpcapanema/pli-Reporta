"""API pública de compartilhamento — eventos de tráfego aprovados (GeoJSON)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_session
from ..services.export_reports import validate_layer
from ..services.layer_feed import feature_collection
from ..services.public_api_spec import api_manifest
from ..services.report_catalog import EVENT_CATEGORIES, catalog_payload

router = APIRouter()


def _base_url(request: Request) -> str:
    if settings.public_base_url.strip():
        return settings.public_base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        parts = [float(x) for x in bbox.split(",")]
        if len(parts) == 4:
            return (parts[0], parts[1], parts[2], parts[3])
    except ValueError as exc:
        raise HTTPException(400, detail="bbox inválido (minLon,minLat,maxLon,maxLat).") from exc
    raise HTTPException(400, detail="bbox inválido (minLon,minLat,maxLon,maxLat).")


def _public_events_fc(
    db: Session,
    *,
    category: str | None = None,
    bbox: str | None = None,
    since: str | None = None,
    min_priority: float = 0.0,
) -> dict:
    """FeatureCollection — export_publico + evento_trafego."""
    return feature_collection(
        db,
        mapa="export_publico",
        interaction_type="evento_trafego",
        category=category,
        bbox=_parse_bbox(bbox),
        since=since,
        min_priority=min_priority,
    )


def _geojson_response(fc: dict) -> JSONResponse:
    return JSONResponse(
        fc,
        headers={
            "Cache-Control": "public, max-age=60",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/")
def public_api_root(request: Request) -> dict:
    """Manifesto da API pública (endpoints, camadas, regras)."""
    return api_manifest(base_url=_base_url(request))


@router.get("/catalog")
def public_api_catalog() -> dict:
    """Catálogo reduzido — somente categorias de eventos de tráfego."""
    full = catalog_payload()
    return {
        "interaction_types": [
            t for t in full["interaction_types"] if t["id"] == "evento_trafego"
        ],
        "event_categories": EVENT_CATEGORIES,
        "statuses": {
            k: v for k, v in full["statuses"].items() if v.get("export_publico")
        },
        "status_visibility_matrix": full["status_visibility_matrix"],
    }


@router.get("/eventos-trafego.geojson")
def public_all_traffic_events(
    request: Request,
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    since: str | None = Query(None, description="ISO 8601 — captured_at mínimo"),
    min_priority: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Todos os eventos de tráfego aprovados, todas as categorias."""
    fc = _public_events_fc(
        db,
        bbox=bbox,
        since=since,
        min_priority=min_priority,
    )
    fc["metadata"] = {
        "api": "PLI Reporta public v1",
        "interaction_type": "evento_trafego",
        "manifest": f"{_base_url(request)}/api/public/",
    }
    return _geojson_response(fc)


@router.get("/eventos-trafego/{category_id}.geojson")
def public_traffic_layer(
    category_id: str,
    request: Request,
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    since: str | None = Query(None, description="ISO 8601"),
    min_priority: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Uma camada (categoria) de eventos de tráfego aprovados."""
    cat = category_id.strip().lower()
    try:
        meta = validate_layer("evento_trafego", cat)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    fc = _public_events_fc(
        db,
        category=cat,
        bbox=bbox,
        since=since,
        min_priority=min_priority,
    )
    fc["metadata"] = {
        "api": "PLI Reporta public v1",
        "interaction_type": "evento_trafego",
        "category_id": cat,
        "category_label": meta["label"],
        "manifest": f"{_base_url(request)}/api/public/",
    }
    return _geojson_response(fc)
