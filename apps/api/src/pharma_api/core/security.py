from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type

from pharma_api.core.config import Settings, get_settings

_EMAIL_WHITESPACE = re.compile(r"\s+")


def normalize_email(email: str) -> str:
    normalized = unicodedata.normalize("NFKC", email).strip().casefold()
    return _EMAIL_WHITESPACE.sub("", normalized)


def _password_hasher(settings: Settings | None = None) -> PasswordHasher:
    config = settings or get_settings()
    return PasswordHasher(
        time_cost=config.argon2_time_cost,
        memory_cost=config.argon2_memory_cost_kib,
        parallelism=config.argon2_parallelism,
        hash_len=config.argon2_hash_len,
        salt_len=config.argon2_salt_len,
        type=Type.ID,
    )


def validate_password_policy(password: str, settings: Settings | None = None) -> None:
    config = settings or get_settings()
    if len(password) < config.password_min_length:
        raise ValueError(f"Password must contain at least {config.password_min_length} characters")
    if len(password) > 128:
        raise ValueError("Password must contain at most 128 characters")
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        raise ValueError("Password must contain letters and numbers")


def hash_password(password: str, settings: Settings | None = None) -> str:
    validate_password_policy(password, settings)
    return _password_hasher(settings).hash(password)


@dataclass(frozen=True, slots=True)
class PasswordVerification:
    valid: bool
    replacement_hash: str | None = None


def verify_password(
    password: str,
    password_hash: str,
    settings: Settings | None = None,
) -> PasswordVerification:
    hasher = _password_hasher(settings)
    try:
        valid = hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return PasswordVerification(valid=False)
    replacement = (
        hasher.hash(password) if valid and hasher.check_needs_rehash(password_hash) else None
    )
    return PasswordVerification(valid=valid, replacement_hash=replacement)


def generate_token(byte_length: int = 32) -> str:
    return secrets.token_urlsafe(byte_length)


def _hmac_digest(value: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_session_token(token: str, settings: Settings | None = None) -> str:
    config = settings or get_settings()
    return _hmac_digest(token, config.session_token_pepper.get_secret_value())


def hash_one_time_token(token: str, settings: Settings | None = None) -> str:
    config = settings or get_settings()
    return _hmac_digest(token, config.one_time_token_pepper.get_secret_value())


def hash_sensitive_identifier(value: str | None, settings: Settings | None = None) -> str | None:
    if not value:
        return None
    config = settings or get_settings()
    return _hmac_digest(value, config.one_time_token_pepper.get_secret_value())


def safe_user_agent(value: str | None) -> str | None:
    if not value:
        return None
    return "".join(char for char in value if char.isprintable())[:512]


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
