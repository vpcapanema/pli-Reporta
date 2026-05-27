"""Tarefas de manutenção: expiração e limpeza."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update

from ..database import session_scope
from ..models import Cluster, Report


def expire_old_reports() -> int:
    """Move reportes vencidos para status 'expirado'. Retorna quantidade afetada."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with session_scope() as db:
        stmt = (
            update(Report)
            .where(
                Report.status.in_(("validado", "publicado", "em_moderacao")),
                Report.valid_to.isnot(None),
                Report.valid_to <= now_iso,
            )
            .values(status="expirado")
        )
        result = db.execute(stmt)
        return result.rowcount or 0


def close_inactive_clusters(idle_hours: float = 24.0) -> int:
    now_iso = datetime.now(timezone.utc).isoformat()
    with session_scope() as db:
        clusters = db.execute(
            select(Cluster).where(Cluster.status == "ativo")
        ).scalars().all()
        n = 0
        for c in clusters:
            try:
                last = datetime.fromisoformat(c.last_seen.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600.0
            if age_h > idle_hours:
                c.status = "fechado"
                db.add(c)
                n += 1
        return n
