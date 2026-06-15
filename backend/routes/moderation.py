"""Endpoints de gestão e moderação (Bearer token de gestor)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import AuditLog, Report
from ..schemas import ModerationDecision, ModerationPolicyUpdate
from ..services import auth as auth_svc
from .moderation_helpers import report_detail as build_report_detail
from .moderation_helpers import report_summary
from ..services.moderation_policy import (
    ensure_default_policy,
    friendly_policy_payload,
    get_active_policy,
    simulate_policy,
    update_policy,
)
from ..services.pipeline import report_to_feature
from ..services.report_catalog import catalog_payload
from ..services.road_context import MANAGER_REVIEW_SCOPES, STATUS_REGISTRO_MUNICIPAL

router = APIRouter()


def _manager_queue_filter():
    """Fila do gestor: manifestações + eventos em rodovia estadual/federal."""
    return (
        (Report.interaction_type == "manifestacao")
        | (Report.road_scope.in_(tuple(MANAGER_REVIEW_SCOPES)))
    )


def require_moderator(
    authorization: str | None = Header(default=None),
) -> auth_svc.ModeratorSession:
    if not auth_svc.auth_configured():
        raise HTTPException(503, detail="Acesso restrito não configurado.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail="Sessão não autenticada.")
    token = authorization[7:].strip()
    session = auth_svc.verify_session_token(token)
    if not session:
        raise HTTPException(401, detail="Sessão expirada ou inválida.")
    return session


@router.get("/moderation/catalog")
def moderation_catalog(
    _moderator: auth_svc.ModeratorSession = Depends(require_moderator),
) -> dict:
    return catalog_payload()


@router.get("/moderation/stats")
def moderation_stats(
    db: Session = Depends(get_session),
    _moderator: auth_svc.ModeratorSession = Depends(require_moderator),
) -> dict:
    rows = db.execute(
        select(Report.status, func.count())  # pylint: disable=not-callable
        .group_by(Report.status)
    ).all()
    by_status = {status: int(n) for status, n in rows}
    fila = db.execute(
        select(func.count())  # pylint: disable=not-callable
        .select_from(Report)
        .where(Report.status == "em_moderacao", _manager_queue_filter())
    ).scalar_one()
    return {
        "fila": fila,
        "publicados": by_status.get("publicado", 0),
        "arquivados": by_status.get("descartado", 0),
        "registros_municipais": by_status.get(STATUS_REGISTRO_MUNICIPAL, 0),
        "total": sum(by_status.values()),
        "by_status": by_status,
    }


@router.get("/moderation/policy")
def get_policy(
    db: Session = Depends(get_session),
    _moderator: auth_svc.ModeratorSession = Depends(require_moderator),
) -> dict:
    row = ensure_default_policy(db)
    active = get_active_policy(db)
    return friendly_policy_payload(active, row)


@router.patch("/moderation/policy")
def patch_policy(
    body: ModerationPolicyUpdate,
    db: Session = Depends(get_session),
    moderator: auth_svc.ModeratorSession = Depends(require_moderator),
) -> dict:
    actor = f"moderator:{moderator.user_id}:{moderator.username}"
    raw = body.model_dump(exclude_none=True)

    # Normaliza payload legado → novo formato
    payload: dict = {}
    if raw.get("global_config"):
        payload["global"] = raw["global_config"]
    if raw.get("sinais_veracidade"):
        payload["sinais_veracidade"] = raw["sinais_veracidade"]
    if raw.get("fatores_via"):
        payload["fatores_via"] = raw["fatores_via"]
    if raw.get("categorias_evento"):
        payload["categorias_evento"] = raw["categorias_evento"]
    if raw.get("categorias_manif"):
        payload["categorias_manif"] = raw["categorias_manif"]

    # Legado: preset
    if raw.get("preset"):
        payload["preset"] = raw["preset"]
        from ..services.moderation_policy import PRESET_THRESHOLDS
        t = PRESET_THRESHOLDS.get(raw["preset"], {})
        if t:
            g = payload.setdefault("global", {})
            g.update({
                "event_publish_min":  int(t["event_publish_min"] * 100),
                "event_discard_below": int(t["event_discard_below"] * 100),
                "manif_publish_min":  int(t["manif_publish_min"] * 100),
                "manif_discard_below": int(t["manif_discard_below"] * 100),
            })

    # Legado: eventos / manifestacoes
    if raw.get("eventos"):
        ev = raw["eventos"]
        g = payload.setdefault("global", {})
        if "publicar_sozinho" in ev:
            g["event_publish_min"] = int(ev["publicar_sozinho"])
        if "arquivar_sozinho" in ev:
            g["event_discard_below"] = int(ev["arquivar_sozinho"])
    if raw.get("manifestacoes"):
        mn = raw["manifestacoes"]
        g = payload.setdefault("global", {})
        if "publicar_sozinho" in mn:
            g["manif_publish_min"] = int(mn["publicar_sozinho"])
        if "arquivar_sozinho" in mn:
            g["manif_discard_below"] = int(mn["arquivar_sozinho"])

    active, row = update_policy(db, payload=payload, actor=actor)
    return friendly_policy_payload(active, row)


@router.post("/moderation/policy/simulate")
def policy_simulate(
    db: Session = Depends(get_session),
    _moderator: auth_svc.ModeratorSession = Depends(require_moderator),
    days: int = Query(default=7, ge=1, le=90),
) -> dict:
    row = ensure_default_policy(db)
    active = get_active_policy(db)
    return simulate_policy(db, active, days=days, row=row)


@router.get("/moderation/reports")
def list_reports(
    db: Session = Depends(get_session),
    _moderator: auth_svc.ModeratorSession = Depends(require_moderator),
    interaction_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    road_scope: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    filters = []
    if interaction_type:
        filters.append(Report.interaction_type == interaction_type)
    if status:
        filters.append(Report.status == status)
    if road_scope:
        filters.append(Report.road_scope == road_scope.strip().lower())
    total = db.execute(
        select(func.count()).select_from(Report).where(*filters)  # pylint: disable=not-callable
    ).scalar_one()
    rows = db.execute(
        select(Report)
        .where(*filters)
        .order_by(Report.received_at.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()
    return {
        "total": int(total),
        "offset": offset,
        "limit": limit,
        "items": [report_summary(r) for r in rows],
    }


@router.get("/moderation/reports.geojson")
def reports_geojson(
    db: Session = Depends(get_session),
    _moderator: auth_svc.ModeratorSession = Depends(require_moderator),
    interaction_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    road_scope: str | None = Query(default=None),
) -> dict:
    stmt = select(Report).order_by(Report.received_at.desc()).limit(2000)
    if interaction_type:
        stmt = stmt.where(Report.interaction_type == interaction_type)
    if status:
        stmt = stmt.where(Report.status == status)
    if road_scope:
        stmt = stmt.where(Report.road_scope == road_scope.strip().lower())
    rows = db.execute(stmt).scalars().all()
    return {
        "type": "FeatureCollection",
        "features": [report_to_feature(r) for r in rows],
    }


@router.get("/moderation/municipal.geojson")
def municipal_geojson(
    db: Session = Depends(get_session),
    _moderator: auth_svc.ModeratorSession = Depends(require_moderator),
    since: str | None = Query(default=None, description="ISO 8601 — received_at mínimo"),
    municipio: str | None = Query(default=None, description="Filtrar por nome do município"),
    limit: int = Query(default=50000, ge=1, le=50000),
) -> dict:
    """Camada interna de eventos municipais para relatórios e exportação às prefeituras."""
    stmt = (
        select(Report)
        .where(
            Report.status == STATUS_REGISTRO_MUNICIPAL,
            Report.interaction_type == "evento_trafego",
        )
        .order_by(Report.received_at.desc())
        .limit(limit)
    )
    if since:
        stmt = stmt.where(Report.received_at >= since)
    rows = db.execute(stmt).scalars().all()
    features = []
    for r in rows:
        if municipio:
            ctx = {}
            if r.road_context_json:
                try:
                    ctx = json.loads(r.road_context_json)
                except (ValueError, TypeError):
                    ctx = {}
            mun = str(ctx.get("municipio") or r.road_label or "").strip().lower()
            if municipio.strip().lower() not in mun:
                continue
        features.append(report_to_feature(r))
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "scope": "municipal",
            "status": STATUS_REGISTRO_MUNICIPAL,
            "count": len(features),
        },
    }


@router.get("/moderation/reports/{report_id}")
def report_detail(
    report_id: str,
    db: Session = Depends(get_session),
    _moderator: auth_svc.ModeratorSession = Depends(require_moderator),
) -> dict:
    rep = db.get(Report, report_id)
    if not rep:
        raise HTTPException(404, detail="Reporte não encontrado.")
    return build_report_detail(rep, db)


@router.get("/moderation/queue")
def queue(
    db: Session = Depends(get_session),
    moderator: auth_svc.ModeratorSession = Depends(require_moderator),
) -> dict:
    rows = db.execute(
        select(Report)
        .where(Report.status == "em_moderacao", _manager_queue_filter())
        .order_by(Report.priority.desc(), Report.received_at.asc())
        .limit(100)
    ).scalars().all()
    items = []
    for r in rows:
        signals = json.loads(r.veracity_signals_json or "{}")
        items.append({
            **report_summary(r),
            "signals": signals,
        })
    return {
        "queue_size": len(items),
        "items": items,
        "moderator": moderator.username,
        "moderator_id": moderator.user_id,
    }


@router.post("/moderation/{report_id}/decide")
def decide(
    report_id: str,
    decision: ModerationDecision,
    db: Session = Depends(get_session),
    moderator: auth_svc.ModeratorSession = Depends(require_moderator),
) -> dict:
    rep = db.get(Report, report_id)
    if not rep:
        raise HTTPException(404, detail="Reporte não encontrado.")
    if rep.status != "em_moderacao":
        raise HTTPException(409, detail=f"Status atual não permite decidir: {rep.status}")
    if (
        rep.interaction_type == "evento_trafego"
        and (rep.road_scope or "").strip().lower() not in MANAGER_REVIEW_SCOPES
    ):
        raise HTTPException(
            409,
            detail="Este reporte não está na fila do gestor (escopo municipal ou sem malha DER).",
        )

    rep.status = "publicado" if decision.decision == "publicar" else "descartado"
    db.add(AuditLog(
        ts=datetime.now(timezone.utc).isoformat(),
        actor=f"moderator:{moderator.user_id}:{moderator.username}",
        action=f"decide:{decision.decision}",
        target_type="report",
        target_id=report_id,
        payload_json=json.dumps({"note": decision.note}, ensure_ascii=False),
    ))
    db.commit()
    return {"id": rep.id, "status": rep.status}
