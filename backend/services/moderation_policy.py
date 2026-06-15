"""Política do aprovador automático — presets e linguagem amigável."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AuditLog, ModerationPolicy, Report
from .relevance import BLOCKING_CATEGORIES

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

CONSIDERA_EVENTO_PUBLICAR = [
    "Foto tirada no aplicativo (não só da galeria)",
    "Localização do celular coerente com o reporte",
    "Precisão razoável do GPS",
    "Data da foto compatível com o horário informado, quando possível",
    "Histórico positivo do dispositivo, quando existir",
    "Outros reportes parecidos no mesmo lugar reforçam a confiança",
]

CONSIDERA_EVENTO_ARQUIVAR = [
    "Mesma foto já usada em outro reporte",
    "Localização incoerente ou impossível",
    "Confiança geral muito baixa",
    "Categoria vaga com pouca evidência",
]

CONSIDERA_MANIF_PUBLICAR = [
    "Texto com tamanho adequado e claro",
    "Conteúdo condizente com elogio, sugestão ou reclamação",
    "Linguagem adequada, sem spam óbvio",
    "Foto e local coerentes com o comentário",
]

CONSIDERA_MANIF_ARQUIVAR = [
    "Texto muito curto ou vazio",
    "Comentário genérico sem relação com a via",
    "Incoerência entre tipo escolhido e texto",
]

AUTO_NUNCA_FILA = [
    "Foto já usada antes → arquivada automaticamente",
    "Local impossível ou incoerente → arquivada",
    "Eventos muito confiáveis → publicados sozinhos",
    "Comentários claros e adequados → publicados sozinhos",
]

# Definições dos 7 sinais de veracidade para exibição amigável
SINAIS_VERACIDADE = [
    {
        "id": "capture_inapp",
        "label": "Foto tirada no app",
        "peso": 20,
        "como": "Captura direta no app: 20 pts · Importada da galeria: 8 pts",
    },
    {
        "id": "geo_browser",
        "label": "Precisão do GPS",
        "peso": 20,
        "como": "< 50 m: 20 pts · 50–200 m: 10 pts · > 200 m: 2 pts · Sem GPS: 8 pts",
    },
    {
        "id": "image_integrity",
        "label": "Integridade da imagem",
        "peso": 15,
        "como": "Sem edição detectada: 15 pts · Software de edição encontrado: 0 pts",
    },
    {
        "id": "exif_match",
        "label": "GPS da foto coerente com o local",
        "peso": 15,
        "como": "EXIF bate com local declarado (< 100 m): 15 pts · Parcial: 8 pts · Incoerente: 2 pts · Sem EXIF: 8 pts",
    },
    {
        "id": "road_snap",
        "label": "Ponto sobre uma via",
        "peso": 10,
        "como": "< 30 m da via: 10 pts · < 100 m: 6 pts · < 200 m: 3 pts · Fora de via: 0 pts",
    },
    {
        "id": "user_reputation",
        "label": "Histórico do dispositivo",
        "peso": 10,
        "como": "De 0 a 10 pts conforme reportes anteriores aprovados pelo sistema",
    },
    {
        "id": "temporal_plausibility",
        "label": "Atualidade da captura",
        "peso": 10,
        "como": "≤ 30 min: 10 pts · ≤ 2 h: 6 pts · ≤ 24 h: 4 pts · Mais antigo: 2 pts",
    },
]

# Critérios de pontuação das manifestações (score L = V × conteúdo × escopo)
SINAIS_LEGITIMIDADE = [
    {
        "id": "veracidade",
        "label": "Confiança na localização e foto",
        "peso": "base",
        "como": "Mesmos 7 critérios dos eventos (0–100 pts) — servem de base multiplicadora",
    },
    {
        "id": "conteudo",
        "label": "Qualidade do texto",
        "peso": "×fator",
        "como": "≥ 40 chars descritivos: ×1,0 · Adequado (15–40): ×0,75 · Genérico: ×0,5 · Curto (< 15 chars): ×0,2 · Spam: ×0",
    },
]


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


def _pct(value: float) -> int:
    return int(round(value * 100))


def _slider_block(
    *,
    titulo: str,
    descricao: str,
    valor_pct: int,
    considera: list[str],
) -> dict:
    return {
        "titulo": titulo,
        "descricao": descricao,
        "valor": valor_pct,
        "considera": considera,
    }


def friendly_policy_payload(active: ActivePolicy) -> dict:
    presets = [
        {"id": "cauteloso", "label": "Mais cauteloso", "descricao": "Publica menos sozinho; mais reportes chegam para você"},
        {"id": "equilibrado", "label": "Equilibrado", "descricao": "Recomendado — equilibra automático e fila humana"},
        {"id": "agil", "label": "Mais ágil", "descricao": "Publica quase tudo confiável; fila mínima"},
    ]
    return {
        "preset": active.preset,
        "presets": presets,
        "intro": (
            "O PLI Reporta analisa cada envio antes de chegar a você. "
            "A maioria é publicada ou arquivada automaticamente. "
            "Só os casos difíceis ou sensíveis entram na sua fila."
        ),
        "eventos": {
            "publicar_sozinho": _slider_block(
                titulo="Confiança mínima para publicar evento sozinho",
                descricao="Quão seguro o sistema precisa estar para colocar no mapa sem passar por você",
                valor_pct=_pct(active.event_publish_min),
                considera=CONSIDERA_EVENTO_PUBLICAR,
            ),
            "arquivar_sozinho": _slider_block(
                titulo="Quando arquivar evento sem olhar",
                descricao="Quando o sistema pode descartar sozinho, sem incomodar você",
                valor_pct=_pct(active.event_discard_below),
                considera=CONSIDERA_EVENTO_ARQUIVAR,
            ),
            "sempre_revisar": {
                "bloqueio_alagamento": active.always_review_blocking,
                "envio_offline": active.always_review_offline,
                "primeiro_na_regiao": active.always_review_first_in_area,
                "categoria_outro": active.always_review_other,
            },
        },
        "manifestacoes": {
            "publicar_sozinho": _slider_block(
                titulo="Confiança mínima para publicar manifestação sozinho",
                descricao="O comentário precisa estar claro e adequado para ir ao mapa sem revisão",
                valor_pct=_pct(active.manif_publish_min),
                considera=CONSIDERA_MANIF_PUBLICAR,
            ),
            "arquivar_sozinho": _slider_block(
                titulo="Quando arquivar manifestação sem olhar",
                descricao="Quando o comentário é claramente inadequado",
                valor_pct=_pct(active.manif_discard_below),
                considera=CONSIDERA_MANIF_ARQUIVAR,
            ),
        },
        "auto_nunca_filas": AUTO_NUNCA_FILA,
        "sinais_evento": SINAIS_VERACIDADE,
        "sinais_manif": SINAIS_LEGITIMIDADE,
    }


def apply_preset(preset: str) -> dict[str, float]:
    if preset not in PRESET_THRESHOLDS:
        raise ValueError(f"preset inválido: {preset}")
    return PRESET_THRESHOLDS[preset]


def update_policy(
    db: Session,
    *,
    payload: dict,
    actor: str,
) -> ActivePolicy:
    row = ensure_default_policy(db)
    if "preset" in payload and payload["preset"]:
        preset = payload["preset"]
        if preset in PRESET_THRESHOLDS:
            row.preset = preset
            for k, v in PRESET_THRESHOLDS[preset].items():
                setattr(row, k, v)
    ev = payload.get("eventos") or {}
    if "publicar_sozinho" in ev:
        row.event_publish_min = float(ev["publicar_sozinho"]) / 100.0
    if "arquivar_sozinho" in ev:
        row.event_discard_below = float(ev["arquivar_sozinho"]) / 100.0
    rev = ev.get("sempre_revisar") or {}
    if "bloqueio_alagamento" in rev:
        row.always_review_blocking = 1 if rev["bloqueio_alagamento"] else 0
    if "envio_offline" in rev:
        row.always_review_offline = 1 if rev["envio_offline"] else 0
    if "primeiro_na_regiao" in rev:
        row.always_review_first_in_area = 1 if rev["primeiro_na_regiao"] else 0
    if "categoria_outro" in rev:
        row.always_review_other = 1 if rev["categoria_outro"] else 0
    man = payload.get("manifestacoes") or {}
    if "publicar_sozinho" in man:
        row.manif_publish_min = float(man["publicar_sozinho"]) / 100.0
    if "arquivar_sozinho" in man:
        row.manif_discard_below = float(man["arquivar_sozinho"]) / 100.0
    row.updated_at = datetime.now(timezone.utc).isoformat()
    row.updated_by = actor
    db.add(
        AuditLog(
            actor=actor,
            action="policy:update",
            target_type="moderation_policy",
            target_id="1",
            payload_json=str(payload),
        )
    )
    db.commit()
    db.refresh(row)
    return _row_to_active(row)


def _would_status_event(
    *,
    policy: ActivePolicy,
    v_score: float,
    category: str,
    offline: bool,
    cluster_confirmations: int,
) -> str:
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


def _would_status_manifestation(*, policy: ActivePolicy, l_score: float) -> str:
    if l_score < policy.manif_discard_below:
        return "descartado"
    if l_score < policy.manif_publish_min:
        return "em_moderacao"
    return "publicado"


def simulate_policy(db: Session, policy: ActivePolicy, days: int = 7) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = db.execute(
        select(Report).where(Report.received_at >= since)
    ).scalars().all()
    counts = {"publicado": 0, "descartado": 0, "em_moderacao": 0}
    examples: list[dict] = []
    for r in rows:
        offline = bool(r.capture_nonce_valid == 0)
        confirmations = 1
        if r.interaction_type == "manifestacao":
            sim = _would_status_manifestation(policy=policy, l_score=r.relevance_score)
        else:
            sim = _would_status_event(
                policy=policy,
                v_score=r.veracity_score,
                category=r.category,
                offline=offline,
                cluster_confirmations=confirmations,
            )
        counts[sim] = counts.get(sim, 0) + 1
        if sim == "em_moderacao" and len(examples) < 5:
            examples.append({
                "id": r.id,
                "motivo": _human_reason(r, sim, policy),
            })
    return {
        "periodo_dias": days,
        "total": len(rows),
        "publicados_auto": counts.get("publicado", 0),
        "arquivados_auto": counts.get("descartado", 0),
        "sua_fila": counts.get("em_moderacao", 0),
        "exemplos_fila": examples,
    }


def _human_reason(report: Report, status: str, policy: ActivePolicy) -> str:
    if status != "em_moderacao":
        return ""
    if report.category in BLOCKING_CATEGORIES and policy.always_review_blocking:
        return "Bloqueio ou alagamento — sempre passa por revisão humana"
    if report.category == "outro" and policy.always_review_other:
        return "Categoria «outro» — o sistema preferiu não decidir sozinho"
    if report.interaction_type == "manifestacao":
        return "Confiança intermediária no comentário — preferiu enviar para você"
    return "Confiança intermediária — o sistema preferiu não decidir sozinho"
