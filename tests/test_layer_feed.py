"""Testes do serviço de feeds por matriz de visibilidade."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.models import Report
from backend.services.geometry_sync import sync_report_geometry
from backend.services.layer_feed import features_for_feed, statuses_for_feed


def _report(**kwargs) -> Report:
    rep = Report(
        id=kwargs.get("id", "01TEST00000000000000000001"),
        category=kwargs.get("category", "buraco"),
        interaction_type=kwargs.get("interaction_type", "evento_trafego"),
        lat=kwargs.get("lat", -22.72),
        lon=kwargs.get("lon", -46.79),
        photo_path="demo/x.jpg",
        photo_hash="abc",
        captured_at=datetime.now(timezone.utc).isoformat(),
        status=kwargs.get("status", "publicado"),
        veracity_score=0.8,
        relevance_score=0.7,
        priority=0.56,
        valid_to=kwargs.get(
            "valid_to",
            (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        ),
    )
    sync_report_geometry(rep)
    return rep


def test_statuses_for_public_feed():
    assert "publicado" in statuses_for_feed("publico")
    assert "resolvido" in statuses_for_feed("publico")
    assert "em_moderacao" not in statuses_for_feed("publico")


def test_gestao_feed_excludes_descartado(db_session):
    db_session.add(_report(status="descartado", id="01TEST00000000000000000002"))
    db_session.add(_report(status="publicado", id="01TEST00000000000000000003"))
    db_session.commit()

    feats = features_for_feed(db_session, mapa="gestao", interaction_type="evento_trafego")
    statuses = {f["properties"]["status"] for f in feats}
    assert "publicado" in statuses
    assert "descartado" not in statuses


def test_public_feed_only_published(db_session):
    db_session.add(_report(status="em_moderacao", id="01TEST00000000000000000004"))
    db_session.add(_report(status="publicado", id="01TEST00000000000000000005"))
    db_session.commit()

    feats = features_for_feed(db_session, mapa="publico", interaction_type="evento_trafego")
    assert all(f["properties"]["visivel_mapa_publico"] for f in feats)
    assert all(f["properties"]["status"] in ("publicado", "resolvido") for f in feats)


def test_expired_valid_to_hidden(db_session):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    db_session.add(_report(status="publicado", valid_to=past, id="01TEST00000000000000000006"))
    db_session.commit()

    feats = features_for_feed(db_session, mapa="publico")
    assert not any(f["properties"]["id"] == "01TEST00000000000000000006" for f in feats)


def test_geometry_sync_sets_point():
    rep = _report(id="01TEST00000000000000000007")
    from backend.config import settings
    if settings.database_url.startswith("sqlite"):
        return
    assert rep.geom_point is not None
    assert rep.geom_polygon is not None
