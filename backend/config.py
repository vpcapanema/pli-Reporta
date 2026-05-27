"""Configurações carregadas de variáveis de ambiente / .env."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PLI Reporta"
    app_env: str = "development"

    database_url: str = "sqlite:///./pli_reporta.db"
    photo_storage_dir: str = "./backend/storage/photos"
    public_base_url: str = "http://localhost:8080"

    secret_key: str = "change-me"
    capture_nonce_ttl_seconds: int = 300

    auto_publish_threshold: float = 0.70
    auto_discard_threshold: float = 0.30

    roads_geojson_path: str = ""

    allowed_origins: str = "*"

    moderator_api_key: str = ""
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


settings = Settings()
