"""Testes da simbologia oficial de eventos de tráfego."""
from __future__ import annotations

from backend.services.traffic_symbology import (
    EVENT_ICON_PNG_IDS,
    MARKER_BORDER_COLOR,
    event_icon_format,
    event_icon_static_path,
    traffic_event_symbology_payload,
    traffic_feature_symbology,
)


def test_png_categories_match_funcionalidades():
    assert event_icon_format("acidente") == "png"
    assert event_icon_format("buraco") == "svg"
    assert "acidente" in EVENT_ICON_PNG_IDS
    assert "buraco" not in EVENT_ICON_PNG_IDS


def test_symbology_payload_shape():
    payload = traffic_event_symbology_payload()
    assert payload["marker_shape"] == "diamond"
    assert payload["marker_border_color"] == MARKER_BORDER_COLOR
    assert len(payload["categories"]) == 13
    assert payload["rendering"]["sigla_no_marcador"] is False
    legend = payload["legenda_status"]
    assert legend["titulo"] == "Relação cor / status"
    assert len(legend["mapa_publico"]) == 2
    assert legend["mapa_publico"][0]["status"] == "publicado"
    assert legend["mapa_publico"][0]["symbol_color"] == "#15803d"
    assert legend["por_status"]["resolvido"] == "#7e22ce"


def test_feature_symbology_urls():
    sym = traffic_feature_symbology(
        "buraco",
        "publicado",
        base_url="https://example.com",
    )
    assert sym["icon_url"] == "https://example.com/static/img/icons/buraco.svg"
    assert sym["symbol_color"] == "#15803d"
    assert sym["status_label"] == "Publicado"
