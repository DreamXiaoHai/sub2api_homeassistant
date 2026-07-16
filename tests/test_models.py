"""Tests for sub2API payload parsing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.sub2api.models import (
    Sub2APIModelError,
    parse_subscriptions,
)


def test_parse_screenshot_quota_values(progress_payload) -> None:
    """Daily and weekly values from the supplied screenshot remain exact."""

    subscription = parse_subscriptions(progress_payload)[42]

    assert subscription.group_name == "Codex Subscription"
    assert subscription.platform == "openai"
    assert subscription.daily is not None
    assert subscription.daily.used_usd == 29.61
    assert subscription.daily.limit_usd == 300.0
    assert subscription.daily.remaining_usd == 270.39
    assert subscription.daily.percentage == 9.87
    assert subscription.daily.resets_at == datetime(2026, 7, 17, tzinfo=UTC)
    assert subscription.weekly is not None
    assert subscription.weekly.used_usd == 64.09
    assert subscription.weekly.limit_usd == 600.0
    assert subscription.weekly.remaining_usd == 535.91
    assert subscription.weekly.resets_at == datetime(2026, 7, 21, tzinfo=UTC)


def test_limit_without_active_window_is_available(progress_payload) -> None:
    """Configured limits remain visible before a reset window is active."""

    progress_payload[0]["progress"]["daily"] = None
    progress_payload[0]["subscription"]["daily_window_start"] = None
    subscription = parse_subscriptions(progress_payload)[42]

    assert subscription.daily is not None
    assert subscription.daily.used_usd == 29.61
    assert subscription.daily.limit_usd == 300.0
    assert subscription.daily.resets_at is None


def test_missing_limit_omits_window(progress_payload) -> None:
    """A quota type without a limit does not produce sensors."""

    progress_payload[0]["progress"]["weekly"] = None
    progress_payload[0]["subscription"]["group"]["weekly_limit_usd"] = None

    assert parse_subscriptions(progress_payload)[42].weekly is None


@pytest.mark.parametrize(
    "payload", [{}, [None], [{"subscription": {}, "progress": {}}]]
)
def test_malformed_payload_is_rejected(payload) -> None:
    """Malformed responses fail the full coordinator update."""

    with pytest.raises(Sub2APIModelError):
        parse_subscriptions(payload)
