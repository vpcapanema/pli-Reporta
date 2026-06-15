"""Geração e verificação do nonce de captura in-app.

Uso: o cliente pede um nonce ao backend imediatamente antes de abrir a câmera.
O nonce é assinado com SECRET_KEY e tem TTL curto. No envio do reporte, o cliente
devolve o nonce; o backend confirma assinatura e validade. Isso eleva s_capture_inapp.
"""
from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import settings


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="pli-reporta-capture")


def issue_nonce(client_id: str | None = None) -> str:
    payload = {"client_id": client_id or "anon"}
    return _serializer().dumps(payload)


def verify_nonce(nonce: str | None, *, offline: bool = False) -> bool:
    if not nonce:
        return False
    max_age = (
        settings.capture_nonce_offline_ttl_seconds
        if offline
        else settings.capture_nonce_ttl_seconds
    )
    try:
        _serializer().loads(nonce, max_age=max_age)
        return True
    except (SignatureExpired, BadSignature):
        return False
