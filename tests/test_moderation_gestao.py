"""Testes da API de gestão e política de moderação."""
from __future__ import annotations


def _login(app_client):
    r = app_client.post("/api/auth/login", json={
        "username": "test-admin",
        "password": "test-pass",
    })
    assert r.status_code == 200
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_moderation_catalog(app_client):
    headers = _login(app_client)
    r = app_client.get("/api/moderation/catalog", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "event_categories" in body
    assert "statuses" in body


def test_moderation_stats(app_client):
    headers = _login(app_client)
    r = app_client.get("/api/moderation/stats", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "fila" in body
    assert "total" in body


def test_moderation_policy_get_and_patch(app_client):
    headers = _login(app_client)
    r = app_client.get("/api/moderation/policy", headers=headers)
    assert r.status_code == 200
    policy = r.json()
    assert policy["preset"] in ("cauteloso", "equilibrado", "agil")
    assert "eventos" in policy
    assert "manifestacoes" in policy

    patch = app_client.patch(
        "/api/moderation/policy",
        headers=headers,
        json={"preset": "cauteloso"},
    )
    assert patch.status_code == 200
    assert patch.json()["preset"] == "cauteloso"


def test_moderation_policy_simulate(app_client):
    headers = _login(app_client)
    r = app_client.post("/api/moderation/policy/simulate?days=7", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "total" in body
    assert "sua_fila" in body


def test_moderation_reports_and_geojson(app_client, jpeg_bytes):
    from datetime import datetime, timezone

    headers = _login(app_client)
    nonce = app_client.get("/api/capture-nonce").json()["nonce"]
    files = {"photo": ("c.jpg", jpeg_bytes, "image/jpeg")}
    data = {
        "lat": "-23.55", "lon": "-46.63", "accuracy_m": "10",
        "category": "buraco", "captured_at": datetime.now(timezone.utc).isoformat(),
        "capture_nonce": nonce,
    }
    app_client.post("/api/reports", files=files, data=data)

    r = app_client.get("/api/moderation/reports", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] >= 1

    geo = app_client.get("/api/moderation/reports.geojson", headers=headers)
    assert geo.status_code == 200
    assert geo.json()["type"] == "FeatureCollection"


def test_gestao_routes_served(app_client):
    for path in ("/gestao", "/gestao/eventos", "/gestao/manifestacoes", "/gestao/aprovador", "/gestao/funcionalidades"):
        r = app_client.get(path)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
