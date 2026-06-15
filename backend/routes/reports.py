"""Endpoints públicos de reporte e feed para o roteador."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_session
from ..models import Report
from ..schemas import CaptureNonceResponse, ReportCreated
from ..services import nonce as nonce_svc
from ..services.pipeline import (
    active_public_reports_stmt,
    ingest_report,
    report_to_feature,
)

router = APIRouter()

USER_MESSAGES = {
    "publicado": "Recebemos seu reporte. Ele será exibido no mapa público.",
    "em_moderacao": "Recebemos seu reporte. Está em análise pela equipe.",
    "descartado": "Recebemos seu reporte, mas não pôde ser publicado.",
    "validado": "Recebemos seu reporte. Está em análise pela equipe.",
}


def _user_message(status: str) -> str:
    return USER_MESSAGES.get(status, "Recebemos seu reporte.")


@router.get("/capture-nonce", response_model=CaptureNonceResponse)
def get_capture_nonce(client_id: str | None = None) -> CaptureNonceResponse:
    return CaptureNonceResponse(
        nonce=nonce_svc.issue_nonce(client_id),
        expires_in=settings.capture_nonce_ttl_seconds,
    )


@router.post("/reports", status_code=201, response_model=ReportCreated)
async def create_report(
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
    db.commit()

    rep = result.report
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
    )


@router.post("/incidents/{cluster_id}/resolver")
def resolve_incident(cluster_id: str) -> dict:
    """Contra-reporte público: 'este evento já foi resolvido / não está mais aqui'.

    Acumula votos; ao atingir o limiar, o evento é marcado como resolvido
    automaticamente, sem precisar de um gestor conferir.
    """
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


def _geojson_feed(
    db: Session,
    *,
    interaction_type: str | None,
    bbox: str | None,
    since: str | None,
    category: str | None,
    min_priority: float,
) -> JSONResponse:
    now_iso = datetime.now(timezone.utc).isoformat()
    stmt = active_public_reports_stmt(interaction_type=interaction_type)
    if category:
        stmt = stmt.where(Report.category == category)
    if since:
        stmt = stmt.where(Report.captured_at >= since)
    rows = db.execute(stmt).scalars().all()

    bbox_t: tuple[float, float, float, float] | None = None
    if bbox:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) == 4:
                bbox_t = (parts[0], parts[1], parts[2], parts[3])
        except ValueError as exc:
            raise HTTPException(400, detail="bbox inválido.") from exc

    features = []
    for r in rows:
        if r.priority < min_priority:
            continue
        if bbox_t and not (
            bbox_t[0] <= r.lon <= bbox_t[2] and bbox_t[1] <= r.lat <= bbox_t[3]
        ):
            continue
        features.append(report_to_feature(r))

    fc = {"type": "FeatureCollection", "features": features, "generated_at": now_iso}
    headers = {"Cache-Control": "public, max-age=30"}
    return JSONResponse(fc, headers=headers)


@router.get("/incidents.geojson")
def incidents_feed(
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    since: str | None = Query(None, description="ISO 8601"),
    category: str | None = None,
    min_priority: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Feed para o roteador — apenas eventos de tráfego publicados."""
    return _geojson_feed(
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
    """Feed público de manifestações cidadãs (elogio, sugestão, reclamação)."""
    return _geojson_feed(
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
