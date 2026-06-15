"""Login de acesso restrito (moderadores)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import (
    AuthContextResponse,
    AuthFieldHint,
    LoginRequest,
    LoginResponse,
    SigmaAuthLinks,
)
from ..services import auth as auth_svc
from ..services.sigma_auth import SigmaConnectionError

router = APIRouter()

_IDENTIFIER_HINT = AuthFieldHint(
    label="Usuário",
    placeholder="gestor.silva ou gestor.silva@orgao.gov.br",
    hint="",
)
_PASSWORD_HINT = AuthFieldHint(
    label="Senha",
    placeholder="Sua senha",
    hint="",
)


def _sigma_auth_links() -> SigmaAuthLinks | None:
    base = settings.sigma_api_base_url.strip().rstrip("/")
    if not base:
        return None
    return SigmaAuthLinks(
        cadastro=f"{base}/cadastro",
        cadastro_sigma=f"{base}/cadastro",
        recuperar_senha=f"{base}/auth/recuperacao-senha-acesso-geral",
        login_gestor=f"{base}/?next=/plataforma",
        login_sigma=f"{base}/?next=/plataforma",
        selecionar_perfil=f"{base}/auth/selecionar-perfil",
    )


@router.get("/auth/context", response_model=AuthContextResponse)
def auth_context() -> AuthContextResponse:
    return AuthContextResponse(
        sigma_configured=auth_svc.auth_configured(),
        profile="GESTOR",
        identifier=_IDENTIFIER_HINT,
        password=_PASSWORD_HINT,
        sigma_links=_sigma_auth_links(),
    )


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    if not auth_svc.auth_configured():
        raise HTTPException(
            503,
            detail="Acesso restrito não configurado (SIGMA ou credenciais locais ausentes).",
        )
    try:
        session = auth_svc.authenticate(body.username.strip(), body.password)
    except SigmaConnectionError as exc:
        raise HTTPException(
            503,
            detail="SIGMA indisponível. Verifique SIGMA_API_BASE_URL ou conectividade com a VM.",
        ) from exc
    if not session:
        raise HTTPException(401, detail="Usuário ou senha inválidos.")
    token = auth_svc.issue_session_token(session)
    return LoginResponse(
        token=token,
        expires_in=settings.moderator_session_ttl_seconds,
        username=session.username,
    )
