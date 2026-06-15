"""Tarefas de manutenção: expiração, limpeza e resolução automática.

O ciclo de vida dos eventos é automático:
- TTL por categoria define o `valid_to`; vencido → status 'expirado'.
- Confirmações repetidas no mesmo ponto renovam o `valid_to` (feito no pipeline).
- Contra-reportes ('já foi resolvido') acumulam votos no cluster; ao atingir o
  limiar, o evento vira 'resolvido'.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update

from ..config import settings
from ..database import session_scope
from ..models import Cluster, Report


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def expire_old_reports() -> int:
    """Move reportes vencidos para status 'expirado'. Retorna quantidade afetada."""
    now_iso = _now_iso()
    with session_scope() as db:
        ids = list(
            db.execute(
                select(Report.id).where(
                    Report.status.in_(("validado", "publicado", "em_moderacao")),
                    Report.valid_to.isnot(None),
                    Report.valid_to <= now_iso,
                )
            ).scalars().all()
        )
        if not ids:
            return 0
        db.execute(
            update(Report)
            .where(Report.id.in_(ids))
            .values(status="expirado")
        )
        from .layer_publish import refresh_reports_layers

        refresh_reports_layers(db, ids)
        return len(ids)


def close_inactive_clusters(idle_hours: float | None = None) -> int:
    idle = settings.cluster_idle_hours if idle_hours is None else idle_hours
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
            if age_h > idle:
                c.status = "fechado"
                db.add(c)
                n += 1
        return n


def register_resolve_vote(cluster_id: str) -> dict:
    """Registra um contra-reporte ('já foi resolvido') para um cluster.

    Ao atingir o limiar de votos, marca o cluster e seus reportes ativos como
    'resolvido'. Retorna o estado resultante para o cliente.
    """
    threshold = settings.resolve_votes_threshold
    with session_scope() as db:
        cluster = db.get(Cluster, cluster_id)
        if cluster is None:
            return {"found": False}
        if cluster.status == "resolvido":
            return {"found": True, "resolved": True, "votes": cluster.resolve_votes}

        cluster.resolve_votes = (cluster.resolve_votes or 0) + 1
        resolved = cluster.resolve_votes >= threshold
        if resolved:
            cluster.status = "resolvido"
            db.execute(
                update(Report)
                .where(
                    Report.cluster_id == cluster.id,
                    Report.status.in_(("publicado", "validado", "em_moderacao")),
                )
                .values(status="resolvido")
            )
            from .layer_publish import refresh_reports_layers

            resolved_ids = list(
                db.execute(
                    select(Report.id).where(
                        Report.cluster_id == cluster.id,
                        Report.status == "resolvido",
                    )
                ).scalars().all()
            )
            refresh_reports_layers(db, resolved_ids)
        db.add(cluster)
        return {
            "found": True,
            "resolved": resolved,
            "votes": cluster.resolve_votes,
            "threshold": threshold,
        }


def run_maintenance() -> dict:
    """Executa um ciclo completo de manutenção. Idempotente."""
    expired = expire_old_reports()
    closed = close_inactive_clusters()
    return {"expired": expired, "closed_clusters": closed, "ran_at": _now_iso()}
