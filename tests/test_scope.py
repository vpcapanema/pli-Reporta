"""Testes do gate de escopo viário (DER + mancha urbana IBGE)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.services.road_context import STATUS_REGISTRO_MUNICIPAL
from backend.services.scope import (
    ROAD_SCOPE_ESTADUAL,
    ROAD_SCOPE_FEDERAL,
    ROAD_SCOPE_MUNICIPAL,
    ScopeRejectedError,
    classify_traffic_scope,
    scope_gate_enabled,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MALHA = FIXTURES / "malha_scope_test.geojson"
URBAN = FIXTURES / "mancha_urbana_test.geojson"


@pytest.fixture(name="scope_env")
def _scope_env(monkeypatch):
    monkeypatch.setenv("ROADS_GEOJSON_PATH", str(MALHA))
    monkeypatch.setenv("URBAN_GEOJSON_PATH", str(URBAN))
    from backend.config import Settings

    fresh = Settings()
    monkeypatch.setattr("backend.services.scope.settings", fresh)
    monkeypatch.setattr("backend.services.pipeline.settings", fresh, raising=False)
    return fresh


@pytest.mark.usefixtures("scope_env")
def test_scope_gate_enabled():
    assert scope_gate_enabled() is True


@pytest.mark.usefixtures("scope_env")
def test_rejects_urban_without_der_snap():
    with pytest.raises(ScopeRejectedError):
        classify_traffic_scope(-23.55, -46.63)


@pytest.mark.usefixtures("scope_env")
def test_accepts_estadual_on_der():
    result = classify_traffic_scope(-22.895, -47.065)
    assert result.scope == ROAD_SCOPE_ESTADUAL
    assert "SP" in (result.rodovia or "")


@pytest.mark.usefixtures("scope_env")
def test_accepts_federal_on_der():
    result = classify_traffic_scope(-23.095, -46.495)
    assert result.scope == ROAD_SCOPE_FEDERAL
    assert result.rodovia == "BR 116"


@pytest.mark.usefixtures("scope_env")
def test_classifies_municipal_outside_urban():
    result = classify_traffic_scope(-22.50, -47.80)
    assert result.scope == ROAD_SCOPE_MUNICIPAL
    assert result.context.get("scope") == ROAD_SCOPE_MUNICIPAL


def test_api_rejects_urban_report(app_client, scope_env, jpeg_bytes):
    del scope_env  # fixture: aplica paths DER/IBGE nos serviços
    nonce = app_client.get("/api/v1/capture-nonce").json()["nonce"]
    files = {"photo": ("c.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "lat": "-23.55",
        "lon": "-46.63",
        "category": "buraco",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "capture_nonce": nonce,
    }
    r = app_client.post("/api/v1/reports", files=files, data=data)
    assert r.status_code == 422, r.text
    assert "via urbana" in r.json()["detail"].lower()


def test_api_stores_municipal_report_without_publication(app_client, scope_env):
    del scope_env
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (320, 240), (80, 120, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    jpeg = buf.getvalue()

    nonce = app_client.get("/api/v1/capture-nonce").json()["nonce"]
    files = {"photo": ("municipal.jpg", jpeg, "image/jpeg")}
    data = {
        "lat": "-22.50",
        "lon": "-47.80",
        "category": "buraco",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "capture_nonce": nonce,
    }
    r = app_client.post("/api/v1/reports", files=files, data=data)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["road_scope"] == ROAD_SCOPE_MUNICIPAL
    assert body["status"] == STATUS_REGISTRO_MUNICIPAL
    assert "prefeitura" in body["message"].lower()


def test_municipal_not_in_public_feed(app_client, scope_env):
    del scope_env
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (320, 240), (80, 120, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    jpeg = buf.getvalue()

    nonce = app_client.get("/api/v1/capture-nonce").json()["nonce"]
    files = {"photo": ("municipal2.jpg", jpeg, "image/jpeg")}
    data = {
        "lat": "-22.50",
        "lon": "-47.80",
        "category": "buraco",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "capture_nonce": nonce,
    }
    created = app_client.post("/api/v1/reports", files=files, data=data)
    assert created.status_code == 201
    rid = created.json()["id"]

    feed = app_client.get("/api/v1/incidents.geojson")
    ids = [f["properties"]["id"] for f in feed.json()["features"]]
    assert rid not in ids
