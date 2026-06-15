"""Pipeline de submissão de reportes — orquestra veracidade, clusterização e relevância."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Report
from . import exif as exif_svc
from . import photos as photo_svc
from .clustering import find_or_create_cluster
from .geo import nearest_road
from .ids import new_ulid
from .legitimacy import compute_legitimacy
from .nonce import verify_nonce
from .relevance import BLOCKING_CATEGORIES, compute_relevance, is_blocking, ttl_for
from .veracity import compute_veracity, signals_to_payload

MANIFESTATION_CATEGORIES = frozenset({"elogio", "sugestao", "reclamacao"})
EVENT_CATEGORIES = frozenset({
    "bloqueio_total", "acidente", "incendio", "animal_na_pista",
    "objeto_na_pista", "queda_arvore", "veiculo_quebrado", "alagamento",
    "obra_grande", "lentidao_corredor", "sinalizacao_quebrada", "buraco", "outro",
})
PUBLIC_STATUSES = frozenset({"publicado", "validado"})


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


def _normalize_interaction(interaction_type: str | None, category: str) -> str:
    it = (interaction_type or "evento_trafego").strip().lower()
    if category in MANIFESTATION_CATEGORIES:
        return "manifestacao"
    if it in ("manifestacao", "evento_trafego"):
        return it
    return "evento_trafego"


def _duplicate_photo(db: Session, photo_hash: str) -> bool:
    row = db.execute(
        select(Report.id).where(Report.photo_hash == photo_hash).limit(1)
    ).scalar_one_or_none()
    return row is not None


def _status_for_event(
    *,
    v_score: float,
    category: str,
    policy,
    offline: bool = False,
    cluster_confirmations: int = 1,
) -> str:
    from .moderation_policy import ActivePolicy

    if not isinstance(policy, ActivePolicy):
        if v_score < policy.auto_discard_threshold:
            return "descartado"
        if category in BLOCKING_CATEGORIES:
            return "em_moderacao"
        if v_score < policy.auto_publish_threshold:
            return "em_moderacao"
        return "publicado"

    if v_score < policy.event_discard_below:
        return "descartado"
    if policy.always_review_blocking and category in BLOCKING_CATEGORIES:
        return "em_moderacao"
    if policy.always_review_other and category == "outro":
        return "em_moderacao"
    if policy.always_review_first_in_area and cluster_confirmations <= 1:
        return "em_moderacao"
    if v_score < policy.event_publish_min:
        status = "em_moderacao"
    else:
        status = "publicado"
    if policy.always_review_offline and offline and status == "publicado":
        return "em_moderacao"
    return status


def _status_for_manifestation(l_score: float, policy) -> str:
    from .moderation_policy import ActivePolicy

    if not isinstance(policy, ActivePolicy):
        if l_score < policy.manifestation_discard_threshold:
            return "descartado"
        if l_score < policy.manifestation_publish_threshold:
            return "em_moderacao"
        return "publicado"

    if l_score < policy.manif_discard_below:
        return "descartado"
    if l_score < policy.manif_publish_min:
        return "em_moderacao"
    return "publicado"


def _traffic_scope_at(
    lat: float, lon: float,
) -> tuple[str | None, str | None, dict | None, list[str]]:
    """Classifica escopo viário (DER/IBGE) ou devolve vazios se gate desligado."""
    from .scope import classify_traffic_scope, scope_gate_enabled

    if not scope_gate_enabled():
        return None, None, None, []
    scope = classify_traffic_scope(lat, lon)
    label = scope.rodovia or (scope.context or {}).get("municipio")
    return scope.scope, label, scope.context, [scope.explanation]


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
    interaction_type: str | None = "evento_trafego",
    offline_capture: bool = False,
    user_reputation: float = 0.0,
) -> IngestResult:
    itype = _normalize_interaction(interaction_type, category)
    if itype == "manifestacao" and category not in MANIFESTATION_CATEGORIES:
        category = "reclamacao"

    road_scope: str | None = None
    road_label: str | None = None
    road_context: dict | None = None
    scope_explanation: list[str] = []
    if itype == "evento_trafego":
        road_scope, road_label, road_context, scope_explanation = _traffic_scope_at(lat, lon)

    rid = new_ulid()
    rel_path, sha = photo_svc.save_photo(image_bytes, rid)
    exif_data = exif_svc.parse_exif(image_bytes)
    nonce_ok = verify_nonce(capture_nonce, offline=offline_capture)

    if _duplicate_photo(db, sha):
        rep = Report(
            id=rid,
            client_id=client_id,
            interaction_type=itype,
            category=category,
            magnitude=magnitude or "normal",
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
            veracity_score=0.0,
            relevance_score=0.0,
            priority=0.0,
            status="descartado",
        )
        db.add(rep)
        db.flush()
        return IngestResult(
            report=rep,
            explanation=["gate=duplicate_photo — foto já utilizada em outro reporte"],
        )

    v_score, signals = compute_veracity(
        lat=lat,
        lon=lon,
        accuracy_m=accuracy_m,
        exif=exif_data,
        captured_at_iso=captured_at_iso,
        nonce_valid=nonce_ok,
        reputation=user_reputation,
        offline_capture=offline_capture,
    )

    cluster = None
    r_score = 0.0
    priority = 0.0
    valid_to_dt: datetime | None = None
    affected_edge: str | None = None
    explanation: list[str] = scope_explanation + [s.line() for s in signals]

    if itype == "manifestacao":
        leg = compute_legitimacy(veracity=v_score, description=description)
        r_score = leg.score
        priority = leg.score
        from .moderation_policy import get_active_policy

        policy = get_active_policy(db)
        status = _status_for_manifestation(leg.score, policy)
        valid_to_dt = datetime.now(timezone.utc) + timedelta(days=180)
        explanation.extend(leg.explain() + [f"status = {status}"])
    else:
        if category not in EVENT_CATEGORIES:
            category = "outro"
        cluster = find_or_create_cluster(db, category=category, lat=lat, lon=lon)
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
        from .moderation_policy import get_active_policy

        policy = get_active_policy(db)
        status = _status_for_event(
            v_score=v_score,
            category=category,
            policy=policy,
            offline=offline_capture,
            cluster_confirmations=cluster.confirmations,
        )
        from .road_context import ROAD_SCOPE_MUNICIPAL, STATUS_REGISTRO_MUNICIPAL

        if road_scope == ROAD_SCOPE_MUNICIPAL:
            status = STATUS_REGISTRO_MUNICIPAL
        valid_to_dt = datetime.now(timezone.utc) + timedelta(hours=ttl_for(category))
        affected_edge = _osm_id_for(lat, lon)
        # Renovação por confirmação: novas confirmações no mesmo ponto estendem a
        # validade dos reportes ativos do cluster. Silêncio (sem novos reportes)
        # deixa o evento expirar sozinho pelo valid_to.
        if cluster is not None and cluster.confirmations > 1:
            db.execute(
                update(Report)
                .where(
                    Report.cluster_id == cluster.id,
                    Report.status.in_(("publicado", "validado", "em_moderacao")),
                )
                .values(valid_to=valid_to_dt.isoformat())
            )
        explanation.extend(r.explain() + [
            f"P = V·R = {priority:.2f}",
            f"status = {status}",
            f"bloqueante = {is_blocking(category, priority)}",
        ])
        if road_scope == ROAD_SCOPE_MUNICIPAL:
            explanation.append(
                "escopo municipal — registrado internamente para relatórios e exportação "
                "(sem publicação no mapa PLI)"
            )

    rep = Report(
        id=rid,
        client_id=client_id,
        interaction_type=itype,
        category=category,
        magnitude=magnitude or "normal",
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
        cluster_id=cluster.id if cluster else None,
        valid_to=valid_to_dt.isoformat() if valid_to_dt else None,
        affected_edges_json=json.dumps([affected_edge]) if affected_edge else None,
        road_scope=road_scope,
        road_label=road_label,
        road_context_json=json.dumps(road_context, ensure_ascii=False) if road_context else None,
    )
    db.add(rep)
    db.flush()
    return IngestResult(report=rep, explanation=explanation)


def report_to_feature(r: Report) -> dict[str, Any]:
    blocking = (
        r.interaction_type == "evento_trafego"
        and is_blocking(r.category, r.priority)
    )
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
    road_context: dict | None = None
    if r.road_context_json:
        try:
            road_context = json.loads(r.road_context_json)
        except (ValueError, TypeError):
            road_context = None
    return {
        "type": "Feature",
        "geometry": geom,
        "properties": {
            "id": r.id,
            "interaction_type": r.interaction_type,
            "category": r.category,
            "magnitude": r.magnitude,
            "description": r.description,
            "veracity": round(r.veracity_score, 3),
            "relevance": round(r.relevance_score, 3),
            "priority": round(r.priority, 3),
            "status": r.status,
            "blocking": blocking,
            "cluster_id": r.cluster_id,
            "affected_edges": affected,
            "valid_from": r.valid_from,
            "valid_to": r.valid_to,
            "captured_at": r.captured_at,
            "received_at": r.received_at,
            "photo_url": photo_svc.public_url_for(r.photo_path),
            "road_scope": r.road_scope,
            "road_label": r.road_label,
            "road_context": road_context,
        },
    }


def active_public_reports_stmt(*, interaction_type: str | None = None):
    now_iso = datetime.now(timezone.utc).isoformat()
    stmt = (
        select(Report)
        .where(Report.status.in_(tuple(PUBLIC_STATUSES)))
        .where((Report.valid_to.is_(None)) | (Report.valid_to > now_iso))
    )
    if interaction_type:
        stmt = stmt.where(Report.interaction_type == interaction_type)
    return stmt
