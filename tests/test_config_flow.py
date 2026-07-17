"""Tests for the sub2API config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sub2api import async_migrate_entry
from custom_components.sub2api.api import (
    Sub2APIAuthError,
    Sub2APIClient,
    Sub2APICredentialsError,
    site_identifier,
)
from custom_components.sub2api.const import (
    AUTH_METHOD_CREDENTIALS,
    AUTH_METHOD_TOKEN,
    CONF_ACCESS_TOKEN,
    CONF_AUTH_METHOD,
    CONF_BASE_URL,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.sub2api.models import TotpChallenge, UserInfo

BASE_URL = "https://example.com"
USER = UserInfo(7, "tester", "user@example.com")


@pytest.fixture(autouse=True)
def mock_client_session():
    """Avoid starting the Windows async DNS resolver in config-flow tests."""

    with patch(
        "custom_components.sub2api.config_flow.async_get_clientsession",
        return_value=MagicMock(),
    ):
        yield


async def _start_user_flow(hass, auth_method: str):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_BASE_URL: BASE_URL,
            CONF_AUTH_METHOD: auth_method,
        },
    )


async def _login_success(client: Sub2APIClient, email: str, password: str) -> None:
    client.email = email
    client.password = password
    client.access_token = "credential-access"
    client.refresh_token = "credential-refresh"
    return None


async def _complete_totp_success(
    client: Sub2APIClient, temp_token: str, code: str
) -> None:
    assert temp_token == "temporary-login"
    assert code == "123456"
    client.access_token = "totp-access"
    client.refresh_token = "totp-refresh"


async def test_token_flow_creates_entry(hass) -> None:
    result = await _start_user_flow(hass, AUTH_METHOD_TOKEN)
    assert result["step_id"] == "tokens"

    with (
        patch.object(Sub2APIClient, "async_get_user", AsyncMock(return_value=USER)),
        patch.object(
            Sub2APIClient, "async_get_subscriptions", AsyncMock(return_value={})
        ),
        patch(
            "custom_components.sub2api.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ACCESS_TOKEN: "access",
                CONF_REFRESH_TOKEN: "refresh",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_BASE_URL: BASE_URL,
        CONF_AUTH_METHOD: AUTH_METHOD_TOKEN,
        CONF_ACCESS_TOKEN: "access",
        CONF_REFRESH_TOKEN: "refresh",
        CONF_USER_ID: 7,
        CONF_USERNAME: "tester",
    }


async def test_credentials_flow_stores_password_and_tokens(hass) -> None:
    result = await _start_user_flow(hass, AUTH_METHOD_CREDENTIALS)
    assert result["step_id"] == "credentials"

    with (
        patch.object(Sub2APIClient, "async_login", _login_success),
        patch.object(Sub2APIClient, "async_get_user", AsyncMock(return_value=USER)),
        patch.object(
            Sub2APIClient, "async_get_subscriptions", AsyncMock(return_value={})
        ),
        patch(
            "custom_components.sub2api.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "secret-password",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTH_METHOD] == AUTH_METHOD_CREDENTIALS
    assert result["data"][CONF_EMAIL] == "user@example.com"
    assert result["data"][CONF_PASSWORD] == "secret-password"
    assert result["data"][CONF_ACCESS_TOKEN] == "credential-access"
    assert result["data"][CONF_REFRESH_TOKEN] == "credential-refresh"


async def test_credentials_flow_supports_totp(hass) -> None:
    result = await _start_user_flow(hass, AUTH_METHOD_CREDENTIALS)

    with patch.object(
        Sub2APIClient,
        "async_login",
        AsyncMock(return_value=TotpChallenge("temporary-login", "u***@example.com")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "secret-password",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "totp"

    with (
        patch.object(Sub2APIClient, "async_complete_totp", _complete_totp_success),
        patch.object(Sub2APIClient, "async_get_user", AsyncMock(return_value=USER)),
        patch.object(
            Sub2APIClient, "async_get_subscriptions", AsyncMock(return_value={})
        ),
        patch(
            "custom_components.sub2api.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"totp_code": "123456"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ACCESS_TOKEN] == "totp-access"
    assert result["data"][CONF_REFRESH_TOKEN] == "totp-refresh"
    assert "totp_code" not in result["data"]
    assert "temp_token" not in result["data"]


async def test_user_flow_rejects_http_url(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_BASE_URL: "http://example.com",
            CONF_AUTH_METHOD: AUTH_METHOD_TOKEN,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_url"}


async def test_token_flow_rejects_bad_tokens(hass) -> None:
    result = await _start_user_flow(hass, AUTH_METHOD_TOKEN)
    with patch.object(
        Sub2APIClient, "async_get_user", AsyncMock(side_effect=Sub2APIAuthError)
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ACCESS_TOKEN: "bad",
                CONF_REFRESH_TOKEN: "bad",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "tokens"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_duplicate_account_is_rejected(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BASE_URL: BASE_URL,
            CONF_AUTH_METHOD: AUTH_METHOD_TOKEN,
            CONF_ACCESS_TOKEN: "existing-access",
            CONF_REFRESH_TOKEN: "existing-refresh",
            CONF_USER_ID: 7,
            CONF_USERNAME: "tester",
        },
        unique_id=f"{site_identifier(BASE_URL)}:7",
    )
    entry.add_to_hass(hass)
    result = await _start_user_flow(hass, AUTH_METHOD_TOKEN)

    with (
        patch.object(Sub2APIClient, "async_get_user", AsyncMock(return_value=USER)),
        patch.object(
            Sub2APIClient, "async_get_subscriptions", AsyncMock(return_value={})
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ACCESS_TOKEN: "access",
                CONF_REFRESH_TOKEN: "refresh",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_can_switch_from_tokens_to_credentials(hass) -> None:
    original = {
        CONF_BASE_URL: BASE_URL,
        CONF_AUTH_METHOD: AUTH_METHOD_TOKEN,
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
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_AUTH_METHOD: AUTH_METHOD_CREDENTIALS}
    )
    assert result["step_id"] == "credentials"

    with (
        patch.object(Sub2APIClient, "async_login", _login_success),
        patch.object(Sub2APIClient, "async_get_user", AsyncMock(return_value=USER)),
        patch.object(
            Sub2APIClient, "async_get_subscriptions", AsyncMock(return_value={})
        ),
        patch(
            "custom_components.sub2api.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "new-password",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_AUTH_METHOD] == AUTH_METHOD_CREDENTIALS
    assert entry.data[CONF_PASSWORD] == "new-password"
    assert entry.data[CONF_ACCESS_TOKEN] == "credential-access"


async def test_reauth_rejects_a_different_account(hass) -> None:
    original = {
        CONF_BASE_URL: BASE_URL,
        CONF_AUTH_METHOD: AUTH_METHOD_TOKEN,
        CONF_ACCESS_TOKEN: "old-access",
        CONF_REFRESH_TOKEN: "old-refresh",
        CONF_USER_ID: 7,
        CONF_USERNAME: "tester",
    }
    entry = MockConfigEntry(domain=DOMAIN, version=2, data=original)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=original,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_AUTH_METHOD: AUTH_METHOD_TOKEN}
    )

    with (
        patch.object(
            Sub2APIClient,
            "async_get_user",
            AsyncMock(return_value=UserInfo(8, "other", "other@example.com")),
        ),
        patch.object(
            Sub2APIClient, "async_get_subscriptions", AsyncMock(return_value={})
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ACCESS_TOKEN: "other-access",
                CONF_REFRESH_TOKEN: "other-refresh",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "tokens"
    assert result["errors"] == {"base": "wrong_account"}
    assert entry.data == original


async def test_reauth_uses_saved_credentials_and_prompts_for_totp(hass) -> None:
    original = {
        CONF_BASE_URL: BASE_URL,
        CONF_AUTH_METHOD: AUTH_METHOD_CREDENTIALS,
        CONF_EMAIL: "user@example.com",
        CONF_PASSWORD: "saved-password",
        CONF_ACCESS_TOKEN: "old-access",
        CONF_REFRESH_TOKEN: "old-refresh",
        CONF_USER_ID: 7,
        CONF_USERNAME: "tester",
    }
    entry = MockConfigEntry(domain=DOMAIN, data=original)
    entry.add_to_hass(hass)

    with patch.object(
        Sub2APIClient,
        "async_login",
        AsyncMock(return_value=TotpChallenge("temporary-login", "u***@example.com")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=original,
        )

    assert result["step_id"] == "totp"

    with (
        patch.object(Sub2APIClient, "async_complete_totp", _complete_totp_success),
        patch.object(Sub2APIClient, "async_get_user", AsyncMock(return_value=USER)),
        patch.object(
            Sub2APIClient, "async_get_subscriptions", AsyncMock(return_value={})
        ),
        patch(
            "custom_components.sub2api.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"totp_code": "123456"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "saved-password"
    assert entry.data[CONF_ACCESS_TOKEN] == "totp-access"


async def test_reauth_can_switch_from_credentials_to_tokens(hass) -> None:
    original = {
        CONF_BASE_URL: BASE_URL,
        CONF_AUTH_METHOD: AUTH_METHOD_CREDENTIALS,
        CONF_EMAIL: "user@example.com",
        CONF_PASSWORD: "saved-password",
        CONF_ACCESS_TOKEN: "old-access",
        CONF_REFRESH_TOKEN: "old-refresh",
        CONF_USER_ID: 7,
        CONF_USERNAME: "tester",
    }
    entry = MockConfigEntry(domain=DOMAIN, version=2, data=original)
    entry.add_to_hass(hass)

    with patch.object(
        Sub2APIClient,
        "async_login",
        AsyncMock(side_effect=Sub2APICredentialsError),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=original,
        )

    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_AUTH_METHOD: AUTH_METHOD_TOKEN}
    )
    assert result["step_id"] == "tokens"

    with (
        patch.object(Sub2APIClient, "async_get_user", AsyncMock(return_value=USER)),
        patch.object(
            Sub2APIClient, "async_get_subscriptions", AsyncMock(return_value={})
        ),
        patch(
            "custom_components.sub2api.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ACCESS_TOKEN: "manual-access",
                CONF_REFRESH_TOKEN: "manual-refresh",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert entry.data[CONF_AUTH_METHOD] == AUTH_METHOD_TOKEN
    assert entry.data[CONF_ACCESS_TOKEN] == "manual-access"
    assert CONF_EMAIL not in entry.data
    assert CONF_PASSWORD not in entry.data


async def test_reconfigure_can_change_authentication_method(hass) -> None:
    original = {
        CONF_BASE_URL: BASE_URL,
        CONF_AUTH_METHOD: AUTH_METHOD_TOKEN,
        CONF_ACCESS_TOKEN: "old-access",
        CONF_REFRESH_TOKEN: "old-refresh",
        CONF_USER_ID: 7,
        CONF_USERNAME: "tester",
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id=f"{site_identifier(BASE_URL)}:7",
        data=original,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
        data=original,
    )
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_AUTH_METHOD: AUTH_METHOD_CREDENTIALS}
    )
    assert result["step_id"] == "credentials"

    with (
        patch.object(Sub2APIClient, "async_login", _login_success),
        patch.object(Sub2APIClient, "async_get_user", AsyncMock(return_value=USER)),
        patch.object(
            Sub2APIClient, "async_get_subscriptions", AsyncMock(return_value={})
        ),
        patch(
            "custom_components.sub2api.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_EMAIL: "user@example.com",
                CONF_PASSWORD: "new-password",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_AUTH_METHOD] == AUTH_METHOD_CREDENTIALS
    assert entry.data[CONF_PASSWORD] == "new-password"


async def test_version_one_entry_migrates_to_manual_tokens(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={
            CONF_BASE_URL: BASE_URL,
            CONF_ACCESS_TOKEN: "access",
            CONF_REFRESH_TOKEN: "refresh",
            CONF_USER_ID: 7,
            CONF_USERNAME: "tester",
        },
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 2
    assert entry.data[CONF_AUTH_METHOD] == AUTH_METHOD_TOKEN
