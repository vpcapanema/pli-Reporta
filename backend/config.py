"""Configurações carregadas de variáveis de ambiente / .env."""
from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PLI Reporta"
    app_env: str = "development"

    database_url: str = "sqlite:///./pli_reporta.db"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        """Normaliza a URL para o driver psycopg (v3) do SQLAlchemy.

        Provedores como o Render injetam `postgres://` ou `postgresql://`, que
        o SQLAlchemy tenta abrir com psycopg2 (não instalado). Reescrevemos para
        `postgresql+psycopg://` para usar o psycopg 3.
        """
        if not isinstance(value, str):
            return value
        url = value.strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        elif url.startswith("postgresql+psycopg2://"):
            url = "postgresql+psycopg://" + url[len("postgresql+psycopg2://"):]
        return url
    photo_storage_dir: str = "./backend/storage/photos"
    public_base_url: str = "http://localhost:8080"

    secret_key: str = "change-me"
    capture_nonce_ttl_seconds: int = 300
    capture_nonce_offline_ttl_seconds: int = 172800  # 48 h para fila offline

    auto_publish_threshold: float = 0.70
    auto_discard_threshold: float = 0.30
    manifestation_publish_threshold: float = 0.75
    manifestation_discard_threshold: float = 0.40

    # Ciclo de vida automático de eventos
    maintenance_interval_seconds: int = 600  # roda expiração/limpeza a cada 10 min
    cluster_idle_hours: float = 24.0  # fecha cluster sem confirmações há X horas
    resolve_votes_threshold: int = 2  # contra-reportes p/ marcar evento resolvido

    roads_geojson_path: str = ""
    urban_geojson_path: str = ""
    municipios_geojson_path: str = ""
    road_snap_max_m: float = 60.0

    allowed_origins: str = "*"

    moderator_api_key: str = ""
    moderator_username: str = ""
    moderator_password: str = ""
    moderator_session_ttl_seconds: int = 28800  # 8 h

    # SIGMA-PLI — autenticação de gestores (API HTTP preferida; DB opcional)
    sigma_api_base_url: str = ""
    sigma_database_url: str = ""
    sigma_postgres_host: str = ""
    sigma_postgres_port: int = 5433
    sigma_postgres_database: str = "sigma_pli_qr53"
    sigma_postgres_user: str = "sigma_user"
    sigma_postgres_password: str = ""
    sigma_postgres_sslmode: str = "disable"
    resolver_api_key: str = ""

    @property
    def photo_dir(self) -> Path:
        p = Path(self.photo_storage_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cors_origins(self) -> list[str]:
        if self.allowed_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def sigma_database_dsn(self) -> str:
        """DSN PostgreSQL do SIGMA (usuarios.usuario)."""
        if self.sigma_database_url.strip():
            url = self.sigma_database_url.strip()
            for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://"):
                if url.startswith(prefix):
                    return "postgresql://" + url.split(prefix, 1)[1]
            return url
        if self.sigma_postgres_host.strip() and self.sigma_postgres_password:
            from urllib.parse import quote_plus

            user = quote_plus(self.sigma_postgres_user)
            password = quote_plus(self.sigma_postgres_password)
            return (
                f"postgresql://{user}:{password}@"
                f"{self.sigma_postgres_host}:{self.sigma_postgres_port}/"
                f"{self.sigma_postgres_database}?sslmode={self.sigma_postgres_sslmode}"
            )
        return ""


settings = Settings()
