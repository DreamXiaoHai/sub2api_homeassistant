"""Tests for the async sub2API client."""

from __future__ import annotations

import pytest
from aiohttp import ClientConnectionError, ClientSession, TCPConnector
from aiohttp.resolver import ThreadedResolver
from aioresponses import aioresponses

from custom_components.sub2api.api import (
    Sub2APIAuthError,
    Sub2APIClient,
    Sub2APIConnectionError,
    Sub2APICredentialsError,
    Sub2APIResponseError,
    Sub2APITotpRequired,
    normalize_base_url,
)


def response(data):
    """Wrap data in the standard sub2API response envelope."""

    return {"code": 0, "message": "success", "data": data}


def make_test_session() -> ClientSession:
    """Build a session without the Windows-incompatible async DNS resolver."""

    return ClientSession(connector=TCPConnector(resolver=ThreadedResolver()))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://EXAMPLE.com/", "https://example.com"),
        ("https://example.com/api/v1", "https://example.com"),
        ("https://example.com/sub2api/api/v1/", "https://example.com/sub2api"),
    ],
)
def test_normalize_base_url(value, expected) -> None:
    assert normalize_base_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "example.com",
        "https://user:pass@example.com",
        "https://example.com:invalid",
        "https://example.com?token=secret",
    ],
)
def test_normalize_base_url_rejects_unsafe_values(value) -> None:
    with pytest.raises(ValueError):
        normalize_base_url(value)


async def test_client_reads_progress(progress_payload) -> None:
    with aioresponses() as mocked:
        mocked.get(
            "https://example.com/api/v1/subscriptions/progress",
            payload=response(progress_payload),
        )
        async with make_test_session() as session:
            client = Sub2APIClient(session, "https://example.com", "access", "refresh")
            subscriptions = await client.async_get_subscriptions()

    assert subscriptions[42].daily.used_usd == 29.61
    assert subscriptions[42].weekly.limit_usd == 600.0


async def test_client_reads_dashboard_stats(dashboard_payload) -> None:
    with aioresponses() as mocked:
        mocked.get(
            "https://example.com/api/v1/usage/dashboard/stats",
            payload=response(dashboard_payload),
        )
        async with make_test_session() as session:
            client = Sub2APIClient(session, "https://example.com", "access", "refresh")
            stats = await client.async_get_dashboard_stats()

    assert stats.today_tokens == 3_000_000
    assert stats.total_tokens == 395_900_000


async def test_password_login_saves_returned_tokens() -> None:
    updates: list[tuple[str, str]] = []
    with aioresponses() as mocked:
        mocked.post(
            "https://example.com/api/v1/auth/login",
            payload=response(
                {
                    "access_token": "login-access",
                    "refresh_token": "login-refresh",
                    "expires_in": 7200,
                }
            ),
        )
        async with make_test_session() as session:
            client = Sub2APIClient(
                session,
                "https://example.com",
                "",
                "",
                lambda access, refresh: updates.append((access, refresh)),
            )
            challenge = await client.async_login("user@example.com", "secret-password")

    assert challenge is None
    assert client.access_token == "login-access"
    assert client.refresh_token == "login-refresh"
    assert client.email == "user@example.com"
    assert client.password == "secret-password"
    assert updates == [("login-access", "login-refresh")]


async def test_password_login_can_complete_totp() -> None:
    with aioresponses() as mocked:
        mocked.post(
            "https://example.com/api/v1/auth/login",
            payload=response(
                {
                    "requires_2fa": True,
                    "temp_token": "temporary-login",
                    "user_email_masked": "u***@example.com",
                }
            ),
        )
        mocked.post(
            "https://example.com/api/v1/auth/login/2fa",
            payload=response(
                {
                    "access_token": "totp-access",
                    "refresh_token": "totp-refresh",
                    "expires_in": 7200,
                }
            ),
        )
        async with make_test_session() as session:
            client = Sub2APIClient(session, "https://example.com", "", "")
            challenge = await client.async_login("user@example.com", "secret-password")
            assert challenge is not None
            await client.async_complete_totp(challenge.temp_token, "123456")

    assert client.access_token == "totp-access"
    assert client.refresh_token == "totp-refresh"


async def test_password_login_rejects_interactive_auth_response() -> None:
    with aioresponses() as mocked:
        mocked.post("https://example.com/api/v1/auth/login", status=403)
        async with make_test_session() as session:
            client = Sub2APIClient(session, "https://example.com", "", "")
            with pytest.raises(Sub2APICredentialsError):
                await client.async_login("user@example.com", "secret-password")


