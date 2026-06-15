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


# Campos exportados do shapefile DER → chaves amigáveis no JSON
_DER_FIELD_MAP = {
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


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _props_from_geojson(props: dict) -> dict[str, str | None]:
    """Lê propriedades já normalizadas ou cruas do shapefile."""
    out: dict[str, str | None] = {}
    for key, shp_field in _DER_FIELD_MAP.items():
        raw = props.get(key)
        if raw is None:
            raw = props.get(shp_field)
        out[key] = _clean(raw)
    return out


def context_from_der_snap(*, scope: str, feat: dict, dist_m: float) -> dict[str, Any]:
    props = feat.get("properties") or {}
    der = _props_from_geojson(props)
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


def friendly_road_lines(ctx: dict[str, Any] | None) -> list[str]:
    """Linhas legíveis para popup do mapa."""
    if not ctx:
        return []
    lines: list[str] = []
    scope = ctx.get("scope_label") or scope_label(ctx.get("scope"))
    if scope:
        lines.append(scope)

    rod = ctx.get("rodovia")
    denom = ctx.get("denominacao")
    if rod and denom:
        lines.append(f"{rod} — {denom}")
    elif rod:
        lines.append(str(rod))
    elif denom:
        lines.append(str(denom))

    tipo = ctx.get("tipo_rodoviario")
    if tipo:
        lines.append(f"Tipo: {tipo}")

    mun = ctx.get("municipio")
    if mun:
        lines.append(f"Município: {mun}")

    reg = ctx.get("cod_regional")
    sede_reg = ctx.get("sede_regional")
    if reg or sede_reg:
        parts = [p for p in (reg, sede_reg and f"sede {sede_reg}") if p]
        lines.append(f"Regional DER: {' · '.join(parts)}")

    resid = ctx.get("residencia")
    sede_res = ctx.get("sede_residencia")
    if resid or sede_res:
        parts = [p for p in (resid and f"residência {resid}", sede_res) if p]
        lines.append(f"Residência: {' · '.join(parts)}")

    return lines
