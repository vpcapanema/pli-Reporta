"""Testes da API pública de compartilhamento (eventos de tráfego aprovados)."""
from __future__ import annotations


def test_public_api_manifest(app_client):
    r = app_client.get("/api/public/")
    assert r.status_code == 200
    data = r.json()
    assert data["interaction_type"] == "evento_trafego"
    assert "eventos-trafego.geojson" in data["endpoints"]["todos_eventos"]
    assert len(data["layers"]) >= 10


def test_public_api_catalog(app_client):
    r = app_client.get("/api/public/catalog")
    assert r.status_code == 200
    data = r.json()
    assert len(data["event_categories"]) >= 10
    assert "manifestacao" not in {t["id"] for t in data.get("interaction_types", [])}


def test_public_api_all_events_geojson(app_client):
    r = app_client.get("/api/public/eventos-trafego.geojson")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert "generated_at" in fc
    for f in fc.get("features", []):
        assert f["properties"]["interaction_type"] == "evento_trafego"
        assert f["properties"]["status"] in ("publicado", "resolvido")


def test_public_api_layer_geojson(app_client):
    r = app_client.get("/api/public/eventos-trafego/buraco.geojson")
    assert r.status_code == 200
    fc = r.json()
    assert fc["metadata"]["category_id"] == "buraco"


def test_public_api_invalid_category(app_client):
    r = app_client.get("/api/public/eventos-trafego/invalida_xyz.geojson")
    assert r.status_code == 404


def test_api_publica_page(app_client):
    r = app_client.get("/api-publica")
    assert r.status_code == 200
    assert "API pública" in r.text
    assert "/api/public/eventos-trafego.geojson" in r.text
