"""Score de Legitimidade L para manifestações cidadãs.

L = V · L_conteudo · L_escopo (escopo neutro até malha DER integrada).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

FORBIDDEN_WORDS = frozenset({"spam", "teste123"})

MIN_TEXT_LEN = 15


@dataclass
class LegitimacyResult:
    score: float
    content_factor: float
    scope_factor: float
    explanation: list[str]

    def explain(self) -> list[str]:
        return self.explanation + [
            f"L = V·L_conteudo·L_escopo = {self.score:.2f}",
        ]


def _content_factor(description: str | None) -> tuple[float, str]:
    text = (description or "").strip()
    if len(text) < MIN_TEXT_LEN:
        return 0.2, f"texto curto ({len(text)} chars, mín. {MIN_TEXT_LEN})"
    lower = text.lower()
    if any(w in lower for w in FORBIDDEN_WORDS):
        return 0.0, "conteúdo bloqueado"
    # Especificidade: palavras úteis além de stopwords curtas.
    tokens = [t for t in re.split(r"\W+", lower) if len(t) > 2]
    if len(tokens) < 3:
        return 0.5, "texto genérico"
    if len(text) >= 40:
        return 1.0, "texto descritivo"
    return 0.75, "texto adequado"


def compute_legitimacy(
    *,
    veracity: float,
    description: str | None,
    scope_ok: bool = True,
) -> LegitimacyResult:
    content, content_detail = _content_factor(description)
    scope = 1.0 if scope_ok else 0.0
    score = veracity * content * scope
    return LegitimacyResult(
        score=score,
        content_factor=content,
        scope_factor=scope,
        explanation=[
            f"L_conteudo={content:.2f} — {content_detail}",
            f"L_escopo={scope:.2f}",
        ],
    )
