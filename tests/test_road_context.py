"""Testes do contexto viário enriquecido."""
from __future__ import annotations

from backend.services.road_context import (
    MANAGER_REVIEW_SCOPES,
    context_from_der_snap,
    friendly_road_lines,
    requires_manager_review,
    scope_label,
)


def test_requires_manager_review():
    assert requires_manager_review("estadual") is True
    assert requires_manager_review("federal") is True
    assert requires_manager_review("municipal") is False
    assert requires_manager_review(None) is False
    assert MANAGER_REVIEW_SCOPES == frozenset({"estadual", "federal"})


def test_scope_labels():
    assert scope_label("federal") == "Rodovia federal"
    assert scope_label("estadual") == "Rodovia estadual"
    assert scope_label("municipal") == "Via municipal"


def test_context_from_der_snap():
    feat = {
        "properties": {
            "rodovia": "SP 330",
            "denominacao": "Anhanguera",
            "tipo_rodoviario": "Eixo",
            "municipio": "Campinas",
            "cod_regional": "DR 01",
            "sede_regional": "Campinas",
            "residencia": "01.01",
            "sede_residencia": "Campinas",
        }
    }
    ctx = context_from_der_snap(scope="estadual", feat=feat, dist_m=12.4)
    assert ctx["rodovia"] == "SP 330"
    assert ctx["denominacao"] == "Anhanguera"
    lines = friendly_road_lines(ctx)
    assert any("Rodovia estadual" in ln for ln in lines)
    assert any("SP 330" in ln for ln in lines)
