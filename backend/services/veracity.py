"""Cálculo do score de Veracidade V (METODOLOGIA §3).

Cada sinal devolve (valor em [0,1], explicação humana). O score final é a média
ponderada normalizada. A explicação é guardada no banco para auditoria.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from ..config import settings
from . import exif as exif_svc
from . import geo


@dataclass
class Signal:
    name: str
    value: float
    weight: float
    detail: str

    def line(self) -> str:
        return f"{self.name}={self.value:.2f} (w={self.weight:.2f}) — {self.detail}"


WEIGHTS = {
    "geo_browser": 0.20,
    "exif_match": 0.15,
    "capture_inapp": 0.20,
    "road_snap": 0.10,
    "image_integrity": 0.15,
    "user_reputation": 0.10,
    "temporal_plausibility": 0.10,
}

EDIT_SOFTWARE_HINTS = ("photoshop", "gimp", "lightroom", "snapseed", "facetune", "picsart")


def _parse_iso(s: str) -> datetime | None:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _signal_geo_browser(accuracy_m: float | None, lat: float, lon: float) -> Signal:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return Signal("geo_browser", 0.0, WEIGHTS["geo_browser"], "coordenada inválida")
    if accuracy_m is None:
        return Signal("geo_browser", 0.4, WEIGHTS["geo_browser"], "GPS sem acurácia declarada")
    if accuracy_m < 50:
        return Signal("geo_browser", 1.0, WEIGHTS["geo_browser"], f"GPS ótimo ({accuracy_m:.0f} m)")
    if accuracy_m < 200:
        return Signal("geo_browser", 0.5, WEIGHTS["geo_browser"], f"GPS regular ({accuracy_m:.0f} m)")
    return Signal("geo_browser", 0.1, WEIGHTS["geo_browser"], f"GPS ruim ({accuracy_m:.0f} m)")


def _signal_exif_match(
    exif: dict, lat: float, lon: float, captured_at_iso: str
) -> Signal:
    if not exif or "lat" not in exif:
        return Signal(
            "exif_match",
            0.5,
            WEIGHTS["exif_match"],
            "sem GPS no EXIF (não pune)",
        )
    d = geo.haversine_m(lat, lon, exif["lat"], exif["lon"])
    pos_ok = d < 100
    time_ok = True
    if "datetime" in exif and captured_at_iso:
        exif_dt = exif_svc.parse_exif_datetime(exif["datetime"])
        cap_dt = _parse_iso(captured_at_iso)
        if exif_dt and cap_dt:
            if exif_dt.tzinfo is None:
                exif_dt = exif_dt.replace(tzinfo=timezone.utc)
            if cap_dt.tzinfo is None:
                cap_dt = cap_dt.replace(tzinfo=timezone.utc)
            time_ok = abs((cap_dt - exif_dt).total_seconds()) < 300
    if pos_ok and time_ok:
        return Signal("exif_match", 1.0, WEIGHTS["exif_match"], f"EXIF coerente (Δ={d:.0f} m)")
    if pos_ok or time_ok:
        return Signal("exif_match", 0.5, WEIGHTS["exif_match"], "EXIF parcialmente coerente")
    return Signal("exif_match", 0.1, WEIGHTS["exif_match"], f"EXIF incoerente (Δ={d:.0f} m)")


def _signal_capture_inapp(nonce_valid: bool) -> Signal:
    if nonce_valid:
        return Signal("capture_inapp", 1.0, WEIGHTS["capture_inapp"], "captura in-app válida")
    return Signal("capture_inapp", 0.4, WEIGHTS["capture_inapp"], "upload de galeria")


def _signal_road_snap(lat: float, lon: float) -> Signal:
    if not settings.roads_geojson_path:
        return Signal(
            "road_snap",
            0.7,
            WEIGHTS["road_snap"],
            "sem base de vias configurada (neutro)",
        )
    dist, _ = geo.nearest_road(lat, lon, settings.roads_geojson_path)
    if not isfinite(dist):
        return Signal("road_snap", 0.7, WEIGHTS["road_snap"], "base de vias vazia")
    if dist < 30:
        return Signal("road_snap", 1.0, WEIGHTS["road_snap"], f"sobre via (d={dist:.0f} m)")
    if dist < 100:
        return Signal("road_snap", 0.6, WEIGHTS["road_snap"], f"perto de via (d={dist:.0f} m)")
    if dist < 200:
        return Signal("road_snap", 0.3, WEIGHTS["road_snap"], f"longe de via (d={dist:.0f} m)")
    return Signal("road_snap", 0.0, WEIGHTS["road_snap"], f"fora de via (d={dist:.0f} m)")


def _signal_image_integrity(exif: dict) -> Signal:
    sw = (exif.get("software") or "").lower()
    if any(hint in sw for hint in EDIT_SOFTWARE_HINTS):
        return Signal("image_integrity", 0.0, WEIGHTS["image_integrity"], f"editor detectado: {sw}")
    if sw:
        return Signal("image_integrity", 0.9, WEIGHTS["image_integrity"], f"software: {sw}")
    return Signal("image_integrity", 0.85, WEIGHTS["image_integrity"], "sem indício de edição")


def _signal_user_reputation(reputation: float) -> Signal:
    rep = max(0.0, min(1.0, reputation))
    detail = "anônimo (rep=0)" if rep == 0 else f"reputação {rep:.2f}"
    return Signal("user_reputation", rep, WEIGHTS["user_reputation"], detail)


def _signal_temporal_plausibility(captured_at_iso: str) -> Signal:
    cap = _parse_iso(captured_at_iso)
    if cap is None:
        return Signal(
            "temporal_plausibility",
            0.3,
            WEIGHTS["temporal_plausibility"],
            "captured_at inválido",
        )
    if cap.tzinfo is None:
        cap = cap.replace(tzinfo=timezone.utc)
    age_s = (datetime.now(timezone.utc) - cap).total_seconds()
    if age_s < 0:
        return Signal(
            "temporal_plausibility",
            0.2,
            WEIGHTS["temporal_plausibility"],
            "captura no futuro?",
        )
    if age_s < 1800:
        return Signal("temporal_plausibility", 1.0, WEIGHTS["temporal_plausibility"], "≤ 30 min")
    if age_s < 7200:
        return Signal("temporal_plausibility", 0.6, WEIGHTS["temporal_plausibility"], "≤ 2 h")
    if age_s < 86400:
        return Signal("temporal_plausibility", 0.4, WEIGHTS["temporal_plausibility"], "≤ 24 h")
    return Signal("temporal_plausibility", 0.2, WEIGHTS["temporal_plausibility"], "> 24 h")


def compute_veracity(
    *,
    lat: float,
    lon: float,
    accuracy_m: float | None,
    exif: dict,
    captured_at_iso: str,
    nonce_valid: bool,
    reputation: float = 0.0,
) -> tuple[float, list[Signal]]:
    signals = [
        _signal_geo_browser(accuracy_m, lat, lon),
        _signal_exif_match(exif, lat, lon, captured_at_iso),
        _signal_capture_inapp(nonce_valid),
        _signal_road_snap(lat, lon),
        _signal_image_integrity(exif),
        _signal_user_reputation(reputation),
        _signal_temporal_plausibility(captured_at_iso),
    ]
    total_w = sum(s.weight for s in signals) or 1.0
    score = sum(s.value * s.weight for s in signals) / total_w
    return score, signals


def signals_to_payload(signals: list[Signal]) -> dict[str, Any]:
    return {s.name: {"value": s.value, "weight": s.weight, "detail": s.detail} for s in signals}
