"""Simbologia oficial de eventos de tráfego (espelha gestao-markers.js / Funcionalidades)."""
from __future__ import annotations

from typing import Any

from .report_catalog import EVENT_CATEGORIES, STATUS_META

# Categorias com ícone PNG (Flaticon); demais usam SVG (Font Awesome 6).
EVENT_ICON_PNG_IDS: frozenset[str] = frozenset({
    "acidente",
    "alagamento",
    "bloqueio_total",
    "lentidao_corredor",
    "obra_grande",
    "queda_arvore",
    "sinalizacao_quebrada",
})

MARKER_BORDER_COLOR = "#003b5a"
TRAFFIC_MARKER_SHAPE = "diamond"

# Mesma ordem da legenda do mapa público (frontend/js/viewer.js).
PUBLIC_MAP_LEGEND_STATUS_ORDER: tuple[str, ...] = ("publicado", "resolvido")


def event_icon_format(category_id: str) -> str:
    return "png" if category_id in EVENT_ICON_PNG_IDS else "svg"


def event_icon_static_path(category_id: str) -> str:
    cid = (category_id or "outro").strip().lower()
    return f"/static/img/icons/{cid}.{event_icon_format(cid)}"


def event_icon_url(category_id: str, *, base_url: str = "") -> str:
    path = event_icon_static_path(category_id)
    base = (base_url or "").rstrip("/")
    return f"{base}{path}" if base else path


def status_symbol_color(status_id: str) -> str:
    return STATUS_META.get(status_id, {}).get("cor", "#15803d")


def status_legend_item(status_id: str) -> dict[str, Any]:
    meta = STATUS_META.get(status_id, {})
    return {
        "status": status_id,
        "label": meta.get("label", status_id),
        "symbol_color": meta.get("cor", status_symbol_color(status_id)),
        "descricao": meta.get("descricao", ""),
        "visivel_mapa_publico": bool(meta.get("visivel_mapa_publico")),
        "export_publico": bool(meta.get("export_publico")),
    }


def status_legend_payload() -> dict[str, Any]:
    """Relação cor/status usada nas legendas (mapa público e Funcionalidades)."""
    mapa_publico = [
        status_legend_item(sid)
        for sid in PUBLIC_MAP_LEGEND_STATUS_ORDER
        if sid in STATUS_META
    ]
    todos = [status_legend_item(sid) for sid in STATUS_META]
    return {
        "titulo": "Relação cor / status",
        "descricao": (
            "A cor do símbolo interno do marcador segue o status do evento. "
            "A legenda do mapa público exibe os itens em mapa_publico."
        ),
        "mapa_publico": mapa_publico,
        "todos_status": todos,
        "por_status": {item["status"]: item["symbol_color"] for item in todos},
    }


def enrich_event_category(cat: dict[str, str], *, base_url: str = "") -> dict[str, Any]:
    cid = cat["id"]
    return {
        **cat,
        "icon_format": event_icon_format(cid),
        "icon_path": event_icon_static_path(cid),
        "icon_url": event_icon_url(cid, base_url=base_url),
    }


def traffic_event_symbology_payload(*, base_url: str = "") -> dict[str, Any]:
    """Especificação única de simbologia para consumo pela API pública."""
    return {
        "interaction_type": "evento_trafego",
        "marker_shape": TRAFFIC_MARKER_SHAPE,
        "marker_border_color": MARKER_BORDER_COLOR,
        "symbol_color_source": "status",
        "legenda_status": status_legend_payload(),
        "rendering": {
            "description": (
                "Losango com borda fixa na cor marker_border_color; "
                "ícone interno da categoria (icon_url) tingido pela cor do status (symbol_color)."
            ),
            "icon_technique": "mask_or_alpha_tint",
            "sigla_no_marcador": False,
        },
        "status_colors": {
            sid: meta["cor"] for sid, meta in STATUS_META.items()
        },
        "categories": [
            enrich_event_category(cat, base_url=base_url) for cat in EVENT_CATEGORIES
        ],
    }


def traffic_feature_symbology(
    category_id: str,
    status_id: str,
    *,
    base_url: str = "",
) -> dict[str, Any]:
    """Propriedades de simbologia por feature (única forma válida para eventos de tráfego)."""
    meta = STATUS_META.get(status_id, {})
    return {
        "marker_shape": TRAFFIC_MARKER_SHAPE,
        "marker_border_color": MARKER_BORDER_COLOR,
        "symbol_color": status_symbol_color(status_id),
        "status_label": meta.get("label", status_id),
        "icon_format": event_icon_format(category_id),
        "icon_path": event_icon_static_path(category_id),
        "icon_url": event_icon_url(category_id, base_url=base_url),
    }
