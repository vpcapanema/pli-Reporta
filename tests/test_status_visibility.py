"""Testes da matriz status → visibilidade."""
from __future__ import annotations

from backend.services.layer_schema import (
    GESTAO_MAP_STATUSES,
    PUBLIC_MAP_STATUSES,
    feed_visible,
    visibility_flags,
)
from backend.services.report_catalog import STATUS_META, status_visibility_matrix


def test_status_meta_has_visibility_fields():
    for status_id, meta in STATUS_META.items():
        assert "visivel_mapa_publico" in meta, status_id
        assert "visivel_mapa_gestao" in meta, status_id
        assert "export_publico" in meta, status_id
        assert "export_gestao" in meta, status_id


def test_public_map_statuses():
    assert PUBLIC_MAP_STATUSES == frozenset({"publicado", "resolvido"})


def test_gestao_includes_pipeline_statuses():
    assert "em_moderacao" in GESTAO_MAP_STATUSES
    assert "validado" in GESTAO_MAP_STATUSES
    assert "descartado" not in GESTAO_MAP_STATUSES


def test_visibility_matrix_row_count():
    assert len(status_visibility_matrix()) == len(STATUS_META)


def test_valid_to_overrides_publicado():
    past = "2020-01-01T00:00:00+00:00"
    assert visibility_flags("publicado", valid_to=past) == (False, False)
    assert feed_visible("publicado", valid_to=past, mapa="export_publico") is False


def test_resolvido_visible_on_public_map():
    assert visibility_flags("resolvido") == (True, True)


def test_registro_municipal_not_public():
    assert visibility_flags("registro_municipal") == (False, True)
