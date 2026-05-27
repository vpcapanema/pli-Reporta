"""Cálculo de Relevância R (METODOLOGIA §4).

R = R_severidade · R_confirmacao · R_persistencia · R_afetacao
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

# Tabelas em alinhamento literal com METODOLOGIA §4.1
SEVERITY_BASE: dict[str, float] = {
    "bloqueio_total": 1.00,
    "acidente": 0.85,
    "alagamento": 0.85,
    "obra_grande": 0.70,
    "lentidao_corredor": 0.65,
    "sinalizacao_quebrada": 0.50,
    "buraco": 0.40,
    "outro": 0.30,
}

TTL_HOURS: dict[str, float] = {
    "bloqueio_total": 6,
    "acidente": 2,
    "alagamento": 12,
    "obra_grande": 24 * 30,
    "lentidao_corredor": 1,
    "sinalizacao_quebrada": 24 * 14,
    "buraco": 24 * 90,
    "outro": 24 * 7,
}

BLOCKING_CATEGORIES = {"bloqueio_total", "alagamento"}

MAGNITUDE_FACTOR: dict[str, float] = {"leve": 0.7, "normal": 1.0, "grave": 1.2}

HIGHWAY_FACTOR: dict[str, float] = {
    "motorway": 1.00,
    "motorway_link": 1.00,
    "trunk": 1.00,
    "trunk_link": 1.00,
    "primary": 0.85,
    "primary_link": 0.85,
    "secondary": 0.70,
    "secondary_link": 0.70,
    "tertiary": 0.55,
    "tertiary_link": 0.55,
    "residential": 0.35,
    "unclassified": 0.35,
    "service": 0.15,
    "track": 0.15,
}


@dataclass
class RelevanceBreakdown:
    severity: float
    confirmation: float
    persistence: float
    afetacao: float

    def value(self) -> float:
        return max(0.0, min(1.0, self.severity * self.confirmation * self.persistence * self.afetacao))

    def explain(self) -> list[str]:
        return [
            f"R_severidade={self.severity:.2f}",
            f"R_confirmacao={self.confirmation:.2f}",
            f"R_persistencia={self.persistence:.2f}",
            f"R_afetacao={self.afetacao:.2f}",
        ]


def _r_severity(category: str, magnitude: str) -> float:
    base = SEVERITY_BASE.get(category, 0.3)
    return max(0.0, min(1.0, base * MAGNITUDE_FACTOR.get(magnitude, 1.0)))


def _r_confirmation(n_confirmations: int, k: float = 0.6) -> float:
    n = max(1, n_confirmations)
    return 0.5 + 0.5 * (1.0 - math.exp(-k * n))


def _r_persistence(captured_at_iso: str, ttl_h: float, now: datetime | None = None) -> float:
    try:
        s = captured_at_iso
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        cap = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return 1.0
    if cap.tzinfo is None:
        cap = cap.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    age_h = max(0.0, (now - cap).total_seconds() / 3600.0)
    return math.exp(-age_h / max(0.1, ttl_h))


def _r_afetacao(highway: str | None) -> float:
    if not highway:
        return 0.5  # neutro quando não há base de vias
    return HIGHWAY_FACTOR.get(highway, 0.4)


def ttl_for(category: str) -> float:
    return TTL_HOURS.get(category, 24 * 7)


def is_blocking(category: str, priority: float) -> bool:
    return category in BLOCKING_CATEGORIES and priority > 0.80


def compute_relevance(
    *,
    category: str,
    magnitude: str,
    n_confirmations: int,
    captured_at_iso: str,
    highway: str | None,
) -> RelevanceBreakdown:
    return RelevanceBreakdown(
        severity=_r_severity(category, magnitude),
        confirmation=_r_confirmation(n_confirmations),
        persistence=_r_persistence(captured_at_iso, ttl_for(category)),
        afetacao=_r_afetacao(highway),
    )
