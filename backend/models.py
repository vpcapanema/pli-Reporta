"""Modelos SQLAlchemy. Schema espelha docs/DATA_MODEL.md."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    client_id: Mapped[str | None] = mapped_column(String(64))

    interaction_type: Mapped[str] = mapped_column(String(24), default="evento_trafego", index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    magnitude: Mapped[str] = mapped_column(String(16), default="normal")
    description: Mapped[str | None] = mapped_column(String(500))

    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    geometry_geojson: Mapped[str | None] = mapped_column(Text)

    photo_path: Mapped[str] = mapped_column(String(255))
    photo_hash: Mapped[str] = mapped_column(String(64), index=True)
    exif_json: Mapped[str | None] = mapped_column(Text)

    captured_at: Mapped[str] = mapped_column(String(32))
    received_at: Mapped[str] = mapped_column(String(32), default=_utcnow_iso)
    capture_nonce_valid: Mapped[int] = mapped_column(Integer, default=0)

    veracity_score: Mapped[float] = mapped_column(Float, default=0.0)
    veracity_signals_json: Mapped[str | None] = mapped_column(Text)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    status: Mapped[str] = mapped_column(String(24), default="submetido", index=True)

    cluster_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("clusters.id", ondelete="SET NULL"), index=True
    )

    valid_from: Mapped[str] = mapped_column(String(32), default=_utcnow_iso)
    valid_to: Mapped[str | None] = mapped_column(String(32), index=True)

    affected_edges_json: Mapped[str | None] = mapped_column(Text)

    road_scope: Mapped[str | None] = mapped_column(String(24), index=True)
    road_label: Mapped[str | None] = mapped_column(String(64))
    road_context_json: Mapped[str | None] = mapped_column(Text)


Index("ix_reports_status_validto", Report.status, Report.valid_to)
Index("ix_reports_lat_lon", Report.lat, Report.lon)


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)
    first_seen: Mapped[str] = mapped_column(String(32))
    last_seen: Mapped[str] = mapped_column(String(32), index=True)
    confirmations: Mapped[int] = mapped_column(Integer, default=1)
    resolve_votes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="ativo")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(32), default=_utcnow_iso)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str | None] = mapped_column(Text)


class ModerationPolicy(Base):
    """Política ativa do aprovador automático (linha única id=1)."""
    __tablename__ = "moderation_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    preset: Mapped[str] = mapped_column(String(24), default="equilibrado")
    event_publish_min: Mapped[float] = mapped_column(Float, default=0.70)
    event_discard_below: Mapped[float] = mapped_column(Float, default=0.30)
    manif_publish_min: Mapped[float] = mapped_column(Float, default=0.75)
    manif_discard_below: Mapped[float] = mapped_column(Float, default=0.40)
    always_review_blocking: Mapped[int] = mapped_column(Integer, default=1)
    always_review_offline: Mapped[int] = mapped_column(Integer, default=1)
    always_review_first_in_area: Mapped[int] = mapped_column(Integer, default=0)
    always_review_other: Mapped[int] = mapped_column(Integer, default=1)
    category_overrides_json: Mapped[str | None] = mapped_column(Text, default=None)
    veracity_weights_json: Mapped[str | None] = mapped_column(Text, default=None)
    highway_factors_json: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[str] = mapped_column(String(32), default=_utcnow_iso)
    updated_by: Mapped[str | None] = mapped_column(String(128))
