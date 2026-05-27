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
from ..services.pipeline import ingest_report, report_to_feature

router = APIRouter()


@router.get("/capture-nonce", response_model=CaptureNonceResponse)
def get_capture_nonce(client_id: str | None = None) -> CaptureNonceResponse:
    return CaptureNonceResponse(
        nonce=nonce_svc.issue_nonce(client_id),
        expires_in=settings.capture_nonce_ttl_seconds,
    )


@router.post("/reports", status_code=201, response_model=ReportCreated)
async def create_report(
    photo: Annotated[UploadFile, File(description="Foto do incidente (jpeg/png/webp)")],
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
        except json.JSONDecodeError:
            raise HTTPException(400, detail="geometry deve ser GeoJSON válido.")

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
    )
    db.commit()

    rep = result.report
    return ReportCreated(
        id=rep.id,
        status=rep.status,
        veracity_score=round(rep.veracity_score, 3),
        relevance_score=round(rep.relevance_score, 3),
        priority=round(rep.priority, 3),
        explanation=result.explanation,
        cluster_id=rep.cluster_id,
        valid_to=rep.valid_to,
    )


@router.get("/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_session)) -> dict:
    rep = db.get(Report, report_id)
    if not rep:
        raise HTTPException(404, detail="Reporte não encontrado.")
    return report_to_feature(rep)["properties"]


@router.get("/incidents.geojson")
def incidents_feed(
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    since: str | None = Query(None, description="ISO 8601"),
    category: str | None = None,
    min_priority: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_session),
) -> JSONResponse:
    """Feed primário consumido pelo roteador. Apenas reportes ativos."""
    now_iso = datetime.now(timezone.utc).isoformat()
    stmt = (
        select(Report)
        .where(Report.status.in_(("validado", "publicado")))
        .where((Report.valid_to.is_(None)) | (Report.valid_to > now_iso))
    )
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
        except ValueError:
            raise HTTPException(400, detail="bbox inválido.")

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


@router.get("/reports")
def list_reports_public(
    limit: int = Query(50, ge=1, le=200),
    status: str | None = None,
    db: Session = Depends(get_session),
) -> dict:
    stmt = select(Report).order_by(Report.received_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(Report.status == status)
    rows = db.execute(stmt).scalars().all()
    return {"items": [report_to_feature(r)["properties"] for r in rows]}
