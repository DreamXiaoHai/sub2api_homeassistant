"""Integration tests for subscription sensors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sub2api.api import Sub2APIAuthError, Sub2APIConnectionError
from custom_components.sub2api.const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.sub2api.models import parse_dashboard_stats, parse_subscriptions


async def test_eight_sensors_and_dynamic_availability(
    hass, progress_payload, dashboard_payload
) -> None:
    subscriptions = parse_subscriptions(progress_payload)
    dashboard_stats = parse_dashboard_stats(dashboard_payload)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="sub2API tester",
        data={
            CONF_BASE_URL: "https://example.com",
            CONF_ACCESS_TOKEN: "access",
            CONF_REFRESH_TOKEN: "refresh",
            CONF_USER_ID: 7,
            CONF_USERNAME: "tester",
        },
        unique_id="example:7",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.sub2api.api.Sub2APIClient.async_get_subscriptions",
            AsyncMock(return_value=subscriptions),
        ),
        patch(
            "custom_components.sub2api.api.Sub2APIClient.async_get_dashboard_stats",
            AsyncMock(return_value=dashboard_stats),
        ),
        patch(
            "custom_components.sub2api.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entities) == 8

    used_entry = next(
        item for item in entities if item.unique_id.endswith("daily_used")
    )
    used_state = hass.states.get(used_entry.entity_id)
    assert used_state is not None
    assert used_state.state == "29.61"
    assert used_state.attributes["remaining_usd"] == 270.39
    assert used_state.attributes["percentage"] == 9.87

    today_entry = next(
        item for item in entities if item.unique_id.endswith("today_tokens")
    )
    today_state = hass.states.get(today_entry.entity_id)
    assert today_state is not None
    assert today_state.state == "3000000"
    assert today_state.attributes["input_tokens"] == 621_800
    assert today_state.attributes["output_tokens"] == 55_500
    assert today_state.attributes["cache_read_tokens"] == 2_300_000

    total_entry = next(
        item for item in entities if item.unique_id.endswith("total_tokens")
    )
    total_state = hass.states.get(total_entry.entity_id)
    assert total_state is not None
    assert total_state.state == "395900000"
    assert total_state.attributes["input_tokens"] == 11_500_000
    assert total_state.attributes["output_tokens"] == 800_600

    coordinator = entry.runtime_data.coordinator
    coordinator.async_set_updated_data({})
    await hass.async_block_till_done()
    assert hass.states.get(used_entry.entity_id).state == "unavailable"


async def test_new_weekly_window_adds_entities(
    hass, progress_payload, dashboard_payload
) -> None:
    progress_payload[0]["progress"]["weekly"] = None
    progress_payload[0]["subscription"]["group"]["weekly_limit_usd"] = None
    daily_only = parse_subscriptions(progress_payload)
    dashboard_stats = parse_dashboard_stats(dashboard_payload)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: "https://example.com",
            CONF_ACCESS_TOKEN: "access",
            CONF_REFRESH_TOKEN: "refresh",
            CONF_USER_ID: 7,
            CONF_USERNAME: "tester",
        },
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.sub2api.api.Sub2APIClient.async_get_subscriptions",
            AsyncMock(return_value=daily_only),
        ),
        patch(
            "custom_components.sub2api.api.Sub2APIClient.async_get_dashboard_stats",
            AsyncMock(return_value=dashboard_stats),
        ),
        patch(
            "custom_components.sub2api.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 5

    progress_payload[0]["subscription"]["group"]["weekly_limit_usd"] = 600.0
    progress_payload[0]["progress"]["weekly"] = {
        "limit_usd": 600.0,
        "used_usd": 64.09,
        "remaining_usd": 535.91,
        "percentage": 10.6816666667,
        "window_start": "2026-07-14T00:00:00Z",
        "resets_at": "2026-07-21T00:00:00Z",
        "resets_in_seconds": 479940,
    }
    entry.runtime_data.coordinator.async_set_updated_data(
        parse_subscriptions(progress_payload)
    )
    await hass.async_block_till_done()

    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 8


async def test_usage_failure_does_not_block_quota_sensors(
    hass, progress_payload
) -> None:
    subscriptions = parse_subscriptions(progress_payload)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="sub2API tester",
        data={
            CONF_BASE_URL: "https://example.com",
            CONF_ACCESS_TOKEN: "access",
            CONF_REFRESH_TOKEN: "refresh",
            CONF_USER_ID: 7,
            CONF_USERNAME: "tester",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.sub2api.api.Sub2APIClient.async_get_subscriptions",
            AsyncMock(return_value=subscriptions),
        ),
        patch(
            "custom_components.sub2api.api.Sub2APIClient.async_get_dashboard_stats",
            AsyncMock(side_effect=Sub2APIConnectionError("offline")),
        ),
        patch(
            "custom_components.sub2api.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    used_entry = next(
        item for item in entities if item.unique_id.endswith("daily_used")
    )
    today_entry = next(
        item for item in entities if item.unique_id.endswith("today_tokens")
    )

    assert hass.states.get(used_entry.entity_id).state == "29.61"
    assert hass.states.get(today_entry.entity_id).state == "unavailable"


async def test_auth_failure_starts_reauthentication(
    hass, progress_payload, dashboard_payload
) -> None:
    subscriptions = parse_subscriptions(progress_payload)
    dashboard_stats = parse_dashboard_stats(dashboard_payload)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: "https://example.com",
            CONF_ACCESS_TOKEN: "access",
            CONF_REFRESH_TOKEN: "refresh",
            CONF_USER_ID: 7,
            CONF_USERNAME: "tester",
        },
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.sub2api.api.Sub2APIClient.async_get_subscriptions",
            AsyncMock(return_value=subscriptions),
        ),
        patch(
            "custom_components.sub2api.api.Sub2APIClient.async_get_dashboard_stats",
            AsyncMock(return_value=dashboard_stats),
        ),
        patch(
            "custom_components.sub2api.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entry.runtime_data.client.async_get_subscriptions = AsyncMock(
        side_effect=Sub2APIAuthError("expired")
    )
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(
        flow["context"]["source"] == config_entries.SOURCE_REAUTH for flow in flows
    )
