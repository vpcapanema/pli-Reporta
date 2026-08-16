"""Autenticação de moderadores — sessão local após validação SIGMA-PLI."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import settings
from . import sigma_auth


@dataclass(frozen=True)
class ModeratorSession:
    """Sessao restrita emitida apos autenticacao de gestor."""

    user_id: str
    username: str
    tipo_usuario: str
    full_name: str | None = None


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        settings.secret_key, salt="pli-reporta-moderator-session"
    )


def auth_configured() -> bool:
    """Indica se ha backend SIGMA ou fallback local configurado."""

    if sigma_auth.sigma_configured():
        return True
    return bool(settings.moderator_username and settings.moderator_password)


def authenticate(username: str, password: str) -> ModeratorSession | None:
    """Autentica gestor no SIGMA ou no fallback local de desenvolvimento."""

    identifier = username.strip()
    if not identifier or not password:
        return None

    if sigma_auth.sigma_configured():
        try:
            user = sigma_auth.authenticate_gestor(identifier, password)
        except sigma_auth.SigmaConnectionError as exc:
            raise exc
        if user:
            return ModeratorSession(
                user_id=user.id,
                username=user.username,
                tipo_usuario=user.tipo_usuario,
                full_name=getattr(user, "full_name", user.username),
            )
        return None

    # Fallback local apenas para dev/teste sem SIGMA.
    if settings.moderator_username and settings.moderator_password:
        user_ok = secrets.compare_digest(identifier, settings.moderator_username)
        pass_ok = secrets.compare_digest(password, settings.moderator_password)
        if user_ok and pass_ok:
            return ModeratorSession(
                user_id="local",
                username=identifier,
                tipo_usuario="GESTOR",
                full_name=identifier,
            )
    return None


def issue_session_token(session: ModeratorSession) -> str:
    """Emite token assinado para a sessao restrita."""

    return _serializer().dumps(
        {
            "sub": session.username,
            "uid": session.user_id,
            "role": session.tipo_usuario,
            "name": session.full_name or session.username,
        }
    )


def verify_session_token(token: str | None) -> ModeratorSession | None:
    """Valida token assinado e reconstroi a sessao restrita."""

    if not token:
        return None
    try:
        payload = _serializer().loads(
            token, max_age=settings.moderator_session_ttl_seconds
        )
    except (SignatureExpired, BadSignature):
        return None
    if not isinstance(payload, dict):
        return None
    username = payload.get("sub")
    user_id = payload.get("uid")
    role = payload.get("role")
    full_name = payload.get("name")
    if not isinstance(username, str) or not username:
        return None
    if not isinstance(user_id, str) or not user_id:
        return None
    return ModeratorSession(
        user_id=user_id,
        username=username,
        tipo_usuario=str(role or "GESTOR"),
        full_name=str(full_name) if full_name else username,
    )
