"""Teste manual do fluxo de reporte contra servidor local (http://127.0.0.1:8080).

Uso:
    python scripts/test_report_flow.py

Requer backend rodando e, para escopo completo, malha/IBGE no .env.
Sem malha configurada, só roda cenários genéricos (nonce + report básico).
"""
from __future__ import annotations

import secrets
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _jpeg() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (64, 64), (secrets.randbelow(256),) * 3)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def main() -> int:
    try:
        import httpx
    except ImportError:
        print("pip install httpx", file=sys.stderr)
        return 2

    base = "http://127.0.0.1:8080"
    client = httpx.Client(base_url=base, timeout=30.0)
    ok = 0
    fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  OK  {name}")
        else:
            fail += 1
            print(f"  FALHA  {name}" + (f" — {detail}" if detail else ""))

    print(f"\n=== Fluxo de reporte @ {base} ===\n")

    # Health
    try:
        r = client.get("/healthz")
        check("healthz", r.status_code == 200, r.text[:120])
    except httpx.ConnectError:
        print("  ERRO  servidor offline — rode start-app.ps1 primeiro")
        return 1

    # Nonce
    r = client.get("/api/capture-nonce")
    check("capture-nonce", r.status_code == 200)
    nonce = r.json().get("nonce", "")

    # Report genérico (sem gate se malha desligada)
    files = {"photo": ("t.jpg", _jpeg(), "image/jpeg")}
    data = {
        "lat": "-23.55",
        "lon": "-46.63",
        "accuracy_m": "12",
        "category": "buraco",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "capture_nonce": nonce,
        "client_id": "manual-flow",
    }
    r = client.post("/api/reports", files=files, data=data)
    check(
        "POST /reports (evento)",
        r.status_code in (201, 422),
        f"status={r.status_code} body={r.text[:200]}",
    )
    if r.status_code == 201:
        body = r.json()
        print(f"       -> status={body.get('status')} scope={body.get('road_scope')}")
        print(f"       -> V={body.get('veracity_score')} R={body.get('relevance_score')}")

    # Manifestação
    data["interaction_type"] = "manifestacao"
    data["category"] = "sugestao"
    data["description"] = "Teste manual de fluxo com texto suficiente para validar."
    data["capture_nonce"] = client.get("/api/capture-nonce").json()["nonce"]
    files = {"photo": ("m.jpg", _jpeg(), "image/jpeg")}
    r = client.post("/api/reports", files=files, data=data)
    check("POST /reports (manifestação)", r.status_code == 201, r.text[:200])

    # Login gestor + fila
    login = client.post("/api/auth/login", json={
        "username": "test-admin",
        "password": "test-pass",
    })
    if login.status_code == 401:
        check("login gestor (SIGMA/local)", False, "credenciais locais indisponíveis — use sessão real")
    else:
        check("login gestor", login.status_code == 200)
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        q = client.get("/api/moderation/queue", headers=headers)
        check("fila moderação", q.status_code == 200, q.text[:120])
        if q.status_code == 200:
            print(f"       -> fila={q.json().get('queue_size', 0)} itens")

        stats = client.get("/api/moderation/stats", headers=headers)
        check("stats gestão", stats.status_code == 200)
        if stats.status_code == 200:
            s = stats.json()
            print(f"       -> fila={s.get('fila')} municipal={s.get('registros_municipais')}")

    # Feed público
    feed = client.get("/api/incidents.geojson")
    check("feed incidents.geojson", feed.status_code == 200)
    if feed.status_code == 200:
        n = len(feed.json().get("features", []))
        print(f"       -> {n} evento(s) publico(s) no mapa")

    print(f"\n=== Resultado: {ok} OK, {fail} falha(s) ===\n")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
