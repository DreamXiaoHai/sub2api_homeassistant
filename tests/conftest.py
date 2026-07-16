"""Shared fixtures for sub2API integration tests."""

from __future__ import annotations

import sys
from typing import Any

import pytest
import pytest_socket

if sys.platform == "win32":
    import asyncio

pytest_plugins = "pytest_homeassistant_custom_component"

if sys.platform == "win32":
    # The HA plugin blocks AF_INET sockets before pytest-asyncio creates the
    # Proactor loop. On Windows that loop uses an AF_INET socketpair internally.
    pytest_socket.disable_socket = lambda **kwargs: None


def pytest_configure() -> None:
    """Use the Windows event loop required by Home Assistant's async DNS client."""

    if sys.platform == "win32":
        asyncio.get_event_loop_policy()._loop_factory = asyncio.SelectorEventLoop


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading the integration from custom_components."""


@pytest.fixture
def progress_payload() -> list[dict[str, Any]]:
    """Return a representative /subscriptions/progress data payload."""

    return [
        {
            "subscription": {
                "id": 42,
                "user_id": 7,
                "group_id": 9,
                "status": "active",
                "daily_usage_usd": 29.61,
                "weekly_usage_usd": 64.09,
                "daily_window_start": "2026-07-16T00:00:00Z",
                "weekly_window_start": "2026-07-14T00:00:00Z",
                "group": {
                    "name": "Codex Subscription",
                    "platform": "openai",
                    "daily_limit_usd": 300.0,
                    "weekly_limit_usd": 600.0,
                },
            },
            "progress": {
                "id": 42,
                "group_name": "Codex Subscription",
                "expires_at": "2026-08-14T00:00:00Z",
                "expires_in_days": 29,
                "daily": {
                    "limit_usd": 300.0,
                    "used_usd": 29.61,
                    "remaining_usd": 270.39,
                    "percentage": 9.87,
                    "window_start": "2026-07-16T00:00:00Z",
                    "resets_at": "2026-07-17T00:00:00Z",
                    "resets_in_seconds": 47940,
                },
                "weekly": {
                    "limit_usd": 600.0,
                    "used_usd": 64.09,
                    "remaining_usd": 535.91,
                    "percentage": 10.6816666667,
                    "window_start": "2026-07-14T00:00:00Z",
                    "resets_at": "2026-07-21T00:00:00Z",
                    "resets_in_seconds": 479940,
                },
                "monthly": None,
            },
        }
    ]
