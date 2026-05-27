"""Gera ícones placeholder para a PWA (192 e 512). Roda uma vez na instalação."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "frontend" / "icons"


def make_icon(size: int, path: Path) -> None:
    img = Image.new("RGBA", (size, size), (200, 16, 46, 255))  # vermelho institucional GOV-SP
    draw = ImageDraw.Draw(img)
    # quadrado preto para a marca
    pad = size // 8
    draw.rounded_rectangle(
        (pad, pad, size - pad, size - pad),
        radius=size // 16,
        fill=(31, 31, 31, 255),
    )
    # marcador (gota) simplificado em branco
    cx, cy = size // 2, size // 2
    r = size // 5
    draw.ellipse((cx - r, cy - r - r // 2, cx + r, cy + r // 2), fill=(255, 255, 255, 255))
    draw.polygon(
        [(cx - r // 2, cy + r // 3), (cx + r // 2, cy + r // 3), (cx, cy + r)],
        fill=(255, 255, 255, 255),
    )
    # ponto central vermelho
    draw.ellipse(
        (cx - r // 4, cy - r // 4 - r // 4, cx + r // 4, cy + r // 4 - r // 4),
        fill=(200, 16, 46, 255),
    )
    img.save(path, format="PNG", optimize=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_icon(192, OUT / "icon-192.png")
    make_icon(512, OUT / "icon-512.png")
    print(f"Ícones gerados em {OUT}")


if __name__ == "__main__":
    main()
