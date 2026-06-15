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
    assert body["status"] in ("publicado", "em_moderacao", "descartado")
    assert body["message"]
    assert body["interaction_type"] == "evento_trafego"
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


def test_create_manifestation(app_client, jpeg_bytes):
    nonce = app_client.get("/api/v1/capture-nonce").json()["nonce"]
    files = {"photo": ("c.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "lat": "-23.55",
        "lon": "-46.63",
        "accuracy_m": "12",
        "category": "elogio",
        "interaction_type": "manifestacao",
        "description": "Excelente conservação da rodovia neste trecho.",
        "captured_at": _now_iso(),
        "capture_nonce": nonce,
        "client_id": "test-manif",
    }
    r = app_client.post("/api/v1/reports", files=files, data=data)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["interaction_type"] == "manifestacao"
    assert body["status"] in ("publicado", "em_moderacao", "descartado")


def test_manifestation_requires_description(app_client, jpeg_bytes):
    files = {"photo": ("c.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "lat": "-23.55", "lon": "-46.63",
        "category": "elogio", "interaction_type": "manifestacao",
        "description": "curto",
        "captured_at": _now_iso(),
    }
    r = app_client.post("/api/v1/reports", files=files, data=data)
    assert r.status_code == 400


def test_manifestations_feed(app_client, jpeg_bytes):
    nonce = app_client.get("/api/v1/capture-nonce").json()["nonce"]
    files = {"photo": ("c.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "lat": "-23.55", "lon": "-46.63", "accuracy_m": "10",
        "category": "sugestao", "interaction_type": "manifestacao",
        "description": "Sugiro instalação de iluminação neste trecho.",
        "captured_at": _now_iso(), "capture_nonce": nonce,
    }
    app_client.post("/api/v1/reports", files=files, data=data)

    r = app_client.get("/api/v1/manifestations.geojson")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"


def test_offline_capture_flag(app_client, jpeg_bytes):
    nonce = app_client.get("/api/v1/capture-nonce").json()["nonce"]
    files = {"photo": ("c.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "lat": "-23.55", "lon": "-46.63", "accuracy_m": "10",
        "category": "buraco", "captured_at": _now_iso(),
        "capture_nonce": nonce, "offline_capture": "true",
    }
    r = app_client.post("/api/v1/reports", files=files, data=data)
    assert r.status_code == 201


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


def test_moderation_requires_auth(app_client):
    r = app_client.get("/api/v1/moderation/queue")
    assert r.status_code == 401


def test_login_and_moderation(app_client):
    login = app_client.post("/api/v1/auth/login", json={
        "username": "test-admin",
        "password": "test-pass",
    })
    assert login.status_code == 200
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = app_client.get("/api/v1/moderation/queue", headers=headers)
    assert r.status_code == 200
    assert "items" in r.json()


def test_login_invalid_credentials(app_client):
    r = app_client.post("/api/v1/auth/login", json={
        "username": "wrong",
        "password": "wrongpass",
    })
    assert r.status_code == 401


def test_auth_context(app_client):
    r = app_client.get("/api/v1/auth/context")
    assert r.status_code == 200
    body = r.json()
    assert body["profile"] == "GESTOR"
    assert body["identifier"]["label"] == "Usuário"
    assert "gestor.silva" in body["identifier"]["placeholder"]
    assert body["password"]["placeholder"] == "Sua senha"


def test_acesso_redirect(app_client):
    r = app_client.get("/moderar", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/acesso"
