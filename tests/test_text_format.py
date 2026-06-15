"""Testes de formatação de texto em português."""
from __future__ import annotations

from backend.services.text_format import format_portuguese_text


def test_normalize_whitespace_and_capitalization():
    raw = "  o onibus   nao parou.no ponto.  segunda frase"
    out = format_portuguese_text(raw, use_languagetool=False)
    assert out.startswith("O onibus")
    assert ". " in out or ". N" in out


def test_empty_text_unchanged():
    assert format_portuguese_text("", use_languagetool=False) == ""
    assert format_portuguese_text("   ", use_languagetool=False) == "   "


def test_format_text_endpoint(app_client):
    res = app_client.post("/api/format-text", json={"text": "  elogio ao atendimento rapido.  "})
    assert res.status_code == 200
    body = res.json()
    assert "formatted" in body
    assert body["formatted"].startswith("Elogio")
