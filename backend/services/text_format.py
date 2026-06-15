"""Formatação de texto em português brasileiro (norma culta) para manifestações."""
from __future__ import annotations

import re

import httpx

_LT_URL = "https://api.languagetool.org/v2/check"
_MAX_LEN = 500


def _normalize_whitespace(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])([^\s\d])", r"\1 \2", text)
    return text


def _capitalize_sentences(text: str) -> str:
    if not text:
        return text

    def _upper_after_boundary(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2).upper()

    text = re.sub(r"^(\s*)(\w)", _upper_after_boundary, text)
    text = re.sub(r"([.!?]\s+)(\w)", _upper_after_boundary, text)
    return text


def _apply_languagetool(text: str) -> str:
    with httpx.Client(timeout=8.0) as client:
        response = client.post(
            _LT_URL,
            data={"text": text, "language": "pt-BR"},
        )
        response.raise_for_status()
        payload = response.json()

    matches = sorted(payload.get("matches", []), key=lambda m: m["offset"], reverse=True)
    for match in matches:
        replacements = match.get("replacements") or []
        if not replacements:
            continue
        start = int(match["offset"])
        end = start + int(match["length"])
        text = text[:start] + replacements[0]["value"] + text[end:]
    return text


def format_portuguese_text(text: str, *, use_languagetool: bool = True) -> str:
    """Normaliza espaços, pontuação, capitalização e corrige ortografia/gramática."""
    if not text or not text.strip():
        return text

    cleaned = _normalize_whitespace(text[:_MAX_LEN])
    cleaned = _capitalize_sentences(cleaned)

    if use_languagetool:
        try:
            cleaned = _apply_languagetool(cleaned)
            cleaned = _normalize_whitespace(cleaned)
            cleaned = _capitalize_sentences(cleaned)
        except Exception:
            pass

    return cleaned.strip()
