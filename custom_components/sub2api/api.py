"""Async API client for sub2API."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .models import (
    DashboardStats,
    Subscription,
    UserInfo,
    parse_dashboard_stats,
    parse_subscriptions,
    parse_user,
)

REQUEST_TIMEOUT = ClientTimeout(total=30)


class Sub2APIError(Exception):
    """Base exception for the sub2API client."""


class Sub2APIAuthError(Sub2APIError):
    """Authentication or token refresh failed."""


class Sub2APIConnectionError(Sub2APIError):
    """The sub2API server could not be reached."""


class Sub2APIResponseError(Sub2APIError):
    """The sub2API server returned an invalid or unsuccessful response."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


TokenUpdateCallback = Callable[[str, str], None]


def normalize_base_url(value: str) -> str:
    """Normalize and validate a user-provided HTTPS service URL."""

    candidate = value.strip().rstrip("/")
    try:
        parsed = urlsplit(candidate)
    except ValueError as err:
        raise ValueError("invalid URL") from err

    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("an HTTPS URL with a hostname is required")
    try:
        _ = parsed.port
    except ValueError as err:
        raise ValueError("invalid URL port") from err
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            "URL credentials, query strings, and fragments are not allowed"
        )

    path = parsed.path.rstrip("/")
    if path.lower().endswith("/api/v1"):
        path = path[: -len("/api/v1")]

    return urlunsplit(("https", parsed.netloc.lower(), path, "", "")).rstrip("/")


def site_identifier(base_url: str) -> str:
    """Return a stable, non-secret identifier for a sub2API site."""

    return hashlib.sha256(base_url.encode()).hexdigest()[:12]


class Sub2APIClient:
    """Client for the authenticated sub2API user endpoints."""

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        access_token: str,
        refresh_token: str,
        token_update_callback: TokenUpdateCallback | None = None,
    ) -> None:
        self._session = session
        self.base_url = normalize_base_url(base_url)
        self.access_token = access_token.strip()
        self.refresh_token = refresh_token.strip()
        self._token_update_callback = token_update_callback
        self._refresh_lock = asyncio.Lock()

    async def async_get_user(self) -> UserInfo:
        """Return the currently authenticated user."""

        return parse_user(await self._async_authenticated_get("/auth/me"))

    async def async_get_subscriptions(self) -> dict[int, Subscription]:
        """Return all active subscriptions and quota progress."""

        return parse_subscriptions(
            await self._async_authenticated_get("/subscriptions/progress")
        )

    async def async_get_dashboard_stats(self) -> DashboardStats:
        """Return token usage totals for the current user."""

        return parse_dashboard_stats(
            await self._async_authenticated_get("/usage/dashboard/stats")
        )

    async def _async_authenticated_get(self, path: str) -> Any:
        token_used = self.access_token
        response = await self._async_request(
            "GET",
            path,
            headers={"Authorization": f"Bearer {token_used}"},
        )
        if response.status != 401:
            return await self._async_unwrap(response)

        response.release()
        async with self._refresh_lock:
            if token_used == self.access_token:
                await self._async_refresh_tokens()

        retry = await self._async_request(
            "GET",
            path,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        if retry.status == 401:
            retry.release()
            raise Sub2APIAuthError("authentication failed after token refresh")
        return await self._async_unwrap(retry)

    async def _async_refresh_tokens(self) -> None:
        if not self.refresh_token:
            raise Sub2APIAuthError("refresh token is missing")

        response = await self._async_request(
            "POST",
            "/auth/refresh",
            json={"refresh_token": self.refresh_token},
        )
        if response.status in (400, 401, 403):
            response.release()
            raise Sub2APIAuthError("refresh token was rejected")

        data = await self._async_unwrap(response)
        if not isinstance(data, dict):
            raise Sub2APIAuthError("token refresh response is invalid")
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise Sub2APIAuthError("token refresh response has no access token")
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            raise Sub2APIAuthError("token refresh response has no refresh token")

        self.access_token = access_token.strip()
        self.refresh_token = refresh_token.strip()
        if self._token_update_callback is not None:
            self._token_update_callback(self.access_token, self.refresh_token)

    async def _async_request(
        self, method: str, path: str, **kwargs: Any
    ) -> ClientResponse:
        try:
            return await self._session.request(
                method,
                f"{self.base_url}/api/v1{path}",
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
        except (ClientError, TimeoutError) as err:
            raise Sub2APIConnectionError("cannot connect to sub2API") from err

    async def _async_unwrap(self, response: ClientResponse) -> Any:
        status = response.status
        try:
            payload = await response.json(content_type=None)
        except (ClientError, ValueError) as err:
            raise Sub2APIResponseError("response is not valid JSON", status) from err

        if status == 401:
            raise Sub2APIAuthError("access token was rejected")
        if status < 200 or status >= 300:
            raise Sub2APIResponseError(f"sub2API returned HTTP {status}", status)
        if not isinstance(payload, dict) or payload.get("code") != 0:
            message = payload.get("message") if isinstance(payload, dict) else None
            raise Sub2APIResponseError(
                str(message or "sub2API returned an unsuccessful response"), status
            )
        if "data" not in payload:
            raise Sub2APIResponseError("sub2API response has no data field", status)

        return payload["data"]
