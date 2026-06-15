"""Páginas públicas: HTML servido, scripts referenciados e JS válido."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

PUBLIC_PAGES = [
    {
        "path": "/",
        "html": "index.html",
        "script": "/static/js/app.js",
        "buttons": [
            "branch-evento",
            "branch-manifestacao",
            "btn-step1-evento",
            "btn-step1-manifestacao",
            "btn-submit",
        ],
        "js_markers": ["async function openCameraStep", "function bindUI", "DOMContentLoaded"],
    },
    {
        "path": "/mapa",
        "html": "viewer.html",
        "script": "/static/js/viewer.js",
        "buttons": ["layer-events", "layer-manif"],
        "js_markers": ["layer-events", "layer-manif", "popup-resolver"],
    },
    {
        "path": "/acesso",
        "html": "acesso.html",
        "script": "/static/js/access-login.js",
        "buttons": ["login-toggle-pw"],
        "js_markers": ["login-form", "bindPasswordToggle", "DOMContentLoaded"],
    },
]

JS_CHAIN = [
    "frontend/js/app.js",
    "frontend/js/viewer.js",
    "frontend/js/access-login.js",
    "frontend/js/api.js",
    "frontend/js/db.js",
    "frontend/js/camera.js",
    "frontend/js/map-pick.js",
    "frontend/js/map-style.js",
]


def _node_check(rel_path: str) -> None:
    abs_path = ROOT / rel_path
    proc = subprocess.run(
        ["node", "--check", str(abs_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_public_pages_served(app_client):
    for page in PUBLIC_PAGES:
        r = app_client.get(page["path"])
        assert r.status_code == 200, page["path"]
        html = r.text
        assert page["script"] in html, page["path"]
        for btn_id in page["buttons"]:
            assert f'id="{btn_id}"' in html, f'{page["path"]} missing #{btn_id}'


def test_public_page_scripts_valid(app_client):
    seen: set[str] = set()
    for page in PUBLIC_PAGES:
        if page["script"] in seen:
            continue
        seen.add(page["script"])
        r = app_client.get(page["script"])
        assert r.status_code == 200, page["script"]
        for marker in page["js_markers"]:
            assert marker in r.text, f'{page["script"]} missing {marker}'


def test_public_js_syntax():
    for rel in JS_CHAIN:
        _node_check(rel)


def test_app_js_no_orphan_camera_code(app_client):
    """Regressão: corpo de openCameraStep não pode ficar solto após togglePhotoOption."""
    js = app_client.get("/static/js/app.js").text
    assert "async function openCameraStep" in js
    assert "}\n  hideAllSteps();" not in js
