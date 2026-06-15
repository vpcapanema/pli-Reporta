"""Testes da API pública de compartilhamento (eventos de tráfego aprovados)."""
from __future__ import annotations


def test_public_api_manifest(app_client):
    r = app_client.get("/api/public/")
    assert r.status_code == 200
    data = r.json()
    assert data["interaction_type"] == "evento_trafego"
    assert "eventos-trafego.geojson" in data["endpoints"]["todos_eventos"]
    assert len(data["layers"]) >= 10
    sym = data["simbologia"]
    assert sym["marker_shape"] == "diamond"
    assert sym["marker_border_color"] == "#003b5a"
    assert sym["legenda_status"]["mapa_publico"][0]["status"] == "publicado"
    assert sym["categories"][0]["icon_url"].endswith((".png", ".svg"))
    assert data["layers"][0]["icon_url"] == sym["categories"][0]["icon_url"]


def test_public_api_catalog(app_client):
    r = app_client.get("/api/public/catalog")
    assert r.status_code == 200
    data = r.json()
    assert len(data["event_categories"]) >= 10
    assert data["event_categories"][0]["icon_path"].startswith("/static/img/icons/")
    assert "simbologia" in data
    assert "manifestacao" not in {t["id"] for t in data.get("interaction_types", [])}


def test_public_api_all_events_geojson(app_client):
    r = app_client.get("/api/public/eventos-trafego.geojson")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert "generated_at" in fc
    assert fc["metadata"]["simbologia"]["marker_shape"] == "diamond"
    for f in fc.get("features", []):
        assert f["properties"]["interaction_type"] == "evento_trafego"
        assert f["properties"]["status"] in ("publicado", "resolvido")
        assert f["properties"]["marker_shape"] == "diamond"
        assert f["properties"]["marker_border_color"] == "#003b5a"
        assert f["properties"]["icon_url"].startswith("http")
        assert f["properties"]["symbol_color"].startswith("#")
        assert f["properties"]["status_label"] in ("Publicado", "Resolvido")


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
    assert "api-status-legend-body" in r.text
    assert "Relação cor / status" in r.text
