"""Persistência da mídia. Salva original sem EXIF de localização para publicação."""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from ..config import settings


def save_photo(image_bytes: bytes, report_id: str) -> tuple[str, str]:
    """Devolve (caminho relativo, sha256). Recompacta para JPEG sem metadados."""
    sha = hashlib.sha256(image_bytes).hexdigest()
    sub = sha[:2]
    target_dir = settings.photo_dir / sub
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{report_id}.jpg"

    img = Image.open(BytesIO(image_bytes))
    img = img.convert("RGB")
    # Limita lado maior para 1600 px — economiza disco e CDN.
    max_side = 1600
    if max(img.size) > max_side:
        ratio = max_side / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    img.save(target, format="JPEG", quality=82, optimize=True)

    rel = str(target.relative_to(settings.photo_dir))
    return rel, sha


def public_url_for(rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    rel_url = rel_path.replace("\\", "/")
    return f"{settings.public_base_url.rstrip('/')}/media/{rel_url}"


def absolute_path(rel_path: str) -> Path:
    return settings.photo_dir / rel_path
