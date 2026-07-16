from __future__ import annotations

from fastapi import Response

from pharma_api.api.v1.auth import _clear_auth_cookies, _set_auth_cookies
from pharma_api.core.config import Settings


def test_auth_cookie_attributes_are_hardened() -> None:
    settings = Settings(
        app_env="test",
        session_cookie_secure=True,
        session_cookie_samesite="lax",
        session_cookie_domain=".example.test",
        _env_file=None,
    )
    response = Response()

    _set_auth_cookies(
        response,
        session_token="opaque-session-token",  # noqa: S106
        csrf_token="csrf-token",  # noqa: S106
        settings=settings,
    )

    headers = response.headers.getlist("set-cookie")
    session_cookie = next(value for value in headers if value.startswith("pharma_session="))
    csrf_cookie = next(value for value in headers if value.startswith("pharma_csrf="))
    assert "HttpOnly" in session_cookie
    assert "Secure" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Domain=.example.test" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Secure" in csrf_cookie


def test_clear_auth_cookies_expires_both_values() -> None:
    settings = Settings(app_env="test", _env_file=None)
    response = Response()

    _clear_auth_cookies(response, settings)

    headers = response.headers.getlist("set-cookie")
    assert len(headers) == 2
    assert all("Max-Age=0" in value for value in headers)
