"""Pydantic schemas para a API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CategoryT = Literal[
    "bloqueio_total",
    "acidente",
    "alagamento",
    "obra_grande",
    "lentidao_corredor",
    "sinalizacao_quebrada",
    "buraco",
    "outro",
]
MagnitudeT = Literal["leve", "normal", "grave"]


class CaptureNonceResponse(BaseModel):
    nonce: str
    expires_in: int


class ReportCreated(BaseModel):
    id: str
    status: str
    veracity_score: float
    relevance_score: float
    priority: float
    explanation: list[str]
    cluster_id: str | None
    valid_to: str | None


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