async def test_expired_access_token_is_refreshed_and_persisted(
    progress_payload,
) -> None:
    updates: list[tuple[str, str]] = []
    with aioresponses() as mocked:
        url = "https://example.com/api/v1/subscriptions/progress"
        mocked.get(url, status=401)
        mocked.post(
            "https://example.com/api/v1/auth/refresh",
            payload=response(
                {"access_token": "new-access", "refresh_token": "new-refresh"}
            ),
        )
        mocked.get(url, payload=response(progress_payload))

        async with make_test_session() as session:
            client = Sub2APIClient(
                session,
                "https://example.com",
                "old-access",
                "old-refresh",
                lambda access, refresh: updates.append((access, refresh)),
            )
            subscriptions = await client.async_get_subscriptions()

    assert subscriptions[42].weekly.used_usd == 64.09
    assert client.access_token == "new-access"
    assert client.refresh_token == "new-refresh"
    assert updates == [("new-access", "new-refresh")]


async def test_rejected_refresh_token_falls_back_to_password_login(
    progress_payload,
) -> None:
    with aioresponses() as mocked:
        progress_url = "https://example.com/api/v1/subscriptions/progress"
        mocked.get(progress_url, status=401)
        mocked.post("https://example.com/api/v1/auth/refresh", status=401)
        mocked.post(
            "https://example.com/api/v1/auth/login",
            payload=response(
                {
                    "access_token": "login-access",
                    "refresh_token": "login-refresh",
                    "expires_in": 7200,
                }
            ),
        )
        mocked.get(progress_url, payload=response(progress_payload))

        async with make_test_session() as session:
            client = Sub2APIClient(
                session,
                "https://example.com",
                "expired-access",
                "rejected-refresh",
                email="user@example.com",
                password="secret-password",
            )
            subscriptions = await client.async_get_subscriptions()

    assert subscriptions[42].daily.used_usd == 29.61
    assert client.access_token == "login-access"
    assert client.refresh_token == "login-refresh"


async def test_password_fallback_raises_when_totp_is_required() -> None:
    with aioresponses() as mocked:
        mocked.get("https://example.com/api/v1/auth/me", status=401)
        mocked.get("https://example.com/api/v1/auth/me", status=401)
        mocked.post("https://example.com/api/v1/auth/refresh", status=401)
        mocked.post(
            "https://example.com/api/v1/auth/login",
            payload=response(
                {
                    "requires_2fa": True,
                    "temp_token": "temporary-login",
                    "user_email_masked": "u***@example.com",
                }
            ),
        )

        async with make_test_session() as session:
            client = Sub2APIClient(
                session,
                "https://example.com",
                "expired-access",
                "rejected-refresh",
                email="user@example.com",
                password="secret-password",
            )
            with pytest.raises(Sub2APITotpRequired):
                await client.async_get_user()
            with pytest.raises(Sub2APITotpRequired):
                await client.async_get_user()


@pytest.mark.parametrize("status", [429, 500])
async def test_refresh_server_errors_do_not_trigger_password_login(status) -> None:
    with aioresponses() as mocked:
        mocked.get("https://example.com/api/v1/auth/me", status=401)
        mocked.post(
            "https://example.com/api/v1/auth/refresh",
            status=status,
            payload={"code": 1, "message": "temporary failure", "data": None},
        )

        async with make_test_session() as session:
            client = Sub2APIClient(
                session,
                "https://example.com",
                "expired-access",
                "refresh",
                email="user@example.com",
                password="secret-password",
            )
            with pytest.raises(Sub2APIResponseError) as caught:
                await client.async_get_user()

    assert caught.value.status == status


async def test_rejected_refresh_token_raises_auth_error() -> None:
    with aioresponses() as mocked:
        mocked.get("https://example.com/api/v1/auth/me", status=401)
        mocked.post("https://example.com/api/v1/auth/refresh", status=401)

        async with make_test_session() as session:
            client = Sub2APIClient(session, "https://example.com", "bad", "bad")
            with pytest.raises(Sub2APIAuthError):
                await client.async_get_user()


async def test_network_error_is_classified() -> None:
    with aioresponses() as mocked:
        mocked.get(
            "https://example.com/api/v1/auth/me",
            exception=ClientConnectionError("offline"),
        )
        async with make_test_session() as session:
            client = Sub2APIClient(session, "https://example.com", "access", "refresh")
            with pytest.raises(Sub2APIConnectionError):
                await client.async_get_user()


async def test_rate_limit_is_response_error() -> None:
    with aioresponses() as mocked:
        mocked.get("https://example.com/api/v1/auth/me", status=429, payload={})
        async with make_test_session() as session:
            client = Sub2APIClient(session, "https://example.com", "access", "refresh")
            with pytest.raises(Sub2APIResponseError) as caught:
                await client.async_get_user()

    assert caught.value.status == 429
