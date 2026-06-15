"""Integração real: HTTP → pipeline → persistência SQLite → endpoints de leitura.

Cada teste chama a API (TestClient), depois consulta o banco e o disco
para confirmar inserção/atualização — não mocks.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import func, select

from backend.config import settings
from backend.database import SessionLocal
from backend.models import AuditLog, Cluster, Report
from backend.services.road_context import STATUS_REGISTRO_MUNICIPAL
from backend.services.scope import (
    ROAD_SCOPE_ESTADUAL,
    ROAD_SCOPE_FEDERAL,
    ROAD_SCOPE_MUNICIPAL,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MALHA = FIXTURES / "malha_scope_test.geojson"
URBAN = FIXTURES / "mancha_urbana_test.geojson"

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


def _count(model) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model)) or 0  # pylint: disable=not-callable


def _get_report(report_id: str) -> Report:
    with SessionLocal() as db:
        row = db.get(Report, report_id)
        assert row is not None, f"Report {report_id} não existe no banco"
        return row


def _auth_headers(app_client) -> dict[str, str]:
    login = app_client.post("/api/auth/login", json={
        "username": "test-admin",
        "password": "test-pass",
    })
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['token']}"}


def _post_event(app_client, *, lat: float, lon: float, category: str = "buraco", **extra):
    nonce = app_client.get("/api/capture-nonce").json()["nonce"]
    files = {"photo": ("integ.jpg", _unique_jpeg(), "image/jpeg")}
    data = {
        "lat": str(lat),
        "lon": str(lon),
        "accuracy_m": "10",
        "category": category,
        "magnitude": "normal",
        "captured_at": _now_iso(),
        "capture_nonce": nonce,
        "client_id": f"integ-{secrets.token_hex(4)}",
        **extra,
    }
    return app_client.post("/api/reports", files=files, data=data)


@pytest.mark.usefixtures("scope_env")
class TestReportIntegrationPersistencia:
    """Inserções e rejeições no banco."""

    def test_urbana_nao_grava_linha(self, app_client):
        before = _count(Report)
        r = _post_event(app_client, lat=COORD_URBANA[0], lon=COORD_URBANA[1])
        assert r.status_code == 422
        assert _count(Report) == before

    def test_municipal_grava_registro_completo(self, app_client):
        r = _post_event(app_client, lat=COORD_MUNICIPAL[0], lon=COORD_MUNICIPAL[1])
        assert r.status_code == 201, r.text
        rid = r.json()["id"]

        row = _get_report(rid)
        assert row.status == STATUS_REGISTRO_MUNICIPAL
        assert row.road_scope == ROAD_SCOPE_MUNICIPAL
        assert row.interaction_type == "evento_trafego"
        assert row.category == "buraco"
        assert row.veracity_score > 0
        assert row.photo_path
        assert (settings.photo_dir / row.photo_path).is_file()
        assert row.veracity_signals_json
        json.loads(row.veracity_signals_json)
        assert row.road_context_json
        ctx = json.loads(row.road_context_json)
        assert ctx.get("scope") == ROAD_SCOPE_MUNICIPAL

    def test_estadual_grava_cluster_foto_e_scores(self, app_client):
        r = _post_event(
            app_client,
            lat=COORD_ESTADUAL[0],
            lon=COORD_ESTADUAL[1],
            category="acidente",
        )
        assert r.status_code == 201, r.text
        rid = r.json()["id"]

        row = _get_report(rid)
        assert row.road_scope == ROAD_SCOPE_ESTADUAL
        assert row.road_label
        assert "SP" in (row.road_label or "")
        assert row.cluster_id
        assert row.veracity_score > 0
        assert row.relevance_score > 0
        assert row.priority == pytest.approx(row.veracity_score * row.relevance_score, rel=1e-6)
        assert row.valid_to
        assert (settings.photo_dir / row.photo_path).is_file()

        with SessionLocal() as db:
            cluster = db.get(Cluster, row.cluster_id)
            assert cluster is not None
            assert cluster.category == "acidente"
            assert cluster.confirmations >= 1

    def test_federal_grava_road_scope(self, app_client):
        r = _post_event(
            app_client,
            lat=COORD_FEDERAL[0],
            lon=COORD_FEDERAL[1],
            category="acidente",
        )
        assert r.status_code == 201
        row = _get_report(r.json()["id"])
        assert row.road_scope == ROAD_SCOPE_FEDERAL
        ctx = json.loads(row.road_context_json or "{}")
        assert ctx.get("rodovia") == "BR 116"


@pytest.mark.usefixtures("scope_env")
class TestReportIntegrationEndpoints:
    """Leitura via API bate com o que está no banco."""

    def test_get_report_publico(self, app_client):
        r = _post_event(app_client, lat=COORD_ESTADUAL[0], lon=COORD_ESTADUAL[1])
        rid = r.json()["id"]
        row = _get_report(rid)

        api = app_client.get(f"/api/reports/{rid}")
        assert api.status_code == 200
        props = api.json()
        assert props["id"] == rid
        assert props["status"] == row.status
        assert props["category"] == row.category

    def test_moderation_detail_gestor(self, app_client):
        r = _post_event(
            app_client,
            lat=COORD_ESTADUAL[0],
            lon=COORD_ESTADUAL[1],
            category="bloqueio_total",
        )
        assert r.status_code == 201
        rid = r.json()["id"]
        headers = _auth_headers(app_client)

        detail = app_client.get(f"/api/moderation/reports/{rid}", headers=headers)
        assert detail.status_code == 200
        body = detail.json()
        assert body["id"] == rid
        assert body["status"] == "em_moderacao"
        assert body["road_scope"] == ROAD_SCOPE_ESTADUAL

    def test_stats_refletem_banco(self, app_client):
        before_mun = _count(Report)  # noqa: not used directly — baseline via stats
        _post_event(app_client, lat=COORD_MUNICIPAL[0], lon=COORD_MUNICIPAL[1])
        _post_event(
            app_client,
            lat=COORD_ESTADUAL[0],
            lon=COORD_ESTADUAL[1],
            category="alagamento",
        )
        headers = _auth_headers(app_client)
        stats = app_client.get("/api/moderation/stats", headers=headers)
        assert stats.status_code == 200
        body = stats.json()
        assert body["total"] >= before_mun + 2
        assert body["registros_municipais"] >= 1
        assert body["fila"] >= 1


@pytest.mark.usefixtures("scope_env")
class TestReportIntegrationModeracao:
    """Decisão do gestor persiste status + audit_log."""

    def test_publicar_atualiza_banco_e_audit(self, app_client):
        r = _post_event(
            app_client,
            lat=COORD_ESTADUAL[0],
            lon=COORD_ESTADUAL[1],
            category="bloqueio_total",
        )
        rid = r.json()["id"]
        headers = _auth_headers(app_client)

        decide = app_client.post(
            f"/api/moderation/{rid}/decide",
            headers=headers,
            json={"decision": "publicar", "note": "integração"},
        )
        assert decide.status_code == 200

        row = _get_report(rid)
        assert row.status == "publicado"

        with SessionLocal() as db:
            logs = db.execute(
                select(AuditLog).where(
                    AuditLog.target_type == "report",
                    AuditLog.target_id == rid,
                    AuditLog.action == "decide:publicar",
                )
            ).scalars().all()
            assert len(logs) == 1
            payload = json.loads(logs[0].payload_json or "{}")
            assert payload.get("note") == "integração"

    def test_descartar_atualiza_banco(self, app_client):
        r = _post_event(
            app_client,
            lat=COORD_ESTADUAL[0],
            lon=COORD_ESTADUAL[1],
            category="alagamento",
        )
        rid = r.json()["id"]
        headers = _auth_headers(app_client)

        decide = app_client.post(
            f"/api/moderation/{rid}/decide",
            headers=headers,
            json={"decision": "descartar", "note": "falso positivo"},
        )
        assert decide.status_code == 200
        assert _get_report(rid).status == "descartado"


@pytest.mark.usefixtures("scope_env")
class TestReportIntegrationManifestacao:
    """Manifestação grava linha distinta (sem cluster rodoviário)."""

    def test_manifestacao_persiste_sem_road_scope(self, app_client):
        nonce = app_client.get("/api/capture-nonce").json()["nonce"]
        files = {"photo": ("m.jpg", _unique_jpeg(), "image/jpeg")}
        data = {
            "lat": str(COORD_ESTADUAL[0]),
            "lon": str(COORD_ESTADUAL[1]),
            "category": "reclamacao",
            "interaction_type": "manifestacao",
            "description": "Integração: buraco profundo na lateral da pista estadual.",
            "captured_at": _now_iso(),
            "capture_nonce": nonce,
        }
        r = app_client.post("/api/reports", files=files, data=data)
        assert r.status_code == 201, r.text
        rid = r.json()["id"]

        row = _get_report(rid)
        assert row.interaction_type == "manifestacao"
        assert row.description
        assert row.cluster_id is None
        assert row.road_scope is None
        assert row.relevance_score == pytest.approx(row.priority)
