"""Config flow for the sub2API integration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    Sub2APIAuthError,
    Sub2APIClient,
    Sub2APIConnectionError,
    Sub2APIError,
    normalize_base_url,
    site_identifier,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
)
from .models import Sub2APIModelError, UserInfo

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Required(CONF_ACCESS_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_REFRESH_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_REFRESH_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class Sub2APIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a sub2API config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a sub2API account."""

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data, user = await self._async_validate(user_input)
            except Sub2APIAuthError:
                errors["base"] = "invalid_auth"
            except Sub2APIConnectionError:
                errors["base"] = "cannot_connect"
            except Sub2APIModelError:
                errors["base"] = "invalid_response"
            except Sub2APIError:
                errors["base"] = "invalid_response"
            except ValueError:
                errors["base"] = "invalid_url"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    f"{site_identifier(data[CONF_BASE_URL])}:{user.user_id}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_entry_title(data[CONF_BASE_URL], user), data=data
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication for an existing entry."""

        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate replacement access and refresh tokens."""

        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = {
                CONF_BASE_URL: self._reauth_entry.data[CONF_BASE_URL],
                CONF_ACCESS_TOKEN: user_input[CONF_ACCESS_TOKEN],
                CONF_REFRESH_TOKEN: user_input[CONF_REFRESH_TOKEN],
            }
            try:
                data, user = await self._async_validate(candidate)
            except Sub2APIAuthError:
                errors["base"] = "invalid_auth"
            except Sub2APIConnectionError:
                errors["base"] = "cannot_connect"
            except Sub2APIModelError:
                errors["base"] = "invalid_response"
            except Sub2APIError:
                errors["base"] = "invalid_response"
            except ValueError:
                errors["base"] = "invalid_url"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                if user.user_id != self._reauth_entry.data[CONF_USER_ID]:
                    errors["base"] = "wrong_account"
                else:
                    return self.async_update_reload_and_abort(
                        self._reauth_entry,
                        data_updates=data,
                    )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=REAUTH_SCHEMA, errors=errors
        )

    async def _async_validate(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any], UserInfo]:
        base_url = normalize_base_url(str(user_input[CONF_BASE_URL]))
        rotated_tokens: dict[str, str] = {}

        def capture_tokens(access_token: str, refresh_token: str) -> None:
            rotated_tokens[CONF_ACCESS_TOKEN] = access_token
            rotated_tokens[CONF_REFRESH_TOKEN] = refresh_token

        client = Sub2APIClient(
            async_get_clientsession(self.hass),
            base_url,
            str(user_input[CONF_ACCESS_TOKEN]),
            str(user_input[CONF_REFRESH_TOKEN]),
            capture_tokens,
        )
        user = await client.async_get_user()
        await client.async_get_subscriptions()

        data = {
            CONF_BASE_URL: base_url,
            CONF_ACCESS_TOKEN: rotated_tokens.get(
                CONF_ACCESS_TOKEN, client.access_token
            ),
            CONF_REFRESH_TOKEN: rotated_tokens.get(
                CONF_REFRESH_TOKEN, client.refresh_token
            ),
            CONF_USER_ID: user.user_id,
            CONF_USERNAME: user.username or user.email,
        }
        return data, user


def _entry_title(base_url: str, user: UserInfo) -> str:
    account = user.username or user.email or str(user.user_id)
    host = urlsplit(base_url).hostname or base_url
    return f"sub2API {account} ({host})"
