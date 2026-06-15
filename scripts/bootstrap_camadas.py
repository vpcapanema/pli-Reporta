#!/usr/bin/env python3
"""Cria a árvore data/camadas-do-sistema/ com FeatureCollections vazias."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data" / "camadas-do-sistema"

from backend.services.report_catalog import EVENT_CATEGORIES, MANIF_CATEGORIES  # noqa: E402


def layer_filename(interaction_type: str, category_id: str) -> str:
    return f"{interaction_type}__{category_id}.geojson"


def empty_collection(interaction_type: str, category_id: str) -> dict:
    return {
        "type": "FeatureCollection",
        "name": layer_filename(interaction_type, category_id).replace(".geojson", ""),
        "metadata": {
            "interaction_type": interaction_type,
            "category_id": category_id,
            "geometry_role": None,
        },
        "features": [],
    }


def main() -> None:
    layers: list[tuple[str, str]] = [
        ("evento_trafego", c["id"]) for c in EVENT_CATEGORIES
    ] + [
        ("manifestacao", c["id"]) for c in MANIF_CATEGORIES
    ]

    for sub in ("pontos", "poligonos"):
        dest = BASE / sub
        dest.mkdir(parents=True, exist_ok=True)
        for itype, cat in layers:
            path = dest / layer_filename(itype, cat)
            data = empty_collection(itype, cat)
            data["metadata"]["geometry_role"] = sub[:-1]  # ponto / poligono
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"  {path.relative_to(ROOT)}")

    readme = BASE / "README.md"
    readme.write_text(
        """# Camadas do sistema

Projeção GeoJSON materializada a partir de `reports`.

- `pontos/` — um arquivo por camada; geometria `Point`; **servido nos mapas**.
- `poligonos/` — mesmo `id` e atributos; geometria de área de impacto.

Documentação: [docs/ARQUITETURA_CAMADAS.md](../docs/ARQUITETURA_CAMADAS.md)

Regenerar arquivos vazios (não sobrescreve features existentes se já houver dados — use com cuidado):

```bash
python scripts/bootstrap_camadas.py
```
""",
        encoding="utf-8",
    )
    print(f"\n{len(layers) * 2} arquivos em {BASE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
