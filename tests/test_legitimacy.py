"""Testes unitários do score de legitimidade."""
from backend.services.legitimacy import compute_legitimacy


def test_legitimacy_short_text():
    r = compute_legitimacy(veracity=0.9, description="ok")
    assert r.score < 0.5


def test_legitimacy_good_text():
    r = compute_legitimacy(
        veracity=0.8,
        description="A sinalização horizontal está muito boa neste trecho da rodovia.",
    )
    assert r.score >= 0.6
