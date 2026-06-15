"""Verifica se /gestao/aprovador preenche todos os parâmetros (Playwright).

Requer: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8080"


def main() -> int:
    sys.path.insert(0, str(ROOT))

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright não instalado. Rode:\n"
            "  pip install playwright\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        return 2

    from backend.services.auth import ModeratorSession, issue_session_token

    def session_storage() -> str:
        token = issue_session_token(
            ModeratorSession(user_id="verify", username="verify-bot", tipo_usuario="GESTOR"),
        )
        return json.dumps({
            "token": token,
            "username": "verify-bot",
            "expiresAt": 9_999_999_999_999,
        })

    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR:", e))
        page.on("console", lambda m: print(f"console.{m.type}:", m.text) if m.type == "error" else None)
        page.goto(f"{BASE}/acesso", wait_until="domcontentloaded")
        page.evaluate(
            "(data) => localStorage.setItem('pli-reporta-session', data)",
            session_storage(),
        )
        page.goto(f"{BASE}/gestao/aprovador", wait_until="networkidle")

        page.wait_for_selector("#tbody-signals tr", timeout=10_000)
        page.wait_for_selector("#tbody-eventos tr", timeout=10_000)
        page.wait_for_selector("#tbody-highway tr", timeout=10_000)

        checks = {
            "#g-event-pub": "70",
            "#g-event-disc": "30",
            "#g-manif-pub": "75",
            "#g-manif-disc": "40",
        }
        for sel, expected in checks.items():
            val = page.input_value(sel)
            if val != expected:
                errors.append(f"{sel}={val!r} (esperado {expected})")

        for lbl in ("#lbl-event-pub", "#lbl-event-disc", "#lbl-manif-pub", "#lbl-manif-disc", "#lbl-weight-total"):
            txt = page.inner_text(lbl).strip()
            if not txt:
                errors.append(f"{lbl} vazio")

        counts = page.evaluate(
            """() => ({
              signals: document.querySelectorAll('#tbody-signals tr').length,
              eventos: document.querySelectorAll('#tbody-eventos tr').length,
              highway: document.querySelectorAll('#tbody-highway tr').length,
              manif: document.querySelectorAll('#tbody-manif tr').length,
              fixed: document.querySelectorAll('#relevance-fixed-params article').length,
              emptyInputs: Array.from(document.querySelectorAll('.policy-num-input')).filter(
                el => !String(el.value).trim()
              ).length,
            })""",
        )
        if counts["signals"] != 7:
            errors.append(f"tbody-signals: {counts['signals']} linhas (esperado 7)")
        if counts["eventos"] != 13:
            errors.append(f"tbody-eventos: {counts['eventos']} linhas (esperado 13)")
        if counts["highway"] != 14:
            errors.append(f"tbody-highway: {counts['highway']} linhas (esperado 14)")
        if counts["manif"] != 3:
            errors.append(f"tbody-manif: {counts['manif']} linhas (esperado 3)")
        if counts["fixed"] != 4:
            errors.append(f"relevance-fixed: {counts['fixed']} cards (esperado 4)")
        if counts["emptyInputs"] > 0:
            errors.append(f"{counts['emptyInputs']} input(s) .policy-num-input vazio(s)")

        err_msg = page.locator("#policy-save-msg").inner_text().strip()
        if "Não foi possível carregar" in err_msg:
            errors.append(f"fetch policy falhou: {err_msg}")

        debug = page.evaluate(
            """() => ({
              gpub: document.getElementById('g-event-pub')?.value,
              firstPeso: document.querySelector('#tbody-signals [data-field=peso]')?.value,
              firstSev: document.querySelector('#tbody-eventos [data-field=severidade_base]')?.value,
              msg: document.getElementById('policy-save-msg')?.textContent?.trim(),
            })""",
        )
        print("debug:", debug)

        browser.close()

    if errors:
        print("[FALHA] Aprovador com parâmetros em branco ou incompletos:")
        for e in errors:
            print(" -", e)
        return 1

    print("[OK] Todos os parâmetros preenchidos (7 sinais, 13 eventos, 14 vias, 3 manif).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
