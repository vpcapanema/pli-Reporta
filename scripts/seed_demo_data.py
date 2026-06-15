"""Popula o banco REAL (PostgreSQL/SQLite do .env) com reportes demo.

Os testes pytest usam SQLite temporário — não aparecem na interface.

Este script chama a API local (fluxo real) e opcionalmente publica pendentes.

Uso:
    python scripts/seed_demo_data.py
    python scripts/seed_demo_data.py --publish-pending
    python scripts/seed_demo_data.py --full-matrix
    python scripts/seed_demo_data.py --base-url http://127.0.0.1:8080

Requer backend rodando (start-app.ps1) e malha/IBGE no .env.

"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

# Coordenadas validadas contra malha DER + mancha IBGE (classify_traffic_scope)


DEMO_EVENTS = [
    {
        "label": "SP-095 — acidente (estadual)",
        "lat": -22.7202531,
        "lon": -46.797326,
        "category": "acidente",
        "description": "Demo: acidente leve na SP-095, faixa da direita.",
    },
    {
        "label": "SP-095 — buraco publicado",
        "lat": -22.7188000,
        "lon": -46.7995000,
        "category": "buraco",
        "description": "Demo: buraco na pista, faixa central.",
    },
    {
        "label": "SP-095 — alagamento (estadual)",
        "lat": -22.7091021,
        "lon": -46.8371192,
        "category": "alagamento",
        "description": "Demo: alagamento parcial após chuva forte.",
    },
    {
        "label": "BR-354 — bloqueio (federal)",
        "lat": -22.4333284,
        "lon": -44.7389918,
        "category": "bloqueio_total",
        "description": "Demo: interdição parcial na BR-354.",
    },
    {
        "label": "SP-095 — lentidão (resolvido via seed)",
        "lat": -22.7155000,
        "lon": -46.8050000,
        "category": "lentidao_corredor",
        "description": "Demo: lentidão no corredor — será marcado resolvido.",
    },
    {
        "label": "Interior — buraco (municipal, só gestão)",
        "lat": -22.50,
        "lon": -47.80,
        "category": "buraco",
        "description": (
            "Demo: buraco em via municipal (não aparece no mapa PLI)."
        ),
    },

]


DEMO_MANIFESTATIONS = [
    {
        "label": "Manifestação — elogio",
        "lat": -22.7140000,
        "lon": -46.8080000,
        "category": "elogio",
        "description": "Demo: elogio à equipe de conservação da SP-095.",
    },
    {
        "label": "Manifestação — sugestão",
        "lat": -22.716946,
        "lon": -46.8103328,
        "category": "sugestao",
        "description": "Demo: sugerir sinalização mais visível na SP-095.",
    },
    {
        "label": "Manifestação — reclamação",
        "lat": -22.7743985,
        "lon": -49.8904415,
        "category": "reclamacao",
        "description": "Demo: reclamação sobre conservação da rodovia.",
    },

]


def _jpeg() -> bytes:
    from PIL import Image
    r = secrets.randbelow(256)
    img = Image.new("RGB", (128, 96), (r, 80, 200 - r % 80))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _post_report(
    client,
    *,
    lat: float,
    lon: float,
    category: str,
    description: str = "",
    manifestacao: bool = False,
) -> dict:
    nonce = client.get("/api/capture-nonce").json()["nonce"]
    files = {
        "photo": (f"seed-{secrets.token_hex(4)}.jpg", _jpeg(), "image/jpeg"),
    }
    data = {
        "lat": str(lat),
        "lon": str(lon),
        "accuracy_m": "8",
        "category": category,
        "magnitude": "normal",
        "captured_at": _now_iso(),
        "capture_nonce": nonce,
        "client_id": f"seed-{secrets.token_hex(6)}",
    }
    if description:
        data["description"] = description
    if manifestacao:
        data["interaction_type"] = "manifestacao"
    r = client.post("/api/reports", files=files, data=data)
    return {
        "status": r.status_code,
        "body": r.json() if r.content else {},
        "text": r.text,
    }


def _publish_pending_direct() -> int:
    """Publica em_moderacao estadual/federal no banco (demo sem login)."""
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from sqlalchemy import select
    from backend.database import SessionLocal, init_db
    from backend.models import AuditLog, Report
    from backend.services.geometry_sync import sync_report_geometry
    from backend.services.road_context import STATUS_REGISTRO_MUNICIPAL
    init_db()
    published = 0
    with SessionLocal() as db:
        rows = db.execute(
            select(Report).where(
                Report.status == "em_moderacao",
                Report.interaction_type == "evento_trafego",
            )
        ).scalars().all()
        for rep in rows:
            if rep.status == STATUS_REGISTRO_MUNICIPAL:
                continue
            rep.status = "publicado"
            sync_report_geometry(rep)
            db.add(AuditLog(
                actor="seed_demo_data",
                action="decide:publicar",
                target_type="report",
                target_id=rep.id,
                payload_json=json.dumps(
                    {"note": "publicado pelo seed de demonstração"},
                    ensure_ascii=False,
                ),
            ))
            published += 1
        db.commit()
    return published


def _apply_matrix_samples() -> dict[str, int]:
    """Ajusta status e geometrias para cobrir a matriz de visibilidade."""
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from sqlalchemy import select
    from backend.database import SessionLocal, init_db
    from backend.models import Report
    from backend.services.geometry_sync import sync_report_geometry
    from backend.services import photos as photo_svc
    init_db()
    counts: dict[str, int] = {}
    valid_to = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with SessionLocal() as db:
        # Um reporte resolvido (lentidão)

        lent = db.execute(
            select(Report).where(
                Report.category == "lentidao_corredor",
                Report.interaction_type == "evento_trafego",
            ).order_by(Report.received_at.desc()).limit(1)
        ).scalar_one_or_none()
        if lent:
            lent.status = "resolvido"
            sync_report_geometry(lent)
            counts["resolvido"] = 1

        # Validado internamente (buraco em SP-095)

        bur = db.execute(
            select(Report).where(
                Report.category == "buraco",
                Report.interaction_type == "evento_trafego",
                Report.road_scope.in_(("estadual", "federal")),
            ).order_by(Report.received_at.desc()).limit(1)
        ).scalar_one_or_none()
        if bur:
            bur.status = "validado"
            sync_report_geometry(bur)
            counts["validado"] = 1

        # Manifestação publicada

        man = db.execute(
            select(Report).where(
                Report.interaction_type == "manifestacao",
                Report.category == "elogio",
            ).limit(1)
        ).scalar_one_or_none()
        if man and man.status != "publicado":
            man.status = "publicado"
            sync_report_geometry(man)
            counts["manifestacao_publicada"] = 1

        # Amostra direta: submetido + expirado (só gestão / histórico)

        existing = db.execute(
            select(Report).where(Report.id.like("SEED%")),
        ).scalars().all()
        for old in existing:
            db.delete(old)
        rel_path, sha = photo_svc.save_photo(_jpeg(), "SEED01")
        sub = Report(
            id="SEED01SUBMETIDO000000001",
            interaction_type="evento_trafego",
            category="sinalizacao_quebrada",
            magnitude="leve",
            description="Demo: placa caída — submetido (só gestão).",
            lat=-22.7120000,
            lon=-46.8120000,
            photo_path=rel_path,
            photo_hash=sha + "a",
            captured_at=_now_iso(),
            status="submetido",
            veracity_score=0.5,
            relevance_score=0.4,
            priority=0.2,
            valid_to=valid_to,
            road_scope="estadual",
            road_label="SP-095",
        )
        sync_report_geometry(sub)
        db.add(sub)
        counts["submetido"] = 1
        rel_path2, sha2 = photo_svc.save_photo(_jpeg(), "SEED02")
        exp = Report(
            id="SEED02EXPIRADO0000000001",
            interaction_type="evento_trafego",
            category="outro",
            magnitude="normal",
            description="Demo: evento expirado (fora dos feeds).",
            lat=-22.7110000,
            lon=-46.8130000,
            photo_path=rel_path2,
            photo_hash=sha2 + "b",
            captured_at=_now_iso(),
            status="expirado",
            veracity_score=0.6,
            relevance_score=0.5,
            priority=0.3,
            valid_to=(
                datetime.now(timezone.utc) - timedelta(days=1)
            ).isoformat(),
            road_scope="estadual",
            road_label="SP-095",
        )
        sync_report_geometry(exp)
        db.add(exp)
        counts["expirado"] = 1
        db.commit()
    return counts


def _print_feed_summary(client) -> None:
    pub_ev = client.get("/api/layers/points/evento_trafego.geojson").json()
    pub_man = client.get("/api/layers/points/manifestacao.geojson").json()
    print("\n--- Mapa público (camadas de pontos) ---")
    print(f"  Eventos visíveis:       {len(pub_ev.get('features', []))}")
    print(f"  Manifestações visíveis: {len(pub_man.get('features', []))}")
    for f in pub_ev.get("features", [])[:5]:
        p = f.get("properties") or {}
        print(f"    · {p.get('category_label')} — {p.get('status')}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Insere reportes demo no banco real via API.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--publish-pending",
        action="store_true",
        help="Publica reportes em_moderacao (estadual/federal) no banco",
    )
    parser.add_argument(
        "--full-matrix",
        action="store_true",
        help=(
            "Aplica amostras para status da matriz "
            "(validado, resolvido, submetido, expirado)"
        ),
    )
    args = parser.parse_args()
    try:
        import httpx
    except ImportError:
        print("Instale httpx: pip install httpx", file=sys.stderr)
        return 2
    client = httpx.Client(base_url=args.base_url, timeout=60.0)
    print(f"\n=== Seed demo @ {args.base_url} ===\n")
    try:
        health = client.get("/healthz")
    except httpx.ConnectError:
        print("ERRO: backend offline. Rode .vscode/start-app.ps1 primeiro.")
        return 1
    if health.status_code != 200:
        print(f"ERRO: healthz retornou {health.status_code}")
        return 1
    created = 0
    skipped = 0
    for item in DEMO_EVENTS:
        r = _post_report(
            client,
            lat=item["lat"],
            lon=item["lon"],
            category=item["category"],
            description=item.get("description", ""),
        )
        if r["status"] == 201:
            body = r["body"]
            print(f"  OK   {item['label']}")
            print(
                f"       id={body.get('id')} status={body.get('status')} "
                f"scope={body.get('road_scope')}"
            )
            created += 1
        elif r["status"] == 422:
            detail = r["body"].get("detail", r["text"][:120])
            print(f"  422  {item['label']} — {detail}")
            skipped += 1
        else:
            print(
                f"  ERRO {item['label']} — HTTP {r['status']}: "
                f"{r['text'][:200]}"
            )
            skipped += 1
    for item in DEMO_MANIFESTATIONS:
        r = _post_report(
            client,
            lat=item["lat"],
            lon=item["lon"],
            category=item["category"],
            description=item.get("description", ""),
            manifestacao=True,
        )
        if r["status"] == 201:
            body = r["body"]
            print(
                f"  OK   {item['label']} — id={body.get('id')} "
                f"status={body.get('status')}"
            )
            created += 1
        else:
            print(
                f"  ERRO {item['label']} — HTTP {r['status']}: "
                f"{r['text'][:200]}"
            )
            skipped += 1
    if args.publish_pending:
        n = _publish_pending_direct()
        print(
            f"\n  Publicados (demo): {n} reporte(s) "
            "em_moderacao -> publicado"
        )
    if args.full_matrix:
        counts = _apply_matrix_samples()
        print(f"\n  Matriz de exemplos: {counts}")
    _print_feed_summary(client)
    print(f"\n  Criados nesta execução: {created} | Falhas/422: {skipped}")
    print(
        "  Dica: zoom nas rodovias SP-095 / BR-354. "
        "Gestão mostra mais status que o mapa público.\n"
    )
    return 0 if created else 1


if __name__ == "__main__":
    raise SystemExit(main())
