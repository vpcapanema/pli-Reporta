"""Política do aprovador automático — configuração global e por categoria."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AuditLog, ModerationPolicy, Report
from .relevance import BLOCKING_CATEGORIES, HIGHWAY_FACTOR, SEVERITY_BASE, TTL_HOURS
from .veracity import WEIGHTS as DEFAULT_WEIGHTS

# ── Labels das categorias ──────────────────────────────────────────────────────

EVENTO_CATEGORIES = [
    {"id": "bloqueio_total",       "label": "Bloqueio total"},
    {"id": "incendio",             "label": "Incêndio"},
    {"id": "acidente",             "label": "Acidente"},
    {"id": "alagamento",           "label": "Alagamento"},
    {"id": "queda_arvore",         "label": "Queda de árvore"},
    {"id": "animal_na_pista",      "label": "Animal na pista"},
    {"id": "obra_grande",          "label": "Obra na pista"},
    {"id": "objeto_na_pista",      "label": "Objeto na pista"},
    {"id": "lentidao_corredor",    "label": "Lentidão no corredor"},
    {"id": "veiculo_quebrado",     "label": "Veículo quebrado"},
    {"id": "sinalizacao_quebrada", "label": "Sinalização quebrada"},
    {"id": "buraco",               "label": "Buraco"},
    {"id": "outro",                "label": "Outro"},
]

MANIF_CATEGORIES = [
    {"id": "elogio",     "label": "Elogio"},
    {"id": "sugestao",   "label": "Sugestão"},
    {"id": "reclamacao", "label": "Reclamação"},
]

# Descricões dos sinais de veracidade para o frontend
SIGNAL_DESCRIPTIONS = {
    "geo_browser":           "Precisão do GPS declarado pelo navegador/app",
    "exif_match":            "Coerência entre GPS e timestamp da foto (EXIF) com o reporte",
    "capture_inapp":         "Foto capturada dentro do app (nonce válido) vs. enviada da galeria",
    "road_snap":             "Proximidade do ponto reportado a uma via conhecida (malha rodoviária estadual)",
    "image_integrity":       "Ausência de sinais de edição por software (Photoshop, GIMP, Snapseed…)",
    "user_reputation":       "Histórico de acertos/erros anteriores do usuário",
    "temporal_plausibility": "Frescor da captura — foto muito antiga reduz confiabilidade",
}

SIGNAL_LABELS = {
    "geo_browser":           "Precisão GPS",
    "exif_match":            "Coerência EXIF",
    "capture_inapp":         "Captura in-app",
    "road_snap":             "Snap à via",
    "image_integrity":       "Integridade da imagem",
    "user_reputation":       "Reputação do usuário",
    "temporal_plausibility": "Atualidade da captura",
}

# Labels dos tipos de via para o frontend
HIGHWAY_LABELS = {
    "motorway":       "Rodovia principal (faixa dupla)",
    "motorway_link":  "Acesso de rodovia principal",
    "trunk":          "Rodovia de acesso / contorno",
    "trunk_link":     "Acesso de rodovia de contorno",
    "primary":        "Avenida / via primária",
    "primary_link":   "Acesso de via primária",
    "secondary":      "Via secundária",
    "secondary_link": "Acesso de via secundária",
    "tertiary":       "Via terciária",
    "tertiary_link":  "Acesso de via terciária",
    "residential":    "Via residencial",
    "unclassified":   "Via sem classificação",
    "service":        "Via de serviço",
    "track":          "Estrada de terra / trilha",
}

PRESET_THRESHOLDS = {
    "cauteloso": {
        "event_publish_min": 0.85,
        "event_discard_below": 0.20,
        "manif_publish_min": 0.85,
        "manif_discard_below": 0.35,
    },
    "equilibrado": {
        "event_publish_min": 0.70,
        "event_discard_below": 0.30,
        "manif_publish_min": 0.75,
        "manif_discard_below": 0.40,
    },
    "agil": {
        "event_publish_min": 0.55,
        "event_discard_below": 0.40,
        "manif_publish_min": 0.60,
        "manif_discard_below": 0.50,
    },
}


# ── ActivePolicy ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ActivePolicy:
    preset: str
    event_publish_min: float
    event_discard_below: float
    manif_publish_min: float
    manif_discard_below: float
    always_review_blocking: bool
    always_review_offline: bool
    always_review_first_in_area: bool
    always_review_other: bool

    @property
    def auto_publish_threshold(self) -> float:
        return self.event_publish_min

    @property
    def auto_discard_threshold(self) -> float:
        return self.event_discard_below

    @property
    def manifestation_publish_threshold(self) -> float:
        return self.manif_publish_min

    @property
    def manifestation_discard_threshold(self) -> float:
        return self.manif_discard_below


def _defaults_from_env() -> ActivePolicy:
    return ActivePolicy(
        preset="equilibrado",
        event_publish_min=settings.auto_publish_threshold,
        event_discard_below=settings.auto_discard_threshold,
        manif_publish_min=settings.manifestation_publish_threshold,
        manif_discard_below=settings.manifestation_discard_threshold,
        always_review_blocking=True,
        always_review_offline=True,
        always_review_first_in_area=False,
        always_review_other=True,
    )


def _row_to_active(row: ModerationPolicy) -> ActivePolicy:
    return ActivePolicy(
        preset=row.preset,
        event_publish_min=row.event_publish_min,
        event_discard_below=row.event_discard_below,
        manif_publish_min=row.manif_publish_min,
        manif_discard_below=row.manif_discard_below,
        always_review_blocking=bool(row.always_review_blocking),
        always_review_offline=bool(row.always_review_offline),
        always_review_first_in_area=bool(row.always_review_first_in_area),
        always_review_other=bool(row.always_review_other),
    )


def ensure_default_policy(db: Session) -> ModerationPolicy:
    row = db.get(ModerationPolicy, 1)
    if row:
        return row
    d = _defaults_from_env()
    row = ModerationPolicy(
        id=1,
        preset=d.preset,
        event_publish_min=d.event_publish_min,
        event_discard_below=d.event_discard_below,
        manif_publish_min=d.manif_publish_min,
        manif_discard_below=d.manif_discard_below,
        always_review_blocking=1 if d.always_review_blocking else 0,
        always_review_offline=1 if d.always_review_offline else 0,
        always_review_first_in_area=1 if d.always_review_first_in_area else 0,
        always_review_other=1 if d.always_review_other else 0,
        category_overrides_json=None,
        veracity_weights_json=None,
        highway_factors_json=None,
        updated_at=datetime.now(timezone.utc).isoformat(),
        updated_by=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_active_policy(db: Session | None = None) -> ActivePolicy:
    if db is None:
        from ..database import session_scope

        with session_scope() as scoped:
            row = ensure_default_policy(scoped)
            return _row_to_active(row)
    row = ensure_default_policy(db)
    return _row_to_active(row)


# ── Helpers de leitura de JSON ─────────────────────────────────────────────────

def _pct(value: float) -> int:
    return int(round(value * 100))


def _load_overrides(row: ModerationPolicy) -> dict:
    raw = getattr(row, "category_overrides_json", None)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}


def _load_veracity_weights(row: ModerationPolicy) -> dict[str, float]:
    raw = getattr(row, "veracity_weights_json", None)
    if not raw:
        return dict(DEFAULT_WEIGHTS)
    try:
        stored = json.loads(raw)
        # Merge: valores ausentes ficam com o default
        merged = dict(DEFAULT_WEIGHTS)
        merged.update({k: float(v) for k, v in stored.items() if k in merged})
        return merged
    except (ValueError, TypeError):
        return dict(DEFAULT_WEIGHTS)


def _load_highway_factors(row: ModerationPolicy) -> dict[str, float]:
    raw = getattr(row, "highway_factors_json", None)
    if not raw:
        return dict(HIGHWAY_FACTOR)
    try:
        stored = json.loads(raw)
        merged = dict(HIGHWAY_FACTOR)
        merged.update({k: float(v) for k, v in stored.items() if k in merged})
        return merged
    except (ValueError, TypeError):
        return dict(HIGHWAY_FACTOR)


# ── Payload amigável completo ──────────────────────────────────────────────────

def friendly_policy_payload(active: ActivePolicy, row: ModerationPolicy | None = None) -> dict:
    overrides = _load_overrides(row) if row else {}
    ev_ov = overrides.get("evento", {})
    mn_ov = overrides.get("manif", {})

    weights = _load_veracity_weights(row) if row else dict(DEFAULT_WEIGHTS)
    hw_factors = _load_highway_factors(row) if row else dict(HIGHWAY_FACTOR)

    global_cfg = {
        "event_publish_min":         _pct(active.event_publish_min),
        "event_discard_below":       _pct(active.event_discard_below),
        "manif_publish_min":         _pct(active.manif_publish_min),
        "manif_discard_below":       _pct(active.manif_discard_below),
        "always_review_blocking":    active.always_review_blocking,
        "always_review_offline":     active.always_review_offline,
        "always_review_first_in_area": active.always_review_first_in_area,
        "always_review_other":       active.always_review_other,
    }

    # Sinais de veracidade com pesos atuais (em %)
    total_w = sum(weights.values()) or 1.0
    sinais_veracidade = [
        {
            "id":         sig,
            "label":      SIGNAL_LABELS.get(sig, sig),
            "descricao":  SIGNAL_DESCRIPTIONS.get(sig, ""),
            "peso":       round(weights.get(sig, 0.0) * 100 / total_w, 1),
            "peso_raw":   round(weights.get(sig, 0.0), 4),
        }
        for sig in DEFAULT_WEIGHTS
    ]

    # Fatores por tipo de via (em %)
    fatores_via = [
        {
            "id":     hw,
            "label":  HIGHWAY_LABELS.get(hw, hw),
            "fator":  round(hw_factors.get(hw, 0.0) * 100),
        }
        for hw in HIGHWAY_FACTOR
    ]

    # Categorias de evento
    categorias_evento = []
    for cat in EVENTO_CATEGORIES:
        cid = cat["id"]
        ov = ev_ov.get(cid, {})

        if "sempre_revisar" in ov:
            sempre_rev = bool(ov["sempre_revisar"])
        elif cid in BLOCKING_CATEGORIES:
            sempre_rev = active.always_review_blocking
        elif cid == "outro":
            sempre_rev = active.always_review_other
        else:
            sempre_rev = False

        categorias_evento.append({
            "id":               cid,
            "label":            cat["label"],
            "severidade_base":  round(ov.get("severidade_base", SEVERITY_BASE.get(cid, 0.3)) * 100),
            "ttl_horas":        ov.get("ttl_horas", TTL_HOURS.get(cid, 168)),
            "sempre_revisar":   sempre_rev,
            "limiar_publicar":  ov.get("limiar_publicar"),
            "limiar_descartar": ov.get("limiar_descartar"),
        })

    # Categorias de manifestação
    categorias_manif = []
    for cat in MANIF_CATEGORIES:
        cid = cat["id"]
        ov = mn_ov.get(cid, {})
        categorias_manif.append({
            "id":               cid,
            "label":            cat["label"],
            "sempre_revisar":   bool(ov.get("sempre_revisar", False)),
            "limiar_publicar":  ov.get("limiar_publicar"),
            "limiar_descartar": ov.get("limiar_descartar"),
        })

    return {
        "preset": active.preset,
        "eventos": {
            "publicar_sozinho": _pct(active.event_publish_min),
            "arquivar_sozinho": _pct(active.event_discard_below),
            "revisar_bloqueios": active.always_review_blocking,
            "revisar_offline": active.always_review_offline,
            "revisar_primeiro_na_area": active.always_review_first_in_area,
            "revisar_outro": active.always_review_other,
        },
        "manifestacoes": {
            "publicar_sozinho": _pct(active.manif_publish_min),
            "arquivar_sozinho": _pct(active.manif_discard_below),
        },
        "global":              global_cfg,
        "sinais_veracidade":   sinais_veracidade,
        "fatores_via":         fatores_via,
        "categorias_evento":   categorias_evento,
        "categorias_manif":    categorias_manif,
    }


# ── Atualização da política ────────────────────────────────────────────────────

def update_policy(db: Session, *, payload: dict, actor: str) -> tuple[ActivePolicy, ModerationPolicy]:
    row = ensure_default_policy(db)

    preset = payload.get("preset")
    if preset in PRESET_THRESHOLDS:
        row.preset = preset

    # Configuração global — limiares e flags
    g = payload.get("global") or {}
    if "event_publish_min" in g:
        row.event_publish_min = float(g["event_publish_min"]) / 100.0
    if "event_discard_below" in g:
        row.event_discard_below = float(g["event_discard_below"]) / 100.0
    if "manif_publish_min" in g:
        row.manif_publish_min = float(g["manif_publish_min"]) / 100.0
    if "manif_discard_below" in g:
        row.manif_discard_below = float(g["manif_discard_below"]) / 100.0
    if "always_review_blocking" in g:
        row.always_review_blocking = 1 if g["always_review_blocking"] else 0
    if "always_review_offline" in g:
        row.always_review_offline = 1 if g["always_review_offline"] else 0
    if "always_review_first_in_area" in g:
        row.always_review_first_in_area = 1 if g["always_review_first_in_area"] else 0
    if "always_review_other" in g:
        row.always_review_other = 1 if g["always_review_other"] else 0

    # Pesos dos sinais de veracidade
    weights_update = payload.get("sinais_veracidade") or []
    if weights_update:
        current_w = _load_veracity_weights(row)
        for s in weights_update:
            sid = s.get("id")
            if sid and sid in current_w and "peso" in s:
                current_w[sid] = float(s["peso"]) / 100.0
        # Normaliza para que a soma seja 1.0
        total = sum(current_w.values()) or 1.0
        normalized = {k: round(v / total, 6) for k, v in current_w.items()}
        row.veracity_weights_json = json.dumps(normalized, ensure_ascii=False)

    # Fatores de via
    via_update = payload.get("fatores_via") or []
    if via_update:
        current_hw = _load_highway_factors(row)
        for h in via_update:
            hid = h.get("id")
            if hid and hid in current_hw and "fator" in h:
                current_hw[hid] = float(h["fator"]) / 100.0
        row.highway_factors_json = json.dumps(current_hw, ensure_ascii=False)

    # Per-categoria: merge no JSON existente
    existing = _load_overrides(row)

    ev_updates = payload.get("categorias_evento") or []
    mn_updates = payload.get("categorias_manif") or []

    if ev_updates:
        ev_ov = existing.setdefault("evento", {})
        for cat in ev_updates:
            cid = cat.get("id")
            if not cid:
                continue
            entry = ev_ov.setdefault(cid, {})
            for field in ("ttl_horas", "sempre_revisar", "limiar_publicar",
                          "limiar_descartar", "severidade_base"):
                if field not in cat:
                    continue
                val = cat[field]
                if val is None:
                    entry.pop(field, None)
                elif field == "severidade_base":
                    entry[field] = float(val) / 100.0
                else:
                    entry[field] = val
            if not entry:
                ev_ov.pop(cid, None)
        _sync_legacy_flags(row, ev_ov)

    if mn_updates:
        mn_ov = existing.setdefault("manif", {})
        for cat in mn_updates:
            cid = cat.get("id")
            if not cid:
                continue
            entry = mn_ov.setdefault(cid, {})
            for field in ("sempre_revisar", "limiar_publicar", "limiar_descartar"):
                if field in cat:
                    if cat[field] is None:
                        entry.pop(field, None)
                    else:
                        entry[field] = cat[field]
            if not entry:
                mn_ov.pop(cid, None)

    if ev_updates or mn_updates:
        row.category_overrides_json = json.dumps(existing, ensure_ascii=False)

    row.updated_at = datetime.now(timezone.utc).isoformat()
    row.updated_by = actor
    db.add(AuditLog(
        actor=actor,
        action="policy:update",
        target_type="moderation_policy",
        target_id="1",
        payload_json=json.dumps(payload, ensure_ascii=False),
    ))
    db.commit()
    db.refresh(row)
    return _row_to_active(row), row


def _sync_legacy_flags(row: ModerationPolicy, ev_ov: dict) -> None:
    blocking = {cid for cid in BLOCKING_CATEGORIES if ev_ov.get(cid, {}).get("sempre_revisar") is True}
    not_blocking = {cid for cid in BLOCKING_CATEGORIES if ev_ov.get(cid, {}).get("sempre_revisar") is False}
    if len(blocking) == len(BLOCKING_CATEGORIES):
        row.always_review_blocking = 1
    elif len(not_blocking) == len(BLOCKING_CATEGORIES):
        row.always_review_blocking = 0
    if "outro" in ev_ov and "sempre_revisar" in ev_ov["outro"]:
        row.always_review_other = 1 if ev_ov["outro"]["sempre_revisar"] else 0


# ── Simulação ──────────────────────────────────────────────────────────────────

def simulate_policy(db: Session, active: ActivePolicy, days: int = 7,
                    row: ModerationPolicy | None = None) -> dict:
    overrides = _load_overrides(row) if row else {}
    ev_ov = overrides.get("evento", {})

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = db.execute(
        select(Report).where(Report.received_at >= since)
    ).scalars().all()

    counts: dict[str, int] = {"publicado": 0, "descartado": 0, "em_moderacao": 0}
    examples: list[dict] = []

    for r in rows:
        offline = bool(r.capture_nonce_valid == 0)
        if r.interaction_type == "manifestacao":
            sim = _would_status_manifestation(policy=active, l_score=r.relevance_score)
        else:
            sim = _would_status_event(
                policy=active,
                v_score=r.veracity_score,
                category=r.category,
                offline=offline,
                cluster_confirmations=1,
                cat_overrides=ev_ov,
            )
        counts[sim] = counts.get(sim, 0) + 1
        if sim == "em_moderacao" and len(examples) < 5:
            examples.append({"id": r.id, "motivo": _human_reason(r, sim, active)})

    return {
        "periodo_dias":    days,
        "total":           len(rows),
        "publicados_auto": counts.get("publicado", 0),
        "arquivados_auto": counts.get("descartado", 0),
        "sua_fila":        counts.get("em_moderacao", 0),
        "exemplos_fila":   examples,
    }


def _would_status_event(
    *,
    policy: ActivePolicy,
    v_score: float,
    category: str,
    offline: bool,
    cluster_confirmations: int,
    cat_overrides: dict | None = None,
) -> str:
    ov = (cat_overrides or {}).get(category, {})
    disc = (ov["limiar_descartar"] / 100.0) if ov.get("limiar_descartar") is not None else policy.event_discard_below
    pub = (ov["limiar_publicar"] / 100.0) if ov.get("limiar_publicar") is not None else policy.event_publish_min

    if v_score < disc:
        return "descartado"

    if "sempre_revisar" in ov:
        always_rev = bool(ov["sempre_revisar"])
    else:
        always_rev = (
            (policy.always_review_blocking and category in BLOCKING_CATEGORIES)
            or (policy.always_review_other and category == "outro")
        )

    if always_rev:
        return "em_moderacao"
    if policy.always_review_first_in_area and cluster_confirmations <= 1:
        return "em_moderacao"

    status = "publicado" if v_score >= pub else "em_moderacao"
    if policy.always_review_offline and offline and status == "publicado":
        return "em_moderacao"
    return status


def _would_status_manifestation(*, policy: ActivePolicy, l_score: float) -> str:
    if l_score < policy.manif_discard_below:
        return "descartado"
    if l_score < policy.manif_publish_min:
        return "em_moderacao"
    return "publicado"


def _human_reason(report: Report, status: str, policy: ActivePolicy) -> str:
    if status != "em_moderacao":
        return ""
    if report.category in BLOCKING_CATEGORIES and policy.always_review_blocking:
        return "Bloqueio/incêndio/alagamento - revisão obrigatória"
    if report.category == "outro" and policy.always_review_other:
        return "Categoria «outro» - sistema preferiu não decidir sozinho"
    if report.interaction_type == "manifestacao":
        return "Confiança intermediária no comentário"
    return "Confiança intermediária - encaminhado para revisão"
