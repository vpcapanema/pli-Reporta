"""Testes de autenticação SIGMA (API, DB mock) e verificação de senha."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from backend.services.sigma_password import verify_password


def test_verify_argon2_sample():
    assert verify_password("wrong", "$argon2id$v=19$m=32768,t=2,p=2$abc$def") is False


def _mock_db_rows(rows):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = rows
    return mock_conn


def _mock_api_response(*, status_code: int, json_data: dict | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.text = ""
    response.json.return_value = json_data or {}
    return response


def test_authenticate_gestor_via_api_success():
    from backend.services import sigma_auth

    response = _mock_api_response(
        status_code=200,
        json_data={
            "user": {
                "id": "uuid-1",
                "username": "gestor.teste",
                "email_institucional": "gestor@teste.gov.br",
                "tipo_usuario": "GESTOR",
            }
        },
    )
    mock_client = MagicMock()
    mock_client.post.return_value = response

    with patch.object(sigma_auth.settings, "sigma_api_base_url", "http://56.125.163.194"):
        with patch.object(sigma_auth.settings, "sigma_database_url", ""):
            with patch.object(sigma_auth.settings, "sigma_postgres_password", ""):
                with patch("httpx.Client") as client_cls:
                    client_cls.return_value.__enter__.return_value = mock_client
                    user = sigma_auth.authenticate_gestor("gestor.teste", "secret12")

    assert user is not None
    assert user.username == "gestor.teste"
    assert user.tipo_usuario == "GESTOR"
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[0][0] == "http://56.125.163.194/api/auth/login"
    assert call_kwargs[1]["json"]["tipo_usuario"] == "GESTOR"


def test_authenticate_gestor_via_api_invalid_credentials():
    from backend.services import sigma_auth

    response = _mock_api_response(status_code=401)
    mock_client = MagicMock()
    mock_client.post.return_value = response

    with patch.object(sigma_auth.settings, "sigma_api_base_url", "http://56.125.163.194"):
        with patch.object(sigma_auth.settings, "sigma_database_url", ""):
            with patch.object(sigma_auth.settings, "sigma_postgres_password", ""):
                with patch("httpx.Client") as client_cls:
                    client_cls.return_value.__enter__.return_value = mock_client
                    user = sigma_auth.authenticate_gestor("gestor.teste", "badpass1")

    assert user is None


def test_authenticate_gestor_via_api_network_error():
    from backend.services import sigma_auth

    mock_client = MagicMock()
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    with patch.object(sigma_auth.settings, "sigma_api_base_url", "http://56.125.163.194"):
        with patch.object(sigma_auth.settings, "sigma_database_url", ""):
            with patch.object(sigma_auth.settings, "sigma_postgres_password", ""):
                with patch("httpx.Client") as client_cls:
                    client_cls.return_value.__enter__.return_value = mock_client
                    try:
                        sigma_auth.authenticate_gestor("gestor.teste", "secret12")
                        assert False, "expected SigmaConnectionError"
                    except sigma_auth.SigmaConnectionError:
                        pass


def test_authenticate_gestor_db_success():
    from backend.services import sigma_auth

    row = {
        "id": "uuid-1",
        "username": "gestor.teste",
        "email_institucional": "gestor@teste.gov.br",
        "password_hash": "hash",
        "tipo_usuario": "GESTOR",
        "ativo": True,
        "bloqueado_ate": None,
    }

    with patch.object(sigma_auth.settings, "sigma_api_base_url", ""):
        with patch.object(
            sigma_auth.settings,
            "sigma_database_url",
            "postgresql://u:p@127.0.0.1:15433/db",
        ):
            with patch("backend.services.sigma_auth.psycopg.connect", return_value=_mock_db_rows([row])):
                with patch.object(sigma_auth, "verify_password", return_value=True):
                    user = sigma_auth.authenticate_gestor("gestor.teste", "secret12")

    assert user is not None
    assert user.username == "gestor.teste"


def test_authenticate_gestor_db_wrong_password():
    from backend.services import sigma_auth

    row = {
        "id": "uuid-1",
        "username": "gestor.teste",
        "email_institucional": None,
        "password_hash": "hash",
        "tipo_usuario": "GESTOR",
        "ativo": True,
        "bloqueado_ate": None,
    }

    with patch.object(sigma_auth.settings, "sigma_api_base_url", ""):
        with patch.object(
            sigma_auth.settings,
            "sigma_database_url",
            "postgresql://u:p@127.0.0.1:15433/db",
        ):
            with patch("backend.services.sigma_auth.psycopg.connect", return_value=_mock_db_rows([row])):
                with patch.object(sigma_auth, "verify_password", return_value=False):
                    user = sigma_auth.authenticate_gestor("gestor.teste", "badpass1")

    assert user is None
