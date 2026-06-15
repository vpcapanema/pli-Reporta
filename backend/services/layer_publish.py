"""Publicação assíncrona de camadas após ingestão ou mudança de status."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..database import session_scope
from ..models import Report
from .geometry_sync import sync_report_polygon
from .layer_store import publish_report


def finalize_report_layers(report_id: str) -> None:
    """Pós-resposta: polígono PostGIS 10 m + GeoJSON pontos e polígonos."""
    with session_scope() as db:
        rep = db.get(Report, report_id)
        if not rep:
            return
        sync_report_polygon(rep)
        publish_report(rep)


def refresh_report_layers(report_id: str) -> None:
    """Reescreve GeoJSON quando status/visibilidade mudam (sem recriar polígono)."""
    with session_scope() as db:
        rep = db.get(Report, report_id)
        if not rep:
            return
        publish_report(rep)


def refresh_reports_layers(db: Session, report_ids: list[str]) -> None:
    """Atualiza camadas para vários reportes na sessão atual."""
    for rid in report_ids:
        rep = db.get(Report, rid)
        if rep:
            publish_report(rep)
