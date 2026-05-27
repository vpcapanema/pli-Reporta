"""Pipeline de submissão de reportes — orquestra veracidade, clusterização e relevância."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Report
from . import exif as exif_svc
from . import photos as photo_svc
from .clustering import find_or_create_cluster
from .geo import nearest_road
from .ids import new_ulid
from .nonce import verify_nonce
from .relevance import compute_relevance, is_blocking, ttl_for
from .veracity import compute_veracity, signals_to_payload


@dataclass
class IngestResult:
    report: Report
    explanation: list[str]


def _highway_for(lat: float, lon: float) -> str | None:
    if not settings.roads_geojson_path:
        return None
    _, feat = nearest_road(lat, lon, settings.roads_geojson_path, max_m=60.0)
    if not feat:
        return None
    return (feat.get("properties") or {}).get("highway")


def _osm_id_for(lat: float, lon: float) -> str | None:
    if not settings.roads_geojson_path:
        return None
    _, feat = nearest_road(lat, lon, settings.roads_geojson_path, max_m=60.0)
    if not feat:
        return None
    props = feat.get("properties") or {}
    osm_id = props.get("osm_id") or props.get("id") or props.get("@id")
    if osm_id is None:
        return None
    return f"osm:way:{osm_id}"


def ingest_report(
    db: Session,
    *,
    image_bytes: bytes,
    lat: float,
    lon: float,
    accuracy_m: float | None,
    category: str,
    magnitude: str,
    description: str | None,
    captured_at_iso: str,
    capture_nonce: str | None,
    client_id: str | None,
    geometry_geojson: str | None,
    user_reputation: float = 0.0,
) -> IngestResult:
    rid = new_ulid()
    rel_path, sha = photo_svc.save_photo(image_bytes, rid)
    exif_data = exif_svc.parse_exif(image_bytes)
    nonce_ok = verify_nonce(capture_nonce)

    # Cluster + confirmações.
    cluster = find_or_create_cluster(db, category=category, lat=lat, lon=lon)

    # Veracidade.
    v_score, signals = compute_veracity(
        lat=lat,
        lon=lon,
        accuracy_m=accuracy_m,
        exif=exif_data,
        captured_at_iso=captured_at_iso,
        nonce_valid=nonce_ok,
        reputation=user_reputation,
    )

    # Relevância.
    highway = _highway_for(lat, lon)
    r = compute_relevance(
        category=category,
        magnitude=magnitude,
        n_confirmations=cluster.confirmations,
        captured_at_iso=captured_at_iso,
        highway=highway,
    )
    r_score = r.value()
    priority = v_score * r_score

    # Status.
    if v_score < settings.auto_discard_threshold:
        status = "descartado"
    elif v_score < settings.auto_publish_threshold:
        status = "em_moderacao"
    else:
        status = "validado"

    # Validade (TTL por categoria).
    valid_to_dt = datetime.now(timezone.utc) + timedelta(hours=ttl_for(category))

    affected_edge = _osm_id_for(lat, lon)

    rep = Report(
        id=rid,
        client_id=client_id,
        category=category,
        magnitude=magnitude,
        description=(description or None),
        lat=lat,
        lon=lon,
        accuracy_m=accuracy_m,
        geometry_geojson=geometry_geojson,
        photo_path=rel_path,
        photo_hash=sha,
        exif_json=json.dumps(exif_data, ensure_ascii=False) if exif_data else None,
        captured_at=captured_at_iso,
        capture_nonce_valid=1 if nonce_ok else 0,
        veracity_score=v_score,
        veracity_signals_json=json.dumps(signals_to_payload(signals), ensure_ascii=False),
        relevance_score=r_score,
        priority=priority,
        status=status,
        cluster_id=cluster.id,
        valid_to=valid_to_dt.isoformat(),
        affected_edges_json=json.dumps([affected_edge]) if affected_edge else None,
    )
    db.add(rep)
    db.flush()

    explanation = [s.line() for s in signals] + r.explain() + [
        f"P = V·R = {priority:.2f}",
        f"status = {status}",
        f"bloqueante = {is_blocking(category, priority)}",
    ]
    return IngestResult(report=rep, explanation=explanation)


def report_to_feature(r: Report) -> dict[str, Any]:
    blocking = is_blocking(r.category, r.priority)
    coords = [r.lon, r.lat]
    geom: dict[str, Any] = {"type": "Point", "coordinates": coords}
    if r.geometry_geojson:
        try:
            geom = json.loads(r.geometry_geojson)
        except (ValueError, TypeError):
            pass
    affected: list[str] = []
    if r.affected_edges_json:
        try:
            affected = [e for e in json.loads(r.affected_edges_json) if e]
        except (ValueError, TypeError):
            affected = []
    return {
        "type": "Feature",
        "geometry": geom,
        "properties": {
            "id": r.id,
            "category": r.category,
            "magnitude": r.magnitude,
            "veracity": round(r.veracity_score, 3),
            "relevance": round(r.relevance_score, 3),
            "priority": round(r.priority, 3),
            "status": r.status,
            "blocking": blocking,
            "affected_edges": affected,
            "valid_from": r.valid_from,
            "valid_to": r.valid_to,
            "captured_at": r.captured_at,
            "photo_url": photo_svc.public_url_for(r.photo_path),
        },
    }
