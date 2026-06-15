"""Testes do contexto viário enriquecido."""
from __future__ import annotations

from backend.services.road_context import (
    MANAGER_REVIEW_SCOPES,
    context_from_der_snap,
    der_layer_properties,
    format_road_context_value,
    friendly_road_lines,
    requires_manager_review,
    road_context_popup_rows,
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
            "jurisdicao": "Estadual",
            "perimetro_urbano": "S",
        }
    }
    ctx = context_from_der_snap(scope="estadual", feat=feat, dist_m=12.4)
    assert ctx["rodovia"] == "SP 330"
    assert ctx["denominacao"] == "Anhanguera"
    assert "jurisdicao" not in ctx
    assert "perimetro_urbano" not in ctx
    rows = road_context_popup_rows(ctx)
    labels = [label for label, _ in rows]
    assert "Classificação viária" in labels
    assert "Rodovia" in labels
    assert "Coordenadoria Regional Geral DER" in labels
    assert "Residência de conserva DER" in labels
    assert any(label == "Distância snap utilizada" and value == "12,4 m" for label, value in rows)
    layer = der_layer_properties(ctx)
    assert layer["Rodovia"] == "SP 330 — Anhanguera"
    assert layer["Classificação viária"] == "Rodovia estadual"
    assert "Jurisdicao" not in layer
    assert format_road_context_value("tipo_pista", "DUP") == "Duplicada"
    assert format_road_context_value("administra", "DER") == "DER-SP"
    assert format_road_context_value("snap_dist_m", 12.4) == "12,4 m"
    lines = friendly_road_lines(ctx)
    assert any("SP 330" in ln for ln in lines)
    assert all("jurisdicao" not in ln.lower() for ln in lines)
