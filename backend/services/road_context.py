"""Monta o contexto viário do reporte a partir do snap na malha DER ou do município."""
from __future__ import annotations

from typing import Any

ROAD_SCOPE_ESTADUAL = "estadual"
ROAD_SCOPE_FEDERAL = "federal"
ROAD_SCOPE_MUNICIPAL = "municipal"
ROAD_SCOPE_URBAN = "via_urbana"

# Eventos municipais: armazenados para relatórios/exportação, nunca no mapa PLI
STATUS_REGISTRO_MUNICIPAL = "registro_municipal"

MANAGER_REVIEW_SCOPES = frozenset({ROAD_SCOPE_ESTADUAL, ROAD_SCOPE_FEDERAL})


def requires_manager_review(road_scope: str | None) -> bool:
    """Conferência do gestor DER: apenas rodovias estaduais e federais."""
    return (road_scope or "").strip().lower() in MANAGER_REVIEW_SCOPES


# Leitura do shapefile DER (inclui campos só para classificação interna)
_DER_SNAP_READ_MAP = {
    "rodovia": "Rodovia",
    "denominacao": "Denominaca",
    "tipo_rodoviario": "TipoRodovi",
    "municipio": "Municipio",
    "cod_regional": "CodRegiona",
    "sede_regional": "SedeRegion",
    "residencia": "Residencia",
    "sede_residencia": "SedeReside",
    "jurisdicao": "Jurisdicao",
    "administra": "Administra",
    "tipo_pista": "TipoPista",
    "perimetro_urbano": "PerimetroU",
}

# Campos DER persistidos/exportados (PostGIS + GeoJSON ponto E polígono)
DER_LAYER_EXCLUDE = frozenset({"jurisdicao", "perimetro_urbano", "scope"})
DER_LAYER_KEYS = tuple(
    k for k in _DER_SNAP_READ_MAP if k not in DER_LAYER_EXCLUDE
)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _props_from_geojson(props: dict) -> dict[str, str | None]:
    """Lê propriedades já normalizadas ou cruas do shapefile."""
    out: dict[str, str | None] = {}
    for key, shp_field in _DER_SNAP_READ_MAP.items():
        raw = props.get(key)
        if raw is None:
            raw = props.get(shp_field)
        out[key] = _clean(raw)
    return out


def _der_context_for_storage(der: dict[str, str | None]) -> dict[str, str | None]:
    """Remove campos internos que não entram em PostGIS nem GeoJSON."""
    return {k: v for k, v in der.items() if k not in DER_LAYER_EXCLUDE}


def context_from_der_snap(*, scope: str, feat: dict, dist_m: float) -> dict[str, Any]:
    props = feat.get("properties") or {}
    der = _der_context_for_storage(_props_from_geojson(props))
    return {
        "scope": scope,
        "scope_label": scope_label(scope),
        "snap_dist_m": round(dist_m, 1) if dist_m is not None else None,
        **der,
    }


def context_from_municipio(municipio: str | None) -> dict[str, Any]:
    return {
        "scope": ROAD_SCOPE_MUNICIPAL,
        "scope_label": scope_label(ROAD_SCOPE_MUNICIPAL),
        "municipio": _clean(municipio),
        "rodovia": None,
        "denominacao": None,
        "tipo_rodoviario": None,
        "cod_regional": None,
        "sede_regional": None,
        "residencia": None,
        "sede_residencia": None,
    }


def scope_label(scope: str | None) -> str:
    labels = {
        ROAD_SCOPE_FEDERAL: "Rodovia federal",
        ROAD_SCOPE_ESTADUAL: "Rodovia estadual",
        ROAD_SCOPE_MUNICIPAL: "Via municipal",
    }
    return labels.get(scope or "", "Local não identificado")


ROAD_CONTEXT_POPUP_EXCLUDE = DER_LAYER_EXCLUDE

