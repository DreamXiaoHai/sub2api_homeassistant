"""Tests for the sub2API config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sub2api.api import Sub2APIAuthError, site_identifier
from custom_components.sub2api.const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.sub2api.models import UserInfo


async def test_user_flow_creates_entry(hass) -> None:
    validated = {
        CONF_BASE_URL: "https://example.com",
        CONF_ACCESS_TOKEN: "access",
        CONF_REFRESH_TOKEN: "refresh",
        CONF_USER_ID: 7,
        CONF_USERNAME: "tester",
    }
    with (
        patch(
            "custom_components.sub2api.config_flow.Sub2APIConfigFlow._async_validate",
            AsyncMock(
                return_value=(validated, UserInfo(7, "tester", "user@example.com"))
            ),
        ),
        patch(
            "custom_components.sub2api.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_BASE_URL: "https://example.com",
                CONF_ACCESS_TOKEN: "access",
                CONF_REFRESH_TOKEN: "refresh",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == validated
    assert result["result"].unique_id is not None


async def test_user_flow_rejects_http_url(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={
            CONF_BASE_URL: "http://example.com",
            CONF_ACCESS_TOKEN: "access",
            CONF_REFRESH_TOKEN: "refresh",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}


async def test_user_flow_rejects_bad_tokens(hass) -> None:
    with patch(
        "custom_components.sub2api.config_flow.Sub2APIConfigFlow._async_validate",
        AsyncMock(side_effect=Sub2APIAuthError),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_BASE_URL: "https://example.com",
                CONF_ACCESS_TOKEN: "bad",
                CONF_REFRESH_TOKEN: "bad",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_duplicate_account_is_rejected(hass) -> None:
    validated = {
        CONF_BASE_URL: "https://example.com",
        CONF_ACCESS_TOKEN: "access",
        CONF_REFRESH_TOKEN: "refresh",
        CONF_USER_ID: 7,
        CONF_USERNAME: "tester",
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=validated,
        unique_id=f"{site_identifier(validated[CONF_BASE_URL])}:7",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.sub2api.config_flow.Sub2APIConfigFlow._async_validate",
        AsyncMock(return_value=(validated, UserInfo(7, "tester", "user@example.com"))),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_BASE_URL: "https://example.com",
                CONF_ACCESS_TOKEN: "access",
                CONF_REFRESH_TOKEN: "refresh",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_rotated_tokens(hass) -> None:
    original = {
        CONF_BASE_URL: "https://example.com",
        CONF_ACCESS_TOKEN: "old-access",
        CONF_REFRESH_TOKEN: "old-refresh",
        CONF_USER_ID: 7,
        CONF_USERNAME: "tester",
    }
    entry = MockConfigEntry(domain=DOMAIN, data=original)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=original,
    )
    assert result["type"] is FlowResultType.FORM

    updated = {
        **original,
        CONF_ACCESS_TOKEN: "new-access",
        CONF_REFRESH_TOKEN: "new-refresh",
    }
    with (
        patch(
            "custom_components.sub2api.config_flow.Sub2APIConfigFlow._async_validate",
            AsyncMock(
                return_value=(updated, UserInfo(7, "tester", "user@example.com"))
            ),
        ),
        patch(
            "custom_components.sub2api.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ACCESS_TOKEN: "new-access",
                CONF_REFRESH_TOKEN: "new-refresh",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "new-access"
    assert entry.data[CONF_REFRESH_TOKEN] == "new-refresh"
