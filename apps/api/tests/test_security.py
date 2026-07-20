from __future__ import annotations

from pharma_api.core.config import Settings
from pharma_api.core.security import (
    constant_time_equal,
    generate_token,
    hash_one_time_token,
    hash_password,
    hash_session_token,
    normalize_email,
    verify_password,
)


def _settings() -> Settings:
    return Settings(
        app_env="test",
        argon2_time_cost=2,
        argon2_memory_cost_kib=19_456,
        argon2_parallelism=1,
        session_token_pepper="0123456789abcdef0123456789abcdef",  # noqa: S106
        one_time_token_pepper="abcdef0123456789abcdef0123456789",  # noqa: S106
        _env_file=None,
    )


def test_email_normalization_is_unicode_aware_and_stable() -> None:
    assert normalize_email("  USER@Example.COM \n") == "user@example.com"


def test_argon2id_password_hash_round_trip_and_mismatch() -> None:
    settings = _settings()
    encoded = hash_password("Strong-Password-123", settings)

    assert encoded.startswith("$argon2id$")
    assert verify_password("Strong-Password-123", encoded, settings).valid is True
    assert verify_password("Wrong-Password-123", encoded, settings).valid is False


def test_tokens_are_random_and_only_hashed_for_persistence() -> None:
    settings = _settings()
    first = generate_token()
    second = generate_token()

    assert first != second
    assert hash_session_token(first, settings) != first
    assert hash_one_time_token(first, settings) != first
    assert hash_session_token(first, settings) != hash_one_time_token(first, settings)


def test_constant_time_comparison_has_expected_semantics() -> None:
    assert constant_time_equal("same", "same") is True
    assert constant_time_equal("same", "different") is False
