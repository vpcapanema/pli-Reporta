"""Endpoints de moderação humana (faixa cinza) protegidos por API Key."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_session
from ..models import AuditLog, Report
from ..schemas import ModerationDecision

router = APIRouter()


def require_moderator(x_api_key: str | None = Header(default=None)) -> str:
    if not settings.moderator_api_key:
        raise HTTPException(503, detail="Moderação não configurada (MODERATOR_API_KEY ausente).")
    if x_api_key != settings.moderator_api_key:
        raise HTTPException(401, detail="API key inválida.")
    return x_api_key


@router.get("/moderation/queue")
def queue(
    db: Session = Depends(get_session),
    _key: str = Depends(require_moderator),
) -> dict:
    rows = db.execute(
        select(Report)
        .where(Report.status == "em_moderacao")
        .order_by(Report.priority.desc(), Report.received_at.asc())
        .limit(100)
    ).scalars().all()
    items = []
    for r in rows:
        signals = json.loads(r.veracity_signals_json or "{}")
        items.append({
            "id": r.id,
            "category": r.category,
            "magnitude": r.magnitude,
            "lat": r.lat,
            "lon": r.lon,
            "veracity": round(r.veracity_score, 3),
            "relevance": round(r.relevance_score, 3),
            "priority": round(r.priority, 3),
            "received_at": r.received_at,
            "captured_at": r.captured_at,
            "description": r.description,
            "photo_path": r.photo_path,
            "signals": signals,
        })
    return {"queue_size": len(items), "items": items}


@router.post("/moderation/{report_id}/decide")
def decide(
    report_id: str,
    decision: ModerationDecision,
    db: Session = Depends(get_session),
    _key: str = Depends(require_moderator),
) -> dict:
    rep = db.get(Report, report_id)
    if not rep:
        raise HTTPException(404, detail="Reporte não encontrado.")
    if rep.status != "em_moderacao":
        raise HTTPException(409, detail=f"Status atual não permite decidir: {rep.status}")

    rep.status = "validado" if decision.decision == "publicar" else "descartado"
    db.add(AuditLog(
        ts=datetime.now(timezone.utc).isoformat(),
        actor="moderator",
        action=f"decide:{decision.decision}",
        target_type="report",
        target_id=report_id,
        payload_json=json.dumps({"note": decision.note}, ensure_ascii=False),
    ))
    db.commit()
    return {"id": rep.id, "status": rep.status}
