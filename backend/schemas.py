"""Pydantic schemas para a API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CategoryT = Literal[
    "bloqueio_total",
    "acidente",
    "incendio",
    "animal_na_pista",
    "objeto_na_pista",
    "queda_arvore",
    "veiculo_quebrado",
    "alagamento",
    "obra_grande",
    "lentidao_corredor",
    "sinalizacao_quebrada",
    "buraco",
    "outro",
]
ManifestationT = Literal["elogio", "sugestao", "reclamacao"]
InteractionT = Literal["evento_trafego", "manifestacao"]
MagnitudeT = Literal["leve", "normal", "grave"]


class CaptureNonceResponse(BaseModel):
    nonce: str
    expires_in: int


class ReportCreated(BaseModel):
    id: str
    status: str
    interaction_type: str
    message: str
    veracity_score: float
    relevance_score: float
    priority: float
    explanation: list[str]
    cluster_id: str | None
    valid_to: str | None
    road_scope: str | None = None
    road_label: str | None = None


class ReportPublic(BaseModel):
    id: str
    category: CategoryT
    magnitude: MagnitudeT
    description: str | None
    lat: float
    lon: float
    status: str
    veracity: float = Field(alias="veracity_score")
    relevance: float = Field(alias="relevance_score")
    priority: float
    captured_at: str
    valid_to: str | None
    photo_url: str | None

    model_config = ConfigDict(populate_by_name=True)


class ModerationDecision(BaseModel):
    decision: Literal["publicar", "descartar"]
    note: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class LoginResponse(BaseModel):
    token: str
    expires_in: int
    username: str


class AuthFieldHint(BaseModel):
    label: str
    placeholder: str
    hint: str


class SigmaAuthLinks(BaseModel):
    cadastro: str
    cadastro_sigma: str
    recuperar_senha: str
    login_gestor: str
    login_sigma: str
    selecionar_perfil: str


class AuthContextResponse(BaseModel):
    sigma_configured: bool
    profile: str
    identifier: AuthFieldHint
    password: AuthFieldHint
    sigma_links: SigmaAuthLinks | None = None


class ModerationPolicyUpdate(BaseModel):
    """Payload de atualização da política do aprovador automático."""
    global_config: dict | None = Field(
        default=None,
        alias="global",
    )  # event_publish_min, event_discard_below, etc.
    sinais_veracidade: list[dict] | None = None
    fatores_via: list[dict] | None = None
    categorias_evento: list[dict] | None = None  # overrides por categoria de evento
    categorias_manif: list[dict] | None = None   # overrides por tipo de manifestação

    # Legado — aceito para compatibilidade mas mapeado internamente
    preset: str | None = None
    eventos: dict | None = None
    manifestacoes: dict | None = None

    model_config = ConfigDict(populate_by_name=True)
