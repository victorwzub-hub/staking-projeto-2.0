from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_INSECURE_LOCAL_PASSWORD = "change-me-local-only"  # noqa: S105
_INSECURE_SECRET_VALUES = {
    "change-me-local-only",
    "development-session-pepper-change-me",
    "development-token-pepper-change-me",
}


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
    frontend_base_url: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://pharma:change-me-local-only@localhost:5432/pharma"
    database_application_role: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    object_storage_backend: Literal["filesystem", "s3"] = "filesystem"
    object_storage_root: Path = Path(".local/objects")
    s3_endpoint_url: str | None = None
    s3_bucket: str = "pharma-landing"
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_server_side_encryption: Literal["AES256", "aws:kms"] | None = "AES256"
    integration_upload_max_bytes: int = Field(default=104_857_600, ge=1_048_576)
    integration_chunk_records: int = Field(default=1_000, ge=100, le=50_000)
    integration_retention_days: int = Field(default=90, ge=7, le=3_650)
    integration_lease_seconds: int = Field(default=300, ge=30, le=3_600)
    connector_timeout_seconds: int = Field(default=60, ge=5, le=900)

    password_min_length: int = Field(default=12, ge=10, le=128)
    argon2_time_cost: int = Field(default=3, ge=2, le=10)
    argon2_memory_cost_kib: int = Field(default=65_536, ge=19_456, le=1_048_576)
    argon2_parallelism: int = Field(default=4, ge=1, le=16)
    argon2_hash_len: int = Field(default=32, ge=16, le=64)
    argon2_salt_len: int = Field(default=16, ge=16, le=64)

    session_cookie_name: str = "pharma_session"
    csrf_cookie_name: str = "pharma_csrf"
    session_cookie_domain: str | None = None
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_ttl_seconds: int = Field(default=43_200, ge=900, le=2_592_000)
    session_idle_timeout_seconds: int = Field(default=10_800, ge=300, le=604_800)
    session_token_pepper: SecretStr = SecretStr("development-session-pepper-change-me")
    one_time_token_pepper: SecretStr = SecretStr("development-token-pepper-change-me")

    email_verification_ttl_seconds: int = Field(default=86_400, ge=900, le=604_800)
    password_reset_ttl_seconds: int = Field(default=3_600, ge=300, le=86_400)
    invitation_ttl_seconds: int = Field(default=604_800, ge=3_600, le=2_592_000)

    login_max_attempts: int = Field(default=5, ge=3, le=20)
    login_window_seconds: int = Field(default=900, ge=60, le=86_400)
    login_lockout_seconds: int = Field(default=900, ge=60, le=86_400)
    login_max_lockout_seconds: int = Field(default=86_400, ge=300, le=604_800)
    public_auth_max_requests: int = Field(default=5, ge=2, le=100)
    public_auth_window_seconds: int = Field(default=900, ge=60, le=86_400)

    email_backend: Literal["development", "test"] = "development"
    email_spool_directory: Path = Path(".local/emails")
    email_from_address: str = "no-reply@local.invalid"

    bootstrap_enabled: bool = False
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None

    audit_retention_days: int = Field(default=730, ge=90, le=3_650)
    session_retention_days: int = Field(default=180, ge=30, le=730)

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/'")
        return value.rstrip("/")

    @field_validator("database_application_role")
    @classmethod
    def validate_database_application_role(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        candidate = value.strip()
        if not candidate.replace("_", "a").isalnum() or not (
            candidate[0].isalpha() or candidate[0] == "_"
        ):
            raise ValueError("DATABASE_APPLICATION_ROLE must be a simple PostgreSQL identifier")
        return candidate

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+"):
            raise ValueError("DATABASE_URL must use an explicit PostgreSQL driver")
        return value

    @field_validator("api_cors_origins")
    @classmethod
    def normalize_cors_origins(cls, value: str) -> str:
        origins = [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return ",".join(origins)

    @field_validator("frontend_base_url")
    @classmethod
    def normalize_frontend_url(cls, value: str) -> str:
        candidate = value.strip().rstrip("/")
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("FRONTEND_BASE_URL must be an absolute HTTP(S) URL")
        return candidate

    @field_validator("s3_endpoint_url")
    @classmethod
    def validate_s3_endpoint(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        candidate = value.strip().rstrip("/")
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("S3_ENDPOINT_URL must be an absolute HTTP(S) URL")
        return candidate

    @field_validator("s3_server_side_encryption", mode="before")
    @classmethod
    def normalize_s3_server_side_encryption(cls, value: object) -> object:
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return None
            if candidate.casefold() == "aes256":
                return "AES256"
            if candidate.casefold() == "aws:kms":
                return "aws:kms"
        return value

    @field_validator("session_cookie_name", "csrf_cookie_name")
    @classmethod
    def validate_cookie_name(cls, value: str) -> str:
        if not value or any(char.isspace() for char in value):
            raise ValueError("Cookie names must be non-empty and contain no whitespace")
        return value

    @model_validator(mode="after")
    def validate_cookie_policy(self) -> Self:
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None requires SESSION_COOKIE_SECURE=true")
        return self

    @model_validator(mode="after")
    def reject_insecure_deployed_configuration(self) -> Self:
        if self.app_env not in {"staging", "production"}:
            return self

        errors: list[str] = []
        if self.app_debug:
            errors.append("APP_DEBUG must be false in deployed environments")
        if not self.session_cookie_secure:
            errors.append("SESSION_COOKIE_SECURE must be true in deployed environments")
        if self.object_storage_backend != "s3":
            errors.append("OBJECT_STORAGE_BACKEND must be s3 in deployed environments")
        if self.s3_server_side_encryption is None:
            errors.append("S3_SERVER_SIDE_ENCRYPTION must be enabled in deployed environments")

        database = urlsplit(self.database_url)
        if database.hostname in _LOCAL_HOSTS:
            errors.append("DATABASE_URL must not use a loopback host in deployed environments")
        if not database.password or database.password == _INSECURE_LOCAL_PASSWORD:
            errors.append("DATABASE_URL must use a non-default password in deployed environments")

        redis = urlsplit(self.redis_url)
        if redis.hostname in _LOCAL_HOSTS:
            errors.append("REDIS_URL must not use a loopback host in deployed environments")

        frontend = urlsplit(self.frontend_base_url)
        if frontend.scheme != "https" or frontend.hostname in _LOCAL_HOSTS:
            errors.append("FRONTEND_BASE_URL must be a non-loopback HTTPS URL")

        for origin in self.cors_origins:
            parsed_origin = urlsplit(origin)
            if origin == "*":
                errors.append("API_CORS_ORIGINS must not contain '*'")
                continue
            if parsed_origin.scheme != "https":
                errors.append("API_CORS_ORIGINS must use HTTPS origins")
            if parsed_origin.hostname in _LOCAL_HOSTS:
                errors.append("API_CORS_ORIGINS must not contain loopback hosts")

        for name, secret in (
            ("SESSION_TOKEN_PEPPER", self.session_token_pepper),
            ("ONE_TIME_TOKEN_PEPPER", self.one_time_token_pepper),
        ):
            value = secret.get_secret_value()
            if len(value) < 32 or value in _INSECURE_SECRET_VALUES:
                errors.append(f"{name} must be a non-default secret with at least 32 characters")

        if errors:
            raise ValueError("; ".join(dict.fromkeys(errors)))
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin for origin in self.api_cors_origins.split(",") if origin]

    @property
    def is_deployed(self) -> bool:
        return self.app_env in {"staging", "production"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
