"""Configura ambiente de teste isolado.

As variáveis de ambiente DEVEM ser definidas antes de qualquer import de
`backend.*`, porque `backend.config.settings` é instanciado no import do módulo.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# --- top-level: roda na coleção do pytest, antes de importar o app -------- #
_TMP = Path(tempfile.mkdtemp(prefix="pli_reporta_test_"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(_TMP / 'test.db').as_posix()}")
os.environ.setdefault("PHOTO_STORAGE_DIR", str(_TMP / "photos"))
os.environ.setdefault("SECRET_KEY", "test-secret-very-long-enough-string")
os.environ.setdefault("AUTO_PUBLISH_THRESHOLD", "0.70")
os.environ.setdefault("AUTO_DISCARD_THRESHOLD", "0.30")
os.environ["SIGMA_POSTGRES_PASSWORD"] = ""
os.environ["SIGMA_POSTGRES_HOST"] = ""
os.environ["SIGMA_API_BASE_URL"] = ""
os.environ.setdefault("MODERATOR_USERNAME", "test-admin")
os.environ.setdefault("MODERATOR_PASSWORD", "test-pass")
Path(os.environ["PHOTO_STORAGE_DIR"]).mkdir(parents=True, exist_ok=True)

import pytest  # noqa: E402


@pytest.fixture
def app_client():
    """Importa app já com env de teste e devolve TestClient."""
    from fastapi.testclient import TestClient

    from backend.database import init_db
    from backend.main import app

    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def jpeg_bytes():
    """Pequeno JPEG válido sem EXIF."""
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (320, 240), (120, 200, 120))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()