TIPO_PISTA_LABELS: dict[str, str] = {
    "DUP": "Duplicada",
    "PAV": "Pavimentada",
    "CIM": "Cimento",
    "ASF": "Asfaltada",
    "BLO": "Bloqueada / bloquete",
    "CCPB": "CBUQ / concreto betuminoso",
    "TSD": "Tratamento superficial duplo",
    "TER": "Terra",
    "TERRA": "Terra",
    "PED": "Pedra",
    "PEDREIRA": "Pedreira",
    "REC": "Revestimento primário",
}

ADMINISTRA_LABELS: dict[str, str] = {
    "DER": "DER-SP",
    "DNIT": "DNIT",
    "CONCESSIONARIA": "Concessionária",
    "CONCESSIONÁRIA": "Concessionária",
}

ROAD_CONTEXT_POPUP_FIELDS: list[tuple[str, str]] = [
    ("scope_label", "Classificação viária"),
    ("_rodovia_line", "Rodovia"),
    ("tipo_rodoviario", "Tipo rodoviário"),
    ("municipio", "Município"),
    ("tipo_pista", "Tipo de pista"),
    ("administra", "Administrador da via"),
    ("cod_regional", "Coordenadoria Regional Geral DER"),
    ("sede_regional", "Sede da coordenadoria"),
    ("residencia", "Residência de conserva DER"),
    ("sede_residencia", "Sede da residência de conserva"),
    ("snap_dist_m", "Distância snap utilizada"),
]

# Rótulos amigáveis dos campos DER exportados (ordem fixa)
DER_LAYER_FIELD_LABELS: tuple[str, ...] = tuple(
    label for _, label in ROAD_CONTEXT_POPUP_FIELDS
)


def _title_case(value: str) -> str:
    parts: list[str] = []
    word: list[str] = []
    for ch in value.lower():
        if ch.isalnum():
            if not word:
                word.append(ch.upper())
            else:
                word.append(ch)
        else:
            if word:
                parts.append("".join(word))
                word = []
            parts.append(ch)
    if word:
        parts.append("".join(word))
    return "".join(parts)


def _rodovia_line(ctx: dict[str, Any]) -> str | None:
    rod = ctx.get("rodovia")
    denom = ctx.get("denominacao")
    if rod and denom:
        return f"{rod} — {denom}"
    if rod:
        return str(rod)
    if denom:
        return str(denom)
    return None


def format_road_context_value(key: str, value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if key == "tipo_pista":
        code = text.upper()
        return TIPO_PISTA_LABELS.get(code, _title_case(code))
    if key == "administra":
        code = text.upper()
        return ADMINISTRA_LABELS.get(code, _title_case(text))
    if key == "snap_dist_m":
        try:
            n = float(text)
        except (TypeError, ValueError):
            return None
        formatted = f"{n:.1f}".replace(".", ",")
        return f"{formatted} m"
    if key in ("tipo_rodoviario", "municipio", "sede_regional", "sede_residencia"):
        return _title_case(text)
    return text


def der_layer_properties(ctx: dict[str, Any] | None) -> dict[str, str]:
    """Atributos DER para PostGIS/GeoJSON: rótulos amigáveis → valores amigáveis."""
    return {
        label: value
        for label, value in road_context_popup_rows(ctx)
    }


def road_context_popup_rows(ctx: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Pares (rótulo, valor) para popup — omite campos vazios e excluídos."""
    if not ctx:
        return []
    data = dict(ctx)
    if not data.get("scope_label") and data.get("scope"):
        data["scope_label"] = scope_label(str(data["scope"]))
    rows: list[tuple[str, str]] = []
    for key, label in ROAD_CONTEXT_POPUP_FIELDS:
        if key in ROAD_CONTEXT_POPUP_EXCLUDE:
            continue
        if key == "_rodovia_line":
            value = _rodovia_line(data)
        else:
            value = format_road_context_value(key, data.get(key))
        if value:
            rows.append((label, value))
    return rows


def friendly_road_lines(ctx: dict[str, Any] | None) -> list[str]:
    """Linhas legíveis para popup — formato compacto label: valor."""
    return [f"{label}: {value}" for label, value in road_context_popup_rows(ctx)]
