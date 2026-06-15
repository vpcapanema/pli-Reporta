"""Testes do esquema completo de camadas."""
from __future__ import annotations

from backend.services.layer_schema import (
    FULL_LAYER_FIELD_LABELS,
    SYSTEM_LAYER_FIELD_LABELS,
)
from backend.services.road_context import DER_LAYER_FIELD_LABELS


def test_full_layer_field_count():
    assert len(SYSTEM_LAYER_FIELD_LABELS) == 25
    assert len(DER_LAYER_FIELD_LABELS) == 11
    assert len(FULL_LAYER_FIELD_LABELS) == 36


def test_der_snap_label():
    assert "Distância snap utilizada" in DER_LAYER_FIELD_LABELS
    assert "Distância ao trecho DER" not in DER_LAYER_FIELD_LABELS
