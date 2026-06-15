"""Feeds GeoJSON a partir da matriz de visibilidade (Postgres + lat/lon)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..models import Report
from .layer_schema import visibility_flags
from .report_catalog import STATUS_META

MapaFeed = Literal["publico", "gestao", "export_publico", "export_gestao"]
GestaoLayer = Literal["principal", "municipal"]

_VISIBILITY_KEY: dict[MapaFeed, str] = {
    "publico": "visivel_mapa_publico",
    "gestao": "visivel_mapa_gestao",
    "export_publico": "export_publico",
    "export_gestao": "export_gestao",
}


def statuses_for_feed(mapa: MapaFeed) -> tuple[str, ...]:
    key = _VISIBILITY_KEY[mapa]
    return tuple(s for s, meta in STATUS_META.items() if meta.get(key))


def active_feed_stmt(
    *,
    mapa: MapaFeed = "publico",
    interaction_type: str | None = None,
    category: str | None = None,
    gestao_layer: GestaoLayer = "principal",
) -> Select[tuple[Report]]:
    """Consulta reportes visíveis conforme a matriz de status."""
    now_iso = datetime.now(timezone.utc).isoformat()
    statuses = statuses_for_feed(mapa)
    stmt = (
        select(Report)
        .where(Report.status.in_(statuses))
        .where((Report.valid_to.is_(None)) | (Report.valid_to > now_iso))
    )
    if interaction_type:
        stmt = stmt.where(Report.interaction_type == interaction_type)
    if category:
        stmt = stmt.where(Report.category == category)
    if mapa == "gestao":
        if gestao_layer == "principal":
            stmt = stmt.where(Report.status != "registro_municipal")
        elif gestao_layer == "municipal":
            stmt = stmt.where(Report.status == "registro_municipal")
    return stmt


def active_public_reports_stmt(*, interaction_type: str | None = None) -> Select[tuple[Report]]:
    """Compatível com exportações e feeds públicos legados."""
    return active_feed_stmt(mapa="export_publico", interaction_type=interaction_type)


def features_for_feed(
    db: Session,
    *,
    mapa: MapaFeed,
    interaction_type: str | None = None,
    category: str | None = None,
    gestao_layer: GestaoLayer = "principal",
    bbox: tuple[float, float, float, float] | None = None,
    since: str | None = None,
    min_priority: float = 0.0,
    limit: int | None = 5000,
) -> list[dict[str, Any]]:
    stmt = active_feed_stmt(
        mapa=mapa,
        interaction_type=interaction_type,
        category=category,
        gestao_layer=gestao_layer,
    )
    if since:
        stmt = stmt.where(Report.captured_at >= since)
    stmt = stmt.order_by(Report.received_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = db.execute(stmt).scalars().all()

    from .pipeline import report_to_feature

    features: list[dict[str, Any]] = []
    for r in rows:
        if r.priority < min_priority:
            continue
        if bbox and not (bbox[0] <= r.lon <= bbox[2] and bbox[1] <= r.lat <= bbox[3]):
            continue
        pub, gest = visibility_flags(r.status, valid_to=r.valid_to)
        if mapa == "publico" and not pub:
            continue
        if mapa == "gestao" and not gest:
            continue
        features.append(report_to_feature(r))
    return features


def feature_collection(
    db: Session,
    *,
    mapa: MapaFeed,
    interaction_type: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "type": "FeatureCollection",
        "features": features_for_feed(
            db,
            mapa=mapa,
            interaction_type=interaction_type,
            **kwargs,
        ),
        "generated_at": now_iso,
    }
