"""Clusterização leve no MVP: busca incremental de cluster compatível.

Quando um novo reporte chega, procuramos um cluster da MESMA categoria, ativo,
dentro de um raio (default 80 m) e com `last_seen` recente conforme TTL da categoria.
Se existe, anexamos. Se não, criamos.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Cluster
from .geo import haversine_m
from .ids import new_ulid
from .relevance import ttl_for


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_or_create_cluster(
    db: Session,
    *,
    category: str,
    lat: float,
    lon: float,
    radius_m: float = 80.0,
) -> Cluster:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_for(category))).isoformat()
    candidates = db.execute(
        select(Cluster).where(
            Cluster.category == category,
            Cluster.status == "ativo",
            Cluster.last_seen >= cutoff,
        )
    ).scalars().all()

    best: Cluster | None = None
    best_d = float("inf")
    for c in candidates:
        d = haversine_m(lat, lon, c.centroid_lat, c.centroid_lon)
        if d <= radius_m and d < best_d:
            best, best_d = c, d

    if best is not None:
        # Atualiza centróide com média móvel simples ponderada por contagem.
        n = best.confirmations
        best.centroid_lat = (best.centroid_lat * n + lat) / (n + 1)
        best.centroid_lon = (best.centroid_lon * n + lon) / (n + 1)
        best.confirmations = n + 1
        best.last_seen = _now_iso()
        db.add(best)
        return best

    new = Cluster(
        id=new_ulid(),
        category=category,
        centroid_lat=lat,
        centroid_lon=lon,
        first_seen=_now_iso(),
        last_seen=_now_iso(),
        confirmations=1,
        status="ativo",
    )
    db.add(new)
    db.flush()
    return new
