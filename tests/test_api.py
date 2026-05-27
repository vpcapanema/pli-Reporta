"""Testes ponta-a-ponta da API com TestClient."""
from __future__ import annotations

from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_healthz(app_client):
    r = app_client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "queue_size" in body


def test_capture_nonce(app_client):
    r = app_client.get("/api/v1/capture-nonce")
    assert r.status_code == 200
    body = r.json()
    assert body["nonce"]
    assert body["expires_in"] > 0


def test_create_report_with_nonce(app_client, jpeg_bytes):
    nonce = app_client.get("/api/v1/capture-nonce").json()["nonce"]
    files = {"photo": ("c.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "lat": "-23.55",
        "lon": "-46.63",
        "accuracy_m": "12",
        "category": "buraco",
        "magnitude": "normal",
        "captured_at": _now_iso(),
        "capture_nonce": nonce,
        "client_id": "test-client",
    }
    r = app_client.post("/api/v1/reports", files=files, data=data)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] in ("validado", "em_moderacao", "descartado")
    assert 0.0 <= body["veracity_score"] <= 1.0
    assert 0.0 <= body["relevance_score"] <= 1.0
    assert body["explanation"]
    assert body["id"]


def test_create_report_without_nonce_lower_score(app_client, jpeg_bytes):
    files = {"photo": ("c.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "lat": "-23.55", "lon": "-46.63",
        "category": "buraco", "captured_at": _now_iso(),
        "client_id": "no-nonce",
    }
    r = app_client.post("/api/v1/reports", files=files, data=data)
    assert r.status_code == 201
    assert r.json()["veracity_score"] < 0.95


def test_incidents_feed_geojson(app_client, jpeg_bytes):
    nonce = app_client.get("/api/v1/capture-nonce").json()["nonce"]
    files = {"photo": ("c.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "lat": "-23.55", "lon": "-46.63", "accuracy_m": "10",
        "category": "alagamento", "magnitude": "grave",
        "captured_at": _now_iso(), "capture_nonce": nonce,
    }
    app_client.post("/api/v1/reports", files=files, data=data)

    r = app_client.get("/api/v1/incidents.geojson")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert isinstance(fc["features"], list)


def test_moderation_requires_key(app_client):
    r = app_client.get("/api/v1/moderation/queue")
    assert r.status_code == 401


def test_moderation_with_key(app_client):
    r = app_client.get(
        "/api/v1/moderation/queue",
        headers={"X-API-Key": "test-mod-key"},
    )
    assert r.status_code == 200
    assert "items" in r.json()
