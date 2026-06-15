"""Autenticação de moderadores contra o SIGMA-PLI (API HTTP ou PostgreSQL)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import psycopg
from psycopg.rows import dict_row

from ..config import settings
from .sigma_password import verify_password

logger = logging.getLogger(__name__)

GESTOR_PROFILE = "GESTOR"


class SigmaConnectionError(Exception):
    """SIGMA indisponível (rede ou serviço)."""


_LOOKUP_SQL = """
SELECT
    id::text,
    username,
    email_institucional,
    password_hash,
    tipo_usuario,
    ativo,
    bloqueado_ate
FROM usuarios.usuario
WHERE (
    LOWER(username) = LOWER(%(identifier)s)
    OR LOWER(email_institucional) = LOWER(%(identifier)s)
)
  AND UPPER(tipo_usuario) = %(profile)s
  AND ativo = true
LIMIT 2
"""


@dataclass(frozen=True)
class SigmaUser:
    id: str
    username: str
    email: str | None
    tipo_usuario: str


def sigma_api_configured() -> bool:
    return bool(settings.sigma_api_base_url.strip())


def sigma_db_configured() -> bool:
    return bool(settings.sigma_database_dsn)


def sigma_configured() -> bool:
    return sigma_api_configured() or sigma_db_configured()


def _row_blocked(row: dict[str, Any]) -> bool:
    until = row.get("bloqueado_ate")
    if until is None:
        return False
    if isinstance(until, datetime):
        dt = until if until.tzinfo else until.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc)
    return False


def _authenticate_gestor_via_api(identifier: str, password: str) -> SigmaUser | None:
    base = settings.sigma_api_base_url.strip().rstrip("/")
    url = f"{base}/api/auth/login"
    payload = {
        "identifier": identifier.strip(),
        "password": password,
        "tipo_usuario": GESTOR_PROFILE,
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(12.0)) as client:
            response = client.post(url, json=payload)
    except httpx.TimeoutException as exc:
        logger.warning("SIGMA API timeout: %s", url)
        raise SigmaConnectionError("SIGMA indisponível (timeout).") from exc
    except httpx.RequestError as exc:
        logger.warning("SIGMA API erro de rede: %s", exc)
        raise SigmaConnectionError("SIGMA indisponível.") from exc

    if response.status_code == 401:
        return None
    if response.status_code == 429:
        logger.warning("Rate limit no login SIGMA para identifier=%s", identifier)
        return None
    if response.status_code >= 500:
        raise SigmaConnectionError("SIGMA indisponível.")

    if response.status_code != 200:
        logger.warning(
            "Login SIGMA resposta inesperada (%s): %s",
            response.status_code,
            response.text[:300],
        )
        return None

    try:
        data = response.json()
    except ValueError as exc:
        raise SigmaConnectionError("Resposta inválida do SIGMA.") from exc

    user = data.get("user")
    if not isinstance(user, dict):
        return None

    tipo = str(user.get("tipo_usuario", "")).strip().upper()
    if tipo != GESTOR_PROFILE:
        return None

    user_id = user.get("id")
    username = user.get("username")
    if not user_id or not username:
        return None

    email = user.get("email_institucional")
    return SigmaUser(
        id=str(user_id),
        username=str(username),
        email=str(email) if email else None,
        tipo_usuario=tipo,
    )


def _authenticate_gestor_via_db(identifier: str, password: str) -> SigmaUser | None:
    params = {"identifier": identifier.strip(), "profile": GESTOR_PROFILE}

    try:
        conn = psycopg.connect(
            settings.sigma_database_dsn, row_factory=dict_row, connect_timeout=8
        )
        try:
            rows = conn.execute(_LOOKUP_SQL, params).fetchall()
        finally:
            conn.close()
    except Exception as exc:
        err_name = type(exc).__name__
        if "Connection" in err_name or "Timeout" in err_name or "Operational" in err_name:
            logger.warning("SIGMA DB indisponível: %s", exc)
            raise SigmaConnectionError("Banco SIGMA indisponível.") from exc
        logger.exception("Falha ao consultar usuarios.usuario no SIGMA")
        raise SigmaConnectionError("Erro ao consultar banco SIGMA.") from exc

    if not rows:
        return None
    if len(rows) > 1:
        logger.warning("Login ambíguo para identifier=%s (múltiplos gestores)", identifier)
        return None

    row = rows[0]
    if _row_blocked(row):
        return None

    pwd_hash = row.get("password_hash")
    if not verify_password(password, pwd_hash):
        return None

    return SigmaUser(
        id=str(row["id"]),
        username=row["username"],
        email=row.get("email_institucional"),
        tipo_usuario=str(row.get("tipo_usuario") or GESTOR_PROFILE),
    )


def authenticate_gestor(identifier: str, password: str) -> SigmaUser | None:
    """Valida credenciais no SIGMA. Prefere API HTTP; fallback PostgreSQL."""
    if not sigma_configured():
        logger.warning("SIGMA não configurado para autenticação.")
        return None

    if sigma_api_configured():
        return _authenticate_gestor_via_api(identifier, password)

    return _authenticate_gestor_via_db(identifier, password)
