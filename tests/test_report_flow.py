"""Testes práticos do fluxo completo de reporte (escopo → scores → status → gestão).

Cenários cobertos:
  1. Via urbana (IBGE) sem snap DER → HTTP 422
  2. Municipal → registro_municipal, fora do mapa e da fila DER
  3. Estadual / federal → pipeline DER (V, R, status automático)
  4. Bloqueante → em_moderacao + fila do gestor → decisão publicar
  5. Manifestação → pipeline L
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from backend.services.road_context import STATUS_REGISTRO_MUNICIPAL
from backend.services.scope import (
    ROAD_SCOPE_ESTADUAL,
    ROAD_SCOPE_FEDERAL,
    ROAD_SCOPE_MUNICIPAL,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MALHA = FIXTURES / "malha_scope_test.geojson"
URBAN = FIXTURES / "mancha_urbana_test.geojson"

# Coordenadas dos fixtures (malha_scope_test + mancha_urbana_test)
COORD_URBANA = (-23.55, -46.63)
COORD_ESTADUAL = (-22.895, -47.065)
COORD_FEDERAL = (-23.095, -46.495)
COORD_MUNICIPAL = (-22.50, -47.80)


@pytest.fixture(name="scope_env")
def _scope_env(monkeypatch):
    monkeypatch.setenv("ROADS_GEOJSON_PATH", str(MALHA))
    monkeypatch.setenv("URBAN_GEOJSON_PATH", str(URBAN))
    from backend.config import Settings

    fresh = Settings()
    monkeypatch.setattr("backend.services.scope.settings", fresh)
    monkeypatch.setattr("backend.services.pipeline.settings", fresh, raising=False)
    return fresh


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique_jpeg() -> bytes:
    r, g, b = secrets.randbelow(256), secrets.randbelow(256), secrets.randbelow(256)
    img = Image.new("RGB", (96, 96), (r, g, b))
    img.putpixel((0, 0), (secrets.randbelow(256), secrets.randbelow(256), secrets.randbelow(256)))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _auth_headers(app_client) -> dict[str, str]:
    login = app_client.post("/api/auth/login", json={
        "username": "test-admin",
        "password": "test-pass",
    })
    assert login.status_code == 200
    token = login.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _post_event(
    app_client,
    *,
    lat: float,
    lon: float,
    category: str = "buraco",
    client_id: str | None = None,
) -> dict:
    nonce = app_client.get("/api/capture-nonce").json()["nonce"]
    files = {"photo": ("flow.jpg", _unique_jpeg(), "image/jpeg")}
    data = {
        "lat": str(lat),
        "lon": str(lon),
        "accuracy_m": "10",
        "category": category,
        "magnitude": "normal",
        "captured_at": _now_iso(),
        "capture_nonce": nonce,
        "client_id": client_id or f"flow-{secrets.token_hex(4)}",
    }
    r = app_client.post("/api/reports", files=files, data=data)
    return r


@pytest.mark.usefixtures("scope_env")
class TestReportFlowScope:
    """Gate geográfico antes do pipeline."""

    def test_urbana_recusada_422(self, app_client):
        r = _post_event(app_client, lat=COORD_URBANA[0], lon=COORD_URBANA[1])
        assert r.status_code == 422, r.text
        assert "via urbana" in r.json()["detail"].lower()

    def test_municipal_registro_interno(self, app_client):
        r = _post_event(app_client, lat=COORD_MUNICIPAL[0], lon=COORD_MUNICIPAL[1])
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["road_scope"] == ROAD_SCOPE_MUNICIPAL
        assert body["status"] == STATUS_REGISTRO_MUNICIPAL
        assert "prefeitura" in body["message"].lower()

    def test_estadual_classifica_e_processa(self, app_client):
        r = _post_event(app_client, lat=COORD_ESTADUAL[0], lon=COORD_ESTADUAL[1])
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["road_scope"] == ROAD_SCOPE_ESTADUAL
        assert body["status"] in ("publicado", "em_moderacao", "descartado")
        assert 0.0 <= body["veracity_score"] <= 1.0
        assert body["relevance_score"] > 0

    def test_federal_classifica_e_processa(self, app_client):
        r = _post_event(
            app_client,
            lat=COORD_FEDERAL[0],
            lon=COORD_FEDERAL[1],
            category="acidente",
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["road_scope"] == ROAD_SCOPE_FEDERAL
        assert body["status"] in ("publicado", "em_moderacao", "descartado")


@pytest.mark.usefixtures("scope_env")
class TestReportFlowVisibility:
    """O que aparece (ou não) para cidadão e gestor."""

    def test_municipal_fora_do_mapa_publico(self, app_client):
        created = _post_event(app_client, lat=COORD_MUNICIPAL[0], lon=COORD_MUNICIPAL[1])
        rid = created.json()["id"]
        feed = app_client.get("/api/incidents.geojson").json()
        ids = [f["properties"]["id"] for f in feed["features"]]
        assert rid not in ids

    def test_municipal_fora_da_fila_der(self, app_client):
        created = _post_event(app_client, lat=COORD_MUNICIPAL[0], lon=COORD_MUNICIPAL[1])
        rid = created.json()["id"]
        headers = _auth_headers(app_client)
        queue = app_client.get("/api/moderation/queue", headers=headers).json()
        qids = [it["id"] for it in queue["items"]]
        assert rid not in qids

    def test_municipal_no_export_geojson(self, app_client):
        created = _post_event(app_client, lat=COORD_MUNICIPAL[0], lon=COORD_MUNICIPAL[1])
        rid = created.json()["id"]
        headers = _auth_headers(app_client)
        geo = app_client.get("/api/moderation/municipal.geojson", headers=headers)
        assert geo.status_code == 200
        ids = [f["properties"]["id"] for f in geo.json()["features"]]
        assert rid in ids


@pytest.mark.usefixtures("scope_env")
class TestReportFlowModeration:
    """Fila DER e decisão humana."""

    def test_bloqueante_estadual_vai_para_fila(self, app_client):
        r = _post_event(
            app_client,
            lat=COORD_ESTADUAL[0],
            lon=COORD_ESTADUAL[1],
            category="alagamento",
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["road_scope"] == ROAD_SCOPE_ESTADUAL
        assert body["status"] == "em_moderacao"

        headers = _auth_headers(app_client)
        queue = app_client.get("/api/moderation/queue", headers=headers).json()
        assert body["id"] in [it["id"] for it in queue["items"]]

    def test_gestor_publica_da_fila(self, app_client):
        r = _post_event(
            app_client,
            lat=COORD_ESTADUAL[0],
            lon=COORD_ESTADUAL[1],
            category="bloqueio_total",
        )
        assert r.status_code == 201
        rid = r.json()["id"]
        assert r.json()["status"] == "em_moderacao"

        headers = _auth_headers(app_client)
        decide = app_client.post(
            f"/api/moderation/{rid}/decide",
            headers=headers,
            json={"decision": "publicar", "note": "teste fluxo"},
        )
        assert decide.status_code == 200, decide.text
        assert decide.json()["status"] == "publicado"

        feed = app_client.get("/api/incidents.geojson").json()
        assert rid in [f["properties"]["id"] for f in feed["features"]]


@pytest.mark.usefixtures("scope_env")
class TestReportFlowManifestacao:
    """Manifestações usam L, não escopo DER."""

    def test_manifestacao_com_texto(self, app_client):
        nonce = app_client.get("/api/capture-nonce").json()["nonce"]
        files = {"photo": ("manif.jpg", _unique_jpeg(), "image/jpeg")}
        data = {
            "lat": str(COORD_ESTADUAL[0]),
            "lon": str(COORD_ESTADUAL[1]),
            "accuracy_m": "10",
            "category": "elogio",
            "interaction_type": "manifestacao",
            "description": "Excelente sinalização neste trecho da rodovia estadual.",
            "captured_at": _now_iso(),
            "capture_nonce": nonce,
        }
        r = app_client.post("/api/reports", files=files, data=data)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["interaction_type"] == "manifestacao"
        assert body["status"] in ("publicado", "em_moderacao", "descartado")
        assert body["message"]
