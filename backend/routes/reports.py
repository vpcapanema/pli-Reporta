"""Endpoints públicos de reporte e feed para o roteador."""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_session
from ..models import Report
from .. import schemas
from ..schemas import CaptureNonceResponse, ReportCreated
from ..services import nonce as nonce_svc
from ..services import scope as scope_svc
from ..services.layer_feed import feature_collection
from ..services.layer_publish import finalize_report_layers
from ..services.pipeline import ingest_report, report_to_feature
from ..services.report_catalog import catalog_payload
from ..services.text_format import format_portuguese_text

router = APIRouter()

USER_MESSAGES = {
    "publicado": "Recebemos seu reporte. Ele será exibido no mapa público.",
    "em_moderacao": "Recebemos seu reporte. Está em análise pela equipe.",
    "descartado": "Recebemos seu reporte, mas não pôde ser publicado.",
    "validado": "Recebemos seu reporte. Está em análise pela equipe.",
    "registro_municipal": (
        "Recebemos seu reporte. Registramos para encaminhamento à prefeitura "
        "responsável — não será exibido no mapa de rodovias do PLI."
    ),
}


def _user_message(status: str) -> str:
    return USER_MESSAGES.get(status, "Recebemos seu reporte.")


@router.get("/catalog")
def public_catalog() -> dict:
    """Catálogo público de categorias e status (mapa público e exportações)."""
    return catalog_payload()


@router.get("/capture-nonce", response_model=CaptureNonceResponse)
def get_capture_nonce(client_id: str | None = None) -> CaptureNonceResponse:
    return CaptureNonceResponse(
        nonce=nonce_svc.issue_nonce(client_id),
        expires_in=settings.capture_nonce_ttl_seconds,
    )


@router.post("/format-text", response_model=schemas.FormatTextResponse)
def format_text(body: schemas.FormatTextRequest) -> schemas.FormatTextResponse:
    """Revisa ortografia e gramática em português brasileiro (norma culta)."""
    formatted = format_portuguese_text(body.text)
    return schemas.FormatTextResponse(formatted=formatted)


@router.post("/reports", status_code=201, response_model=ReportCreated)
async def create_report(
    background_tasks: BackgroundTasks,
    photo: Annotated[UploadFile, File(description="Foto (jpeg/png/webp)")],
    lat: Annotated[float, Form()],
    lon: Annotated[float, Form()],
    category: Annotated[str, Form()],
    captured_at: Annotated[str, Form(description="ISO 8601 do momento de captura no cliente")],
    accuracy_m: Annotated[float | None, Form()] = None,
    magnitude: Annotated[str, Form()] = "normal",
    description: Annotated[str | None, Form()] = None,
    capture_nonce: Annotated[str | None, Form()] = None,
    client_id: Annotated[str | None, Form()] = None,
    geometry: Annotated[str | None, Form()] = None,
    interaction_type: Annotated[str, Form()] = "evento_trafego",
    offline_capture: Annotated[bool, Form()] = False,
    db: Session = Depends(get_session),
) -> ReportCreated:
    if photo.content_type and not photo.content_type.startswith("image/"):
        raise HTTPException(415, detail="Arquivo deve ser imagem.")
    payload = await photo.read()
    if not payload:
        raise HTTPException(400, detail="Foto vazia.")
    if len(payload) > 12 * 1024 * 1024:
        raise HTTPException(413, detail="Imagem maior que 12 MB.")

    if geometry:
        try:
            json.loads(geometry)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, detail="geometry deve ser GeoJSON válido.") from exc

    itype = (interaction_type or "evento_trafego").strip().lower()
    if itype == "manifestacao":
        desc = (description or "").strip()
        if len(desc) < 15:
            raise HTTPException(400, detail="Descrição obrigatória (mín. 15 caracteres).")

    try:
        result = ingest_report(
            db,
            image_bytes=payload,
            lat=lat,
            lon=lon,
            accuracy_m=accuracy_m,
            category=category,
            magnitude=magnitude,
            description=description,
            captured_at_iso=captured_at,
            capture_nonce=capture_nonce,
            client_id=client_id,
            geometry_geojson=geometry,
            interaction_type=interaction_type,
            offline_capture=offline_capture,
        )
    except scope_svc.ScopeRejectedError as exc:
        raise HTTPException(422, detail=exc.detail) from exc
    db.commit()

    rep = result.report
    background_tasks.add_task(finalize_report_layers, rep.id)
    return ReportCreated(
        id=rep.id,
        status=rep.status,
        interaction_type=rep.interaction_type,
        message=_user_message(rep.status),
        veracity_score=round(rep.veracity_score, 3),
        relevance_score=round(rep.relevance_score, 3),
        priority=round(rep.priority, 3),
        explanation=result.explanation,
        cluster_id=rep.cluster_id,
        valid_to=rep.valid_to,
        road_scope=rep.road_scope,
        road_label=rep.road_label,
    )


