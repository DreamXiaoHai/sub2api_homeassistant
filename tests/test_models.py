"""Tests for sub2API payload parsing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.sub2api.models import (
    AuthTokens,
    Sub2APIModelError,
    TotpChallenge,
    parse_auth_tokens,
    parse_dashboard_stats,
    parse_login_result,
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


def test_parse_screenshot_dashboard_tokens(dashboard_payload) -> None:
    """Today and cumulative token totals match the supplied dashboard."""

    stats = parse_dashboard_stats(dashboard_payload)

    assert stats.today_tokens == 3_000_000
    assert stats.today_input_tokens == 621_800
    assert stats.today_output_tokens == 55_500
    assert stats.total_tokens == 395_900_000
    assert stats.total_input_tokens == 11_500_000
    assert stats.total_output_tokens == 800_600


def test_parse_password_login_token_pair() -> None:
    result = parse_login_result(
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 7200,
        }
    )

    assert result == AuthTokens("access", "refresh")


def test_parse_password_login_totp_challenge() -> None:
    result = parse_login_result(
        {
            "requires_2fa": True,
            "temp_token": "temporary-login",
            "user_email_masked": "u***@example.com",
        }
    )

    assert result == TotpChallenge("temporary-login", "u***@example.com")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"access_token": "access"},
        {"access_token": "", "refresh_token": "refresh"},
    ],
)
def test_malformed_auth_tokens_are_rejected(payload) -> None:
    with pytest.raises(Sub2APIModelError):
        parse_auth_tokens(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"today_tokens": -1},
        {
            "today_input_tokens": "621800",
            "today_output_tokens": 55_500,
            "today_cache_creation_tokens": 22_700,
            "today_cache_read_tokens": 2_300_000,
            "today_tokens": 3_000_000,
            "total_input_tokens": 11_500_000,
            "total_output_tokens": 800_600,
            "total_cache_creation_tokens": 3_599_400,
            "total_cache_read_tokens": 380_000_000,
            "total_tokens": 395_900_000,
        },
    ],
)
def test_malformed_dashboard_stats_are_rejected(payload) -> None:
    with pytest.raises(Sub2APIModelError):
        parse_dashboard_stats(payload)


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
