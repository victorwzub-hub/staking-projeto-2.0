from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_INSECURE_LOCAL_PASSWORD = "change-me-local-only"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Pharma Intelligence SaaS"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_debug: bool = False
    app_log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    api_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "postgresql+psycopg://pharma:change-me-local-only@localhost:5432/pharma"
    redis_url: str = "redis://localhost:6379/0"
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/'")
        return value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+"):
            raise ValueError("DATABASE_URL must use an explicit asynchronous PostgreSQL driver")
        return value

    @field_validator("api_cors_origins")
    @classmethod
    def normalize_cors_origins(cls, value: str) -> str:
        origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return ",".join(origins)

    @model_validator(mode="after")
    def reject_insecure_production_configuration(self) -> Self:
        if self.app_env != "production":
            return self

        errors: list[str] = []
        if self.app_debug:
            errors.append("APP_DEBUG must be false in production")

        database = urlsplit(self.database_url)
        if database.hostname in _LOCAL_HOSTS:
            errors.append("DATABASE_URL must not use a loopback host in production")
        if not database.password or database.password == _INSECURE_LOCAL_PASSWORD:
            errors.append("DATABASE_URL must use a non-default password in production")

        redis = urlsplit(self.redis_url)
        if redis.hostname in _LOCAL_HOSTS:
            errors.append("REDIS_URL must not use a loopback host in production")

        for origin in self.cors_origins:
            parsed_origin = urlsplit(origin)
            if origin == "*":
                errors.append("API_CORS_ORIGINS must not contain '*' in production")
                continue
            if parsed_origin.scheme != "https":
                errors.append("API_CORS_ORIGINS must use HTTPS origins in production")
            if parsed_origin.hostname in _LOCAL_HOSTS:
                errors.append("API_CORS_ORIGINS must not contain loopback hosts in production")

        if errors:
            raise ValueError("; ".join(dict.fromkeys(errors)))
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin for origin in self.api_cors_origins.split(",") if origin]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
