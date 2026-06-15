"""Uvicorn de desenvolvimento — reload estável no Windows.

Recarrega só alterações em backend/**/*.py. Arquivos estáticos (frontend/)
são servidos direto pelo FastAPI — basta Ctrl+F5 no navegador, sem reiniciar
o uvicorn (evita CancelledError ruidoso ao salvar JS/CSS).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 8080


def _ensure_project_on_path() -> None:
    """Garante que subprocessos do --reload encontrem o pacote backend."""
    root = str(ROOT)
    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    prev = os.environ.get("PYTHONPATH", "")
    if root not in prev.split(os.pathsep):
        os.environ["PYTHONPATH"] = root + (os.pathsep + prev if prev else "")


def main() -> int:
    _ensure_project_on_path()

    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Porta inválida: {sys.argv[1]!r}", file=sys.stderr)
            return 2

    # No Windows o subprocess do --reload costuma subir outro interpretador Python
    # (fora do venv) e ficar preso em codigo antigo — desliga reload aqui.
    use_reload = sys.platform != "win32"

    run_kwargs: dict = {
        "host": "127.0.0.1",
        "port": port,
        "log_level": "info",
    }
    if use_reload:
        run_kwargs.update(
            reload=True,
            reload_delay=1.0,
            reload_dirs=[str(ROOT / "backend")],
            reload_includes=["**/*.py"],
            reload_excludes=[
                "**/__pycache__/**",
                "**/*.pyc",
                "**/.pytest_cache/**",
            ],
        )

    uvicorn.run("backend.main:app", **run_kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
