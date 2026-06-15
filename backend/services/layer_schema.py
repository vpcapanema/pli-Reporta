"""Esquema de propriedades das features nas camadas (PostGIS + GeoJSON).

Cada reporte aceito gera duas geometrias (ponto e polígono) com o mesmo pacote
de atributos: campos do sistema + campos DER (snap na malha), todos com rótulos
e valores amigáveis. Ver docs/CAMPOS_CAMADAS.md.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..models import Report
from .report_catalog import (
    EVENT_CATEGORIES,
    INTERACTION_TYPES,
    MANIF_CATEGORIES,
    STATUS_META,
    visibility_for_status,
)
from .road_context import DER_LAYER_FIELD_LABELS, der_layer_properties

# (chave interna, rótulo amigável exportado)
SYSTEM_LAYER_FIELD_SPECS: tuple[tuple[str, str], ...] = (
    ("id", "ID"),
    ("interaction_type", "Tipo de interação"),
    ("category", "Categoria (código)"),
    ("category_label", "Categoria"),
    ("category_sigla", "Sigla da categoria"),
    ("magnitude", "Magnitude"),
    ("description", "Descrição"),
    ("status", "Status"),
    ("visivel_mapa_publico", "Visível no mapa público"),
    ("visivel_mapa_gestao", "Visível no mapa gestão"),
    ("export_publico", "Exportação pública"),
    ("export_gestao", "Exportação gestão"),
    ("blocking", "Bloqueante"),
    ("cluster_id", "Cluster"),
    ("veracity", "Veracidade (V)"),
    ("relevance", "Relevância (R)"),
    ("priority", "Prioridade (P)"),
    ("valid_from", "Válido desde"),
    ("valid_to", "Válido até"),
    ("captured_at", "Capturado em"),
    ("received_at", "Recebido em"),
    ("photo_url", "URL da foto"),
    ("accuracy_m", "Acurácia GPS (m)"),
    ("capture_nonce_valid", "Nonce de captura válido"),
    ("affected_edges", "Trechos afetados"),
)

SYSTEM_LAYER_FIELD_LABELS: tuple[str, ...] = tuple(
    label for _, label in SYSTEM_LAYER_FIELD_SPECS
)

# Ordem completa: sistema + DER (malha estadual, sem jurisdicao/perimetro_urbano)
FULL_LAYER_FIELD_LABELS: tuple[str, ...] = (
    SYSTEM_LAYER_FIELD_LABELS + DER_LAYER_FIELD_LABELS
)

# Chaves internas legadas (feeds atuais ainda usam road_context aninhado)
LAYER_PROPERTY_KEYS: tuple[str, ...] = tuple(
    key for key, _ in SYSTEM_LAYER_FIELD_SPECS
) + ("road_scope", "road_label", "road_context")

PUBLIC_MAP_STATUSES = frozenset(
    s for s, m in STATUS_META.items() if m.get("visivel_mapa_publico")
)

GESTAO_MAP_STATUSES = frozenset(
    s for s, m in STATUS_META.items() if m.get("visivel_mapa_gestao")
)


def empty_system_properties() -> dict[str, Any]:
    """Template dos campos do sistema (chaves internas)."""
    return {
        "id": None,
        "interaction_type": None,
        "category": None,
        "category_label": None,
        "category_sigla": None,
        "magnitude": "normal",
        "description": None,
        "status": "submetido",
        "visivel_mapa_publico": False,
        "visivel_mapa_gestao": False,
        "export_publico": False,
        "export_gestao": False,
        "blocking": False,
        "cluster_id": None,
        "veracity": 0.0,
        "relevance": 0.0,
        "priority": 0.0,
        "valid_from": None,
        "valid_to": None,
        "captured_at": None,
        "received_at": None,
        "photo_url": None,
        "accuracy_m": None,
        "capture_nonce_valid": 0,
        "affected_edges": [],
    }


def empty_properties() -> dict[str, Any]:
    """Compat: template com chaves internas legadas."""
    return {
        **empty_system_properties(),
        "road_scope": None,
        "road_label": None,
        "road_context": None,
    }


def empty_full_layer_properties() -> dict[str, Any]:
    """Template com rótulos amigáveis completos (sistema + DER)."""
    return {label: None for label in FULL_LAYER_FIELD_LABELS}


def _is_valid_now(valid_to: str | None, *, now: datetime | None = None) -> bool:
    if not valid_to:
        return True
    ref = now or datetime.now(timezone.utc)
    try:
        expiry = datetime.fromisoformat(valid_to.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry > ref
    except ValueError:
        return True


def visibility_flags(
    status: str,
    *,
    valid_to: str | None = None,
    now: datetime | None = None,
) -> tuple[bool, bool]:
    """Retorna (visivel_mapa_publico, visivel_mapa_gestao) com matriz + valid_to."""
    flags = visibility_for_status(status)
    if not _is_valid_now(valid_to, now=now):
        return False, False
    return flags["visivel_mapa_publico"], flags["visivel_mapa_gestao"]


def feed_visible(
    status: str,
    *,
    valid_to: str | None = None,
    mapa: str = "publico",
    now: datetime | None = None,
) -> bool:
    """Indica se o reporte entra no feed do mapa ou exportação."""
    flags = visibility_for_status(status)
    if not _is_valid_now(valid_to, now=now):
        return False
    if mapa == "publico":
        return flags["visivel_mapa_publico"]
    if mapa == "gestao":
        return flags["visivel_mapa_gestao"]
    if mapa == "export_publico":
        return flags["export_publico"]
    if mapa == "export_gestao":
        return flags["export_gestao"]
    raise ValueError(f"mapa desconhecido: {mapa}")


def _category_meta(category: str) -> tuple[str, str]:
    for cat in EVENT_CATEGORIES + MANIF_CATEGORIES:
        if cat["id"] == category:
            return cat["label"], cat["sigla"]
    return category, "??"


def build_full_layer_properties(rep: Report) -> dict[str, Any]:
    """Pacote completo de atributos com rótulos e valores amigáveis (36 campos)."""
    from . import photos as photo_svc
    from .relevance import is_blocking

    affected: list[str] = []
    if rep.affected_edges_json:
        try:
            affected = [e for e in json.loads(rep.affected_edges_json) if e]
        except (ValueError, TypeError):
            affected = []

    road_context: dict | None = None
    if rep.road_context_json:
        try:
            road_context = json.loads(rep.road_context_json)
        except (ValueError, TypeError):
            road_context = None

    cat_label, cat_sigla = _category_meta(rep.category)
    itype_label = next(
        (t["label"] for t in INTERACTION_TYPES if t["id"] == rep.interaction_type),
        rep.interaction_type,
    )
    blocking = (
        rep.interaction_type == "evento_trafego"
        and is_blocking(rep.category, rep.priority)
    )
    vis_pub, vis_gest = visibility_flags(rep.status, valid_to=rep.valid_to)
    vis = visibility_for_status(rep.status)
    status_label = STATUS_META.get(rep.status, {}).get("label", rep.status)

    internal: dict[str, Any] = {
        "id": rep.id,
        "interaction_type": itype_label,
        "category": rep.category,
        "category_label": cat_label,
        "category_sigla": cat_sigla,
        "magnitude": rep.magnitude,
        "description": rep.description,
        "status": status_label,
        "visivel_mapa_publico": vis_pub,
        "visivel_mapa_gestao": vis_gest,
        "export_publico": vis["export_publico"],
        "export_gestao": vis["export_gestao"],
        "blocking": blocking,
        "cluster_id": rep.cluster_id,
        "veracity": round(rep.veracity_score, 3),
        "relevance": round(rep.relevance_score, 3),
        "priority": round(rep.priority, 3),
        "valid_from": rep.valid_from,
        "valid_to": rep.valid_to,
        "captured_at": rep.captured_at,
        "received_at": rep.received_at,
        "photo_url": photo_svc.public_url_for(rep.photo_path),
        "accuracy_m": rep.accuracy_m,
        "capture_nonce_valid": rep.capture_nonce_valid,
        "affected_edges": affected,
    }

    props = empty_full_layer_properties()
    for key, label in SYSTEM_LAYER_FIELD_SPECS:
        props[label] = internal[key]
    props.update(der_layer_properties(road_context))
    return props