@router.post("/incidents/{cluster_id}/resolver")
def resolve_incident(cluster_id: str) -> dict:
    """Contra-reporte público: 'este evento já foi resolvido / não está mais aqui'."""
    from ..services.maintenance import register_resolve_vote

    result = register_resolve_vote(cluster_id)
    if not result.get("found"):
        raise HTTPException(404, detail="Evento não encontrado.")
    if result.get("resolved"):
        message = "Obrigado! Marcamos este evento como resolvido."
    else:
        message = "Obrigado pelo aviso. Mais uma confirmação e ele será removido."
    return {**result, "message": message}


@router.get("/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_session)) -> dict:
    rep = db.get(Report, report_id)
    if not rep:
        raise HTTPException(404, detail="Reporte não encontrado.")
    return report_to_feature(rep)["properties"]


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        parts = [float(x) for x in bbox.split(",")]
        if len(parts) == 4:
            return (parts[0], parts[1], parts[2], parts[3])
    except ValueError as exc:
        raise HTTPException(400, detail="bbox inválido.") from exc
    return None


def _public_feed_response(
    db: Session,
    *,
    interaction_type: str,
    bbox: str | None,
    since: str | None,
    category: str | None,
    min_priority: float,
) -> JSONResponse:
    fc = feature_collection(
        db,
        mapa="publico",
        interaction_type=interaction_type,
        category=category,
        since=since,
        min_priority=min_priority,
        bbox=_parse_bbox(bbox),
    )
    return JSONResponse(fc, headers={"Cache-Control": "public, max-age=30"})


@router.get("/layers/points/{interaction_type}.geojson")
def public_points_layer(
    interaction_type: str,
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    since: str | None = Query(None, description="ISO 8601"),
    category: str | None = None,
    min_priority: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Feed público de pontos por tipo de interação (matriz de visibilidade)."""
    itype = interaction_type.strip().lower()
    if itype not in ("evento_trafego", "manifestacao"):
        raise HTTPException(400, detail="interaction_type inválido.")
    return _public_feed_response(
        db,
        interaction_type=itype,
        bbox=bbox,
        since=since,
        category=category,
        min_priority=min_priority,
    )


@router.get("/incidents.geojson")
def incidents_feed(
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    since: str | None = Query(None, description="ISO 8601"),
    category: str | None = None,
    min_priority: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Alias legado — eventos de tráfego visíveis no mapa público."""
    return _public_feed_response(
        db,
        interaction_type="evento_trafego",
        bbox=bbox,
        since=since,
        category=category,
        min_priority=min_priority,
    )


@router.get("/manifestations.geojson")
def manifestations_feed(
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    since: str | None = Query(None, description="ISO 8601"),
    category: str | None = None,
    min_priority: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Alias legado — manifestações visíveis no mapa público."""
    return _public_feed_response(
        db,
        interaction_type="manifestacao",
        bbox=bbox,
        since=since,
        category=category,
        min_priority=min_priority,
    )


@router.get("/reports")
def list_reports_public(
    limit: int = Query(50, ge=1, le=200),
    status: str | None = None,
    interaction_type: str | None = None,
    db: Session = Depends(get_session),
) -> dict:
    stmt = select(Report).order_by(Report.received_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(Report.status == status)
    if interaction_type:
        stmt = stmt.where(Report.interaction_type == interaction_type)
    rows = db.execute(stmt).scalars().all()
    return {"items": [report_to_feature(r)["properties"] for r in rows]}
