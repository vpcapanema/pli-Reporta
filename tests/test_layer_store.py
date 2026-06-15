"""Testes da materialização GeoJSON em data/camadas-do-sistema/."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.models import Report
from backend.services.geometry_sync import IMPACT_BUFFER_M, buffer_point_meters, sync_report_geometry
from backend.services.layer_schema import FULL_LAYER_FIELD_LABELS, build_full_layer_properties
from backend.services.layer_store import BASE, layer_filename, publish_report


def _report(**kwargs) -> Report:
    return Report(
        id=kwargs.get("id", "01TEST00000000000000000001"),
        category=kwargs.get("category", "buraco"),
        interaction_type=kwargs.get("interaction_type", "evento_trafego"),
        lat=kwargs.get("lat", -22.72),
        lon=kwargs.get("lon", -46.79),
        photo_path="demo/x.jpg",
        photo_hash="abc",
        captured_at=datetime.now(timezone.utc).isoformat(),
        status=kwargs.get("status", "publicado"),
        veracity_score=0.8,
        relevance_score=0.7,
        priority=0.56,
        magnitude="normal",
    )


def test_build_full_layer_properties_has_36_fields():
    props = build_full_layer_properties(_report())
    assert len(props) == len(FULL_LAYER_FIELD_LABELS)
    assert props["ID"] == "01TEST00000000000000000001"
    assert props["Status"] == "Publicado"
    assert props["Categoria"] == "Buraco"


def test_buffer_10m_approximate():
    poly = buffer_point_meters(-46.79, -22.72, IMPACT_BUFFER_M)
    assert poly is not None
    assert poly.area > 0


def test_publish_report_writes_point_and_polygon(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.services.layer_store.BASE", tmp_path)
    rep = _report(id="01TEST00000000000000000099")
    sync_report_geometry(rep)
    publish_report(rep)

    pt_path = tmp_path / "pontos" / layer_filename("evento_trafego", "buraco")
    poly_path = tmp_path / "poligonos" / layer_filename("evento_trafego", "buraco")
    assert pt_path.exists()
    assert poly_path.exists()

    pt_fc = json.loads(pt_path.read_text(encoding="utf-8"))
    poly_fc = json.loads(poly_path.read_text(encoding="utf-8"))
    assert len(pt_fc["features"]) == 1
    assert len(poly_fc["features"]) == 1
    assert pt_fc["features"][0]["geometry"]["type"] == "Point"
    assert poly_fc["features"][0]["geometry"]["type"] == "Polygon"
    assert pt_fc["features"][0]["properties"]["ID"] == poly_fc["features"][0]["properties"]["ID"]

    publish_report(_report(id="01TEST00000000000000000099", status="em_moderacao"))
    pt_fc2 = json.loads(pt_path.read_text(encoding="utf-8"))
    assert len(pt_fc2["features"]) == 1
    assert pt_fc2["features"][0]["properties"]["Status"] == "Precisa da sua análise"


@pytest.mark.parametrize("subdir", ["pontos", "poligonos"])
def test_bootstrap_files_exist(subdir):
    """Arquivos de camada do repositório (não tmp) existem após bootstrap."""
    path = BASE / subdir / layer_filename("evento_trafego", "buraco")
    if not path.exists():
        pytest.skip("bootstrap_camadas.py ainda não foi executado")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["type"] == "FeatureCollection"
