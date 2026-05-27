"""Testes unitários dos serviços de scoring."""
from __future__ import annotations

from datetime import datetime, timezone

from backend.services.relevance import (
    BLOCKING_CATEGORIES,
    compute_relevance,
    is_blocking,
    ttl_for,
)
from backend.services.veracity import compute_veracity


def test_relevance_severity_ordering():
    now_iso = datetime.now(timezone.utc).isoformat()
    r_block = compute_relevance(
        category="bloqueio_total", magnitude="grave", n_confirmations=3,
        captured_at_iso=now_iso, highway="motorway",
    ).value()
    r_buraco = compute_relevance(
        category="buraco", magnitude="leve", n_confirmations=1,
        captured_at_iso=now_iso, highway="residential",
    ).value()
    assert r_block > r_buraco
    assert 0.0 <= r_buraco <= 1.0
    assert 0.0 <= r_block <= 1.0


def test_relevance_persistence_decays():
    fresh_iso = datetime.now(timezone.utc).isoformat()
    old = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    r_fresh = compute_relevance(
        category="acidente", magnitude="normal", n_confirmations=1,
        captured_at_iso=fresh_iso, highway="primary",
    ).value()
    r_old = compute_relevance(
        category="acidente", magnitude="normal", n_confirmations=1,
        captured_at_iso=old, highway="primary",
    ).value()
    assert r_fresh > r_old


def test_blocking_rules():
    assert "bloqueio_total" in BLOCKING_CATEGORIES
    assert is_blocking("bloqueio_total", 0.9) is True
    assert is_blocking("bloqueio_total", 0.5) is False
    assert is_blocking("buraco", 0.99) is False


def test_ttl_for_known_categories():
    assert ttl_for("acidente") == 2
    assert ttl_for("buraco") == 24 * 90
    assert ttl_for("desconhecida") > 0  # fallback


def test_veracity_signals_scale():
    now_iso = datetime.now(timezone.utc).isoformat()
    score_good, signals = compute_veracity(
        lat=-23.55, lon=-46.63, accuracy_m=10,
        exif={"lat": -23.55, "lon": -46.63, "datetime": "2026:05:27 12:00:00"},
        captured_at_iso=now_iso,
        nonce_valid=True,
        reputation=0.5,
    )
    score_bad, _ = compute_veracity(
        lat=-23.55, lon=-46.63, accuracy_m=900,
        exif={"software": "Photoshop CS6"},
        captured_at_iso="2020-01-01T00:00:00+00:00",
        nonce_valid=False,
        reputation=0.0,
    )
    assert 0.0 <= score_bad <= score_good <= 1.0
    assert score_good > 0.5
    assert score_bad < score_good
    # Garante que toda decisão é auditável
    assert all(s.detail for s in signals)
