"""Serialização de reportes para a API de moderação."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog, Report
from ..services import photos as photo_svc


def report_summary(r: Report) -> dict:
    return {
        "id": r.id,
        "interaction_type": r.interaction_type,
        "category": r.category,
        "magnitude": r.magnitude,
        "description": r.description,
        "lat": r.lat,
        "lon": r.lon,
        "status": r.status,
        "veracity": round(r.veracity_score, 3),
        "relevance": round(r.relevance_score, 3),
        "priority": round(r.priority, 3),
        "received_at": r.received_at,
        "captured_at": r.captured_at,
        "road_scope": r.road_scope,
        "road_label": r.road_label,
        "photo_url": photo_svc.public_url_for(r.photo_path),
    }


def report_detail(r: Report, db: Session) -> dict:
    signals = json.loads(r.veracity_signals_json or "{}")
    logs = db.execute(
        select(AuditLog)
        .where(AuditLog.target_type == "report", AuditLog.target_id == r.id)
        .order_by(AuditLog.id.desc())
        .limit(20)
    ).scalars().all()
    return {
        **report_summary(r),
        "signals": signals,
        "exif": json.loads(r.exif_json) if r.exif_json else None,
        "cluster_id": r.cluster_id,
        "valid_to": r.valid_to,
        "audit": [
            {
                "ts": a.ts,
                "actor": a.actor,
                "action": a.action,
                "payload": a.payload_json,
            }
            for a in logs
        ],
    }
