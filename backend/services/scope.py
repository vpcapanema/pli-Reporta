"""Escopo geográfico de reportes de tráfego.

Regras (malha DER + mancha urbana IBGE):
- Snap na malha DER com rodovia federal (BR / jurisdição Federal) → federal
- Snap na malha DER demais trechos → estadual
- Dentro da mancha urbana IBGE, sem snap DER → recusado (via urbana)
- Fora da malha DER e fora da mancha urbana → municipal (registro interno, sem publicação PLI)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import settings
from .geo import nearest_road, point_in_municipio, point_in_urban_footprint
from .road_context import (
    ROAD_SCOPE_ESTADUAL,
    ROAD_SCOPE_FEDERAL,
    ROAD_SCOPE_MUNICIPAL,
    context_from_der_snap,
    context_from_municipio,
)


class ScopeRejectedError(Exception):
    """Reporte fora do escopo público PLI (ex.: via urbana)."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class ScopeResult:
    scope: str
    rodovia: str | None
    dist_m: float | None
    in_urban: bool
    explanation: str
    context: dict[str, Any]


def _roads_path() -> str | None:
    path = (settings.roads_geojson_path or "").strip()
    if not path or not Path(path).exists():
        return None
    return path


def _urban_path() -> str | None:
    path = (settings.urban_geojson_path or "").strip()
    if not path or not Path(path).exists():
        return None
    return path


def scope_gate_enabled() -> bool:
    """Gate ativo quando malha DER e mancha urbana IBGE estão configuradas."""
    return _roads_path() is not None and _urban_path() is not None


def _normalize_rodovia(value: str | None) -> str:
    return str(value or "").strip().upper().replace("-", " ").replace("  ", " ")


def _is_federal(props: dict, rodovia: str) -> bool:
    rod = _normalize_rodovia(rodovia)
    juris = str(props.get("jurisdicao") or "").strip().lower()
    admin = str(props.get("administra") or "").strip().lower()
    if rod.startswith("BR"):
        return True
    if juris == "federal":
        return True
    if admin == "dnit":
        return True
    return False


def _is_estadual(props: dict, rodovia: str) -> bool:
    rod = _normalize_rodovia(rodovia)
    juris = str(props.get("jurisdicao") or "").strip().lower()
    admin = str(props.get("administra") or "").strip().lower()
    if rod.startswith("SP"):
        return True
    if juris == "estadual":
        return True
    if admin in ("der", "concessionária", "concessionaria"):
        return True
    return False


def classify_traffic_scope(lat: float, lon: float) -> ScopeResult:
    """Classifica escopo viário. Levanta ScopeRejectedError apenas para via urbana."""
    roads_path = _roads_path()
    urban_path = _urban_path()
    snap_max = max(10.0, float(settings.road_snap_max_m))

    dist_m = float("inf")
    feat: dict | None = None
    if roads_path:
        dist_m, feat = nearest_road(lat, lon, roads_path, max_m=snap_max)

    on_der = feat is not None and dist_m <= snap_max
    in_urban = point_in_urban_footprint(lat, lon, urban_path) if urban_path else False

    if on_der:
        props = feat.get("properties") or {}
        rodovia = str(props.get("rodovia") or "").strip() or None
        if _is_federal(props, rodovia or ""):
            scope = ROAD_SCOPE_FEDERAL
            expl = f"Snap na malha DER — rodovia federal ({rodovia or 'BR'})"
        elif _is_estadual(props, rodovia or ""):
            scope = ROAD_SCOPE_ESTADUAL
            expl = f"Snap na malha DER — rodovia estadual ({rodovia or 'SP'})"
        else:
            scope = ROAD_SCOPE_ESTADUAL
            expl = f"Snap na malha DER ({rodovia or 'trecho estadual'})"
        ctx = context_from_der_snap(scope=scope, feat=feat, dist_m=dist_m)
        return ScopeResult(scope, rodovia, dist_m, in_urban, expl, ctx)

    if in_urban:
        raise ScopeRejectedError(
            "Reporte fora do escopo: localização em via urbana (mancha urbana IBGE). "
            "O PLI Reporta cobre apenas rodovias estaduais e federais cadastradas na malha DER."
        )

    municipio = point_in_municipio(lat, lon)
    ctx = context_from_municipio(municipio)
    return ScopeResult(
        scope=ROAD_SCOPE_MUNICIPAL,
        rodovia=None,
        dist_m=None,
        in_urban=False,
        explanation=(
            "Fora da malha DER estadual/federal — registrado como via municipal "
            "(armazenamento interno, sem publicação no mapa PLI)."
        ),
        context=ctx,
    )
