"""Especificação e helpers da API pública de compartilhamento (eventos de tráfego)."""
from __future__ import annotations

from typing import Any

from .report_catalog import EVENT_CATEGORIES, STATUS_META, status_visibility_matrix

# Status incluídos na API pública de compartilhamento (= export_publico na matriz).
PUBLIC_SHARE_STATUS_KEY = "export_publico"

PUBLIC_EVENT_STATUSES = tuple(
    sid for sid, meta in STATUS_META.items() if meta.get(PUBLIC_SHARE_STATUS_KEY)
)


def public_share_status_labels() -> list[dict[str, str]]:
    return [
        {"id": sid, "label": STATUS_META[sid]["label"]}
        for sid in PUBLIC_EVENT_STATUSES
    ]


def api_manifest(*, base_url: str) -> dict[str, Any]:
    """Manifesto JSON servido em GET /api/public/."""
    base = base_url.rstrip("/")
    prefix = f"{base}/api/public"
    layers = [
        {
            "category_id": c["id"],
            "label": c["label"],
            "sigla": c["sigla"],
            "geojson_url": f"{prefix}/eventos-trafego/{c['id']}.geojson",
        }
        for c in EVENT_CATEGORIES
    ]
    return {
        "name": "PLI Reporta — API pública",
        "version": "1",
        "description": (
            "Acesso aberto a eventos de tráfego aprovados para publicação "
            "(GeoJSON). Não requer autenticação."
        ),
        "interaction_type": "evento_trafego",
        "statuses_incluidos": public_share_status_labels(),
        "regras": {
            "valid_to": "Registros com valid_to no passado são omitidos.",
            "manifestacoes": "Manifestações cidadãs não fazem parte desta API.",
            "moderacao": "Reportes em análise ou arquivados não são expostos.",
        },
        "endpoints": {
            "manifesto": f"{prefix}/",
            "catalogo": f"{prefix}/catalog",
            "todos_eventos": f"{prefix}/eventos-trafego.geojson",
            "camada_por_categoria": f"{prefix}/eventos-trafego/{{category_id}}.geojson",
        },
        "layers": layers,
        "parametros_geojson": {
            "bbox": "minLon,minLat,maxLon,maxLat — filtro espacial opcional",
            "since": "ISO 8601 — capturados a partir desta data",
            "min_priority": "0.0–1.0 — prioridade mínima (padrão 0)",
        },
        "documentacao_html": f"{base}/api-publica",
        "status_visibility_matrix": status_visibility_matrix(),
    }
