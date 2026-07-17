"""Typed sub2API response models and parsers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class Sub2APIModelError(ValueError):
    """Raised when an API payload does not match the expected shape."""


@dataclass(frozen=True, slots=True)
class UserInfo:
    """Authenticated sub2API user identity."""

    user_id: int
    username: str
    email: str


@dataclass(frozen=True, slots=True)
class AuthTokens:
    """A rotating sub2API access and refresh token pair."""

    access_token: str
    refresh_token: str


@dataclass(frozen=True, slots=True)
class TotpChallenge:
    """A pending sub2API two-factor login challenge."""

    temp_token: str
    user_email_masked: str


type LoginResult = AuthTokens | TotpChallenge


@dataclass(frozen=True, slots=True)
class UsageWindow:
    """Quota usage for one rolling window."""

    used_usd: float
    limit_usd: float
    remaining_usd: float
    percentage: float
    window_start: datetime | None
    resets_at: datetime | None
    resets_in_seconds: int | None


@dataclass(frozen=True, slots=True)
class Subscription:
    """One active sub2API subscription."""

    subscription_id: int
    user_id: int
    group_id: int
    group_name: str
    platform: str
    status: str
    daily: UsageWindow | None
    weekly: UsageWindow | None


@dataclass(frozen=True, slots=True)
class DashboardStats:
    """Token usage totals shown on the sub2API user dashboard."""

    today_input_tokens: int
    today_output_tokens: int
    today_cache_creation_tokens: int
    today_cache_read_tokens: int
    today_tokens: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_creation_tokens: int
    total_cache_read_tokens: int
    total_tokens: int


def parse_user(payload: Any) -> UserInfo:
    """Parse the data object returned by /auth/me."""

    data = _mapping(payload, "user")
    return UserInfo(
        user_id=_integer(data.get("id"), "user.id"),
        username=_text(data.get("username")),
        email=_text(data.get("email")),
    )


def parse_auth_tokens(payload: Any) -> AuthTokens:
    """Parse a token pair returned by login, 2FA, or refresh."""

    data = _mapping(payload, "authentication")
    return AuthTokens(
        access_token=_required_text(
            data.get("access_token"), "authentication.access_token"
        ),
        refresh_token=_required_text(
            data.get("refresh_token"), "authentication.refresh_token"
        ),
    )


def parse_login_result(payload: Any) -> LoginResult:
    """Parse a password login response, including an optional TOTP challenge."""

    data = _mapping(payload, "login")
    if data.get("requires_2fa") is True:
        return TotpChallenge(
            temp_token=_required_text(data.get("temp_token"), "login.temp_token"),
            user_email_masked=_text(data.get("user_email_masked")),
        )
    return parse_auth_tokens(data)


def parse_dashboard_stats(payload: Any) -> DashboardStats:
    """Parse the token totals returned by /usage/dashboard/stats."""

    data = _mapping(payload, "dashboard stats")
    return DashboardStats(
        today_input_tokens=_nonnegative_integer(
            data.get("today_input_tokens"), "dashboard_stats.today_input_tokens"
        ),
        today_output_tokens=_nonnegative_integer(
            data.get("today_output_tokens"), "dashboard_stats.today_output_tokens"
        ),
        today_cache_creation_tokens=_nonnegative_integer(
            data.get("today_cache_creation_tokens"),
            "dashboard_stats.today_cache_creation_tokens",
        ),
        today_cache_read_tokens=_nonnegative_integer(
            data.get("today_cache_read_tokens"),
            "dashboard_stats.today_cache_read_tokens",
        ),
        today_tokens=_nonnegative_integer(
            data.get("today_tokens"), "dashboard_stats.today_tokens"
        ),
        total_input_tokens=_nonnegative_integer(
            data.get("total_input_tokens"), "dashboard_stats.total_input_tokens"
        ),
        total_output_tokens=_nonnegative_integer(
            data.get("total_output_tokens"), "dashboard_stats.total_output_tokens"
        ),
        total_cache_creation_tokens=_nonnegative_integer(
            data.get("total_cache_creation_tokens"),
            "dashboard_stats.total_cache_creation_tokens",
        ),
        total_cache_read_tokens=_nonnegative_integer(
            data.get("total_cache_read_tokens"),
            "dashboard_stats.total_cache_read_tokens",
        ),
        total_tokens=_nonnegative_integer(
            data.get("total_tokens"), "dashboard_stats.total_tokens"
        ),
    )


def parse_subscriptions(payload: Any) -> dict[int, Subscription]:
    """Parse /subscriptions/progress data, rejecting partial bad data."""

    if not isinstance(payload, list):
        raise Sub2APIModelError("subscriptions data must be a list")

    subscriptions: dict[int, Subscription] = {}
    for index, raw_item in enumerate(payload):
        item = _mapping(raw_item, f"subscriptions[{index}]")
        raw_subscription = _mapping(
            item.get("subscription"), f"subscriptions[{index}].subscription"
        )
        progress = _mapping(item.get("progress"), f"subscriptions[{index}].progress")
        group = _optional_mapping(raw_subscription.get("group"))

        subscription_id = _integer(
            raw_subscription.get("id"), f"subscriptions[{index}].subscription.id"
        )
        group_id = _integer(
            raw_subscription.get("group_id"),
            f"subscriptions[{index}].subscription.group_id",
        )
        user_id = _integer(
            raw_subscription.get("user_id"),
            f"subscriptions[{index}].subscription.user_id",
        )
        group_name = (
            _text(progress.get("group_name"))
            or _text(group.get("name"))
            or f"Subscription {subscription_id}"
        )

        daily = _parse_window(
            progress.get("daily"),
            group.get("daily_limit_usd"),
            raw_subscription.get("daily_usage_usd"),
            raw_subscription.get("daily_window_start"),
            f"subscriptions[{index}].progress.daily",
        )
        weekly = _parse_window(
            progress.get("weekly"),
            group.get("weekly_limit_usd"),
            raw_subscription.get("weekly_usage_usd"),
            raw_subscription.get("weekly_window_start"),
            f"subscriptions[{index}].progress.weekly",
        )

        if subscription_id in subscriptions:
            raise Sub2APIModelError(f"duplicate subscription id: {subscription_id}")

        subscriptions[subscription_id] = Subscription(
            subscription_id=subscription_id,
            user_id=user_id,
            group_id=group_id,
            group_name=group_name,
            platform=_text(group.get("platform")),
            status=_text(raw_subscription.get("status")),
            daily=daily,
            weekly=weekly,
        )

    return subscriptions


def _parse_window(
    raw_progress: Any,
    raw_limit: Any,
    raw_used: Any,
    raw_window_start: Any,
    field: str,
) -> UsageWindow | None:
    progress = _optional_mapping(raw_progress)
    if progress:
        limit = _number(progress.get("limit_usd"), f"{field}.limit_usd")
        used = _number(progress.get("used_usd"), f"{field}.used_usd")
        return UsageWindow(
            used_usd=used,
            limit_usd=limit,
            remaining_usd=_number(
                progress.get("remaining_usd"), f"{field}.remaining_usd"
            ),
            percentage=_number(progress.get("percentage"), f"{field}.percentage"),
            window_start=_datetime_or_none(
                progress.get("window_start"), f"{field}.window_start"
            ),
            resets_at=_datetime_or_none(
                progress.get("resets_at"), f"{field}.resets_at"
            ),
            resets_in_seconds=_integer_or_none(
                progress.get("resets_in_seconds"), f"{field}.resets_in_seconds"
            ),
        )

    limit = _number_or_none(raw_limit, f"{field}.fallback_limit_usd")
    if limit is None or limit <= 0:
        return None

    used = _number_or_default(raw_used, f"{field}.fallback_used_usd", 0.0)
    return UsageWindow(
        used_usd=used,
        limit_usd=limit,
        remaining_usd=max(limit - used, 0.0),
        percentage=min(max((used / limit) * 100, 0.0), 100.0),
        window_start=_datetime_or_none(
            raw_window_start, f"{field}.fallback_window_start"
        ),
        resets_at=None,
        resets_in_seconds=None,
    )


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Sub2APIModelError(f"{field} must be an object")
    return value


def _optional_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Sub2APIModelError(f"{field} must be an integer")
    return value


def _nonnegative_integer(value: Any, field: str) -> int:
    parsed = _integer(value, field)
    if parsed < 0:
        raise Sub2APIModelError(f"{field} must not be negative")
    return parsed


def _integer_or_none(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _integer(value, field)


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Sub2APIModelError(f"{field} must be a number")
    return float(value)


def _number_or_none(value: Any, field: str) -> float | None:
    if value is None:
        return None
    return _number(value, field)


def _number_or_default(value: Any, field: str, default: float) -> float:
    if value is None:
        return default
    return _number(value, field)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _required_text(value: Any, field: str) -> str:
    parsed = _text(value)
    if not parsed:
        raise Sub2APIModelError(f"{field} must be a non-empty string")
    return parsed


def _datetime_or_none(value: Any, field: str) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise Sub2APIModelError(f"{field} must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise Sub2APIModelError(f"{field} must be an ISO 8601 string") from err
    if parsed.tzinfo is None:
        raise Sub2APIModelError(f"{field} must include a timezone")
    return parsed
