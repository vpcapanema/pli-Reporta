"""Healthcheck e métricas mínimas."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import Report

router = APIRouter()


@router.get("/healthz")
def healthz(db: Session = Depends(get_session)) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    queue_size = db.execute(
        select(func.count()).select_from(Report).where(Report.status == "em_moderacao")
    ).scalar_one()
    active = db.execute(
        select(func.count()).select_from(Report).where(
            Report.status.in_(("validado", "publicado")),
            (Report.valid_to.is_(None)) | (Report.valid_to > now_iso),
        )
    ).scalar_one()
    return {
        "status": "ok",
        "db": "ok",
        "queue_size": int(queue_size),
        "active_incidents": int(active),
        "now": now_iso,
    }
