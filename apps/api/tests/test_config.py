from __future__ import annotations

import pytest
from pydantic import ValidationError

from pharma_api.core.config import Settings

_SAFE_PRODUCTION_CONFIG = {
    "app_env": "production",
    "app_debug": False,
    "database_url": "postgresql+psycopg://pharma:strong-example@db.internal:5432/pharma",
    "redis_url": "redis://cache.internal:6379/0",
    "api_cors_origins": "https://app.example.com",
    "frontend_base_url": "https://app.example.com",
    "session_cookie_secure": True,
    "session_token_pepper": "0123456789abcdef0123456789abcdef",
    "one_time_token_pepper": "abcdef0123456789abcdef0123456789",
}


def test_safe_production_configuration_is_accepted() -> None:
    settings = Settings(**_SAFE_PRODUCTION_CONFIG, _env_file=None)

    assert settings.app_env == "production"
    assert settings.cors_origins == ["https://app.example.com"]


@pytest.mark.parametrize(
    ("override", "expected_message"),
    [
        ({"app_debug": True}, "APP_DEBUG must be false"),
        (
            {
                "database_url": (
                    "postgresql+psycopg://pharma:change-me-local-only@db.internal:5432/pharma"
                )
            },
            "non-default password",
        ),
        (
            {"database_url": "postgresql+psycopg://pharma:strong-example@localhost:5432/pharma"},
            "loopback host",
        ),
        ({"redis_url": "redis://127.0.0.1:6379/0"}, "REDIS_URL"),
        ({"api_cors_origins": "*"}, "must not contain '*'"),
        ({"api_cors_origins": "http://app.example.com"}, "must use HTTPS"),
        ({"api_cors_origins": "https://localhost:3000"}, "loopback hosts"),
    ],
)
def test_insecure_production_configuration_is_rejected(
    override: dict[str, object],
    expected_message: str,
) -> None:
    config = {**_SAFE_PRODUCTION_CONFIG, **override}

    with pytest.raises(ValidationError, match=expected_message):
        Settings(**config, _env_file=None)
