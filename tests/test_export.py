"""Testes de exportação pública de camadas."""
from __future__ import annotations


def test_public_catalog(app_client):
    r = app_client.get("/api/catalog")
    assert r.status_code == 200
    data = r.json()
    assert "event_categories" in data
    assert "manifestation_categories" in data


def test_export_layer_csv_empty(app_client):
    r = app_client.get("/api/export/layer/evento_trafego/buraco?format=csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "ID" in r.text


def test_export_layer_invalid_category(app_client):
    r = app_client.get("/api/export/layer/evento_trafego/invalido_xyz?format=csv")
    assert r.status_code == 404


def test_export_batch_csv_single(app_client):
    r = app_client.post(
        "/api/export/batch",
        json={
            "format": "csv",
            "layers": [{"interaction_type": "evento_trafego", "category_id": "buraco"}],
        },
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "ID" in r.text


def test_export_batch_csv_multi(app_client):
    r = app_client.post(
        "/api/export/batch",
        json={
            "format": "csv",
            "layers": [
                {"interaction_type": "evento_trafego", "category_id": "buraco"},
                {"interaction_type": "manifestacao", "category_id": "elogio"},
            ],
        },
    )
    assert r.status_code == 200
    assert "Camada" in r.text


def test_export_batch_empty_selection(app_client):
    r = app_client.post("/api/export/batch", json={"format": "csv", "layers": []})
    assert r.status_code == 400


def test_export_batch_pdf_zip(app_client):
    body = {
        "format": "pdf",
        "layers": [
            {"interaction_type": "evento_trafego", "category_id": "acidente"},
            {"interaction_type": "evento_trafego", "category_id": "alagamento"},
        ],
    }
    r = app_client.post("/api/export/batch", json=body)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")

    body["format"] = "zip"
    r2 = app_client.post("/api/export/batch", json=body)
    assert r2.status_code == 200
    assert "zip" in r2.headers.get("content-type", "")


def test_moderar_redirects_to_acesso(app_client):
    r = app_client.get("/moderar", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/acesso"
