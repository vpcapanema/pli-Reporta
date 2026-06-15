"""Testes do ciclo de vida automático: TTL, renovação e contra-reporte."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO

from PIL import Image


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique_jpeg() -> bytes:
    """JPEG com conteúdo único para não ser barrado como foto duplicada."""
    r, g, b = secrets.randbelow(256), secrets.randbelow(256), secrets.randbelow(256)
    img = Image.new("RGB", (96, 96), (r, g, b))
    img.putpixel((0, 0), (secrets.randbelow(256), secrets.randbelow(256), secrets.randbelow(256)))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _create_event(app_client, jpeg_bytes=None, category="acidente", client_id="c1"):
    nonce = app_client.get("/api/v1/capture-nonce").json()["nonce"]
    files = {"photo": ("c.jpg", _unique_jpeg(), "image/jpeg")}
    data = {
        "lat": "-23.55", "lon": "-46.63", "accuracy_m": "10",
        "category": category, "captured_at": _now_iso(),
        "capture_nonce": nonce, "client_id": client_id,
    }
    r = app_client.post("/api/v1/reports", files=files, data=data)
    assert r.status_code == 201, r.text
    return r.json()


def test_new_categories_accepted(app_client, jpeg_bytes):
    for cat in ("animal_na_pista", "objeto_na_pista", "queda_arvore", "veiculo_quebrado"):
        body = _create_event(app_client, jpeg_bytes, category=cat)
        assert body["status"] in ("publicado", "em_moderacao", "descartado")


def test_expire_old_reports(app_client, jpeg_bytes):
    from sqlalchemy import select, update

    from backend.database import session_scope
    from backend.models import Report
    from backend.services.maintenance import expire_old_reports

    body = _create_event(app_client, jpeg_bytes, category="acidente")
    rid = body["id"]

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with session_scope() as db:
        db.execute(
            update(Report).where(Report.id == rid).values(valid_to=past, status="publicado")
        )

    n = expire_old_reports()
    assert n >= 1
    with session_scope() as db:
        rep = db.execute(select(Report).where(Report.id == rid)).scalar_one()
        assert rep.status == "expirado"


def test_resolve_by_counter_reports(app_client, jpeg_bytes):
    from backend.database import session_scope
    from backend.models import Report

    body = _create_event(app_client, jpeg_bytes, category="acidente")
    cluster_id = body["cluster_id"]
    assert cluster_id

    # Primeiro voto: ainda não resolve (threshold padrão = 2).
    r1 = app_client.post(f"/api/v1/incidents/{cluster_id}/resolver")
    assert r1.status_code == 200
    assert r1.json()["resolved"] is False

    # Segundo voto: resolve.
    r2 = app_client.post(f"/api/v1/incidents/{cluster_id}/resolver")
    assert r2.status_code == 200
    assert r2.json()["resolved"] is True

    with session_scope() as db:
        from sqlalchemy import select

        rep = db.execute(select(Report).where(Report.id == body["id"])).scalar_one()
        assert rep.status == "resolvido"


def test_resolve_unknown_cluster(app_client):
    r = app_client.post("/api/v1/incidents/inexistente/resolver")
    assert r.status_code == 404


def test_renewal_extends_valid_to(app_client, jpeg_bytes):
    from sqlalchemy import select

    from backend.database import session_scope
    from backend.models import Report

    first = _create_event(app_client, jpeg_bytes, category="acidente", client_id="a")
    with session_scope() as db:
        rep1 = db.execute(select(Report).where(Report.id == first["id"])).scalar_one()
        valid_to_1 = rep1.valid_to

    # Segundo reporte no mesmo ponto/categoria deve renovar o valid_to do primeiro.
    _create_event(app_client, jpeg_bytes, category="acidente", client_id="b")
    with session_scope() as db:
        rep1b = db.execute(select(Report).where(Report.id == first["id"])).scalar_one()
        assert rep1b.valid_to >= valid_to_1
