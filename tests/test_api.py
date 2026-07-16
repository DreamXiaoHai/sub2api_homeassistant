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
    Sub2APIResponseError,
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
