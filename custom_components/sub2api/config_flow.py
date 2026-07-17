"""Config flow for the sub2API integration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    Sub2APIAuthError,
    Sub2APIClient,
    Sub2APIConnectionError,
    Sub2APICredentialsError,
    Sub2APIError,
    normalize_base_url,
    site_identifier,
)
from .const import (
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
    Sub2APIConfigEntry,
)
from .models import Sub2APIModelError, UserInfo

AUTH_METHOD_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[AUTH_METHOD_CREDENTIALS, AUTH_METHOD_TOKEN],
        translation_key="auth_method",
    )
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Required(
            CONF_AUTH_METHOD, default=AUTH_METHOD_CREDENTIALS
        ): AUTH_METHOD_SELECTOR,
    }
)

TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_REFRESH_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

TOTP_SCHEMA = vol.Schema(
    {
        vol.Required("totp_code"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class WrongAccountError(Sub2APIAuthError):
    """Credentials or tokens belong to another configured account."""


class Sub2APIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a sub2API config flow."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the site and authentication method."""

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._base_url = normalize_base_url(str(user_input[CONF_BASE_URL]))
            except ValueError:
                errors["base"] = "invalid_url"
            else:
                self._auth_method = str(user_input[CONF_AUTH_METHOD])
                if self._auth_method == AUTH_METHOD_CREDENTIALS:
                    return await self.async_step_credentials()
                return await self.async_step_tokens()

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign in with an email address and password."""

        errors: dict[str, str] = {}
        if user_input is not None:
            email = str(user_input[CONF_EMAIL]).strip()
            password = str(user_input[CONF_PASSWORD])
            client = self._new_client(email=email, password=password)
            try:
                challenge = await client.async_login(email, password)
                if challenge is not None:
                    self._pending_client = client
                    self._pending_challenge = challenge
                    self._credentials = {
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    }
                    return await self.async_step_totp()
                return await self._async_finish(
                    client,
                    {
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    },
                )
            except WrongAccountError:
                errors["base"] = "wrong_account"
            except Sub2APICredentialsError:
                errors["base"] = "invalid_credentials"
            except Sub2APIAuthError:
                errors["base"] = "invalid_auth"
            except Sub2APIConnectionError:
                errors["base"] = "cannot_connect"
            except (Sub2APIModelError, Sub2APIError, ValueError):
                errors["base"] = "invalid_response"
            except AbortFlow:
                raise
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="credentials",
            data_schema=_credentials_schema(self._saved_email),
            errors=errors,
        )

    async def async_step_tokens(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Authenticate with a manually supplied token pair."""

        errors: dict[str, str] = {}
        if user_input is not None:
            client = self._new_client(
                access_token=str(user_input[CONF_ACCESS_TOKEN]),
                refresh_token=str(user_input[CONF_REFRESH_TOKEN]),
            )
            try:
                return await self._async_finish(client, {})
            except WrongAccountError:
                errors["base"] = "wrong_account"
            except Sub2APIAuthError:
                errors["base"] = "invalid_auth"
            except Sub2APIConnectionError:
                errors["base"] = "cannot_connect"
            except (Sub2APIModelError, Sub2APIError, ValueError):
                errors["base"] = "invalid_response"
            except AbortFlow:
                raise
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="tokens", data_schema=TOKEN_SCHEMA, errors=errors
        )

    async def async_step_totp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete a password login using a current TOTP code."""

        challenge = self._pending_challenge
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._pending_client.async_complete_totp(
                    challenge.temp_token, str(user_input["totp_code"])
                )
                return await self._async_finish(self._pending_client, self._credentials)
            except WrongAccountError:
                errors["base"] = "wrong_account"
            except Sub2APICredentialsError:
                errors["base"] = "invalid_totp"
            except Sub2APIAuthError:
                errors["base"] = "invalid_auth"
            except Sub2APIConnectionError:
                errors["base"] = "cannot_connect"
            except (Sub2APIModelError, Sub2APIError, ValueError):
                errors["base"] = "invalid_response"
            except AbortFlow:
                raise
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        email = challenge.user_email_masked or self._credentials[CONF_EMAIL]
        return self.async_show_form(
            step_id="totp",
            data_schema=TOTP_SCHEMA,
            errors=errors,
            description_placeholders={"email": email},
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication for an existing entry."""

        self._reauth_entry = self._get_reauth_entry()
        self._base_url = self._reauth_entry.data[CONF_BASE_URL]
        self._auth_method = self._reauth_entry.data.get(
            CONF_AUTH_METHOD, AUTH_METHOD_TOKEN
        )

        if self._auth_method == AUTH_METHOD_CREDENTIALS:
            email = self._reauth_entry.data.get(CONF_EMAIL, "")
            password = self._reauth_entry.data.get(CONF_PASSWORD, "")
            if email and password:
                client = self._new_client(email=email, password=password)
                try:
                    challenge = await client.async_login(email, password)
                    if challenge is not None:
                        self._pending_client = client
                        self._pending_challenge = challenge
                        self._credentials = {
                            CONF_EMAIL: email,
                            CONF_PASSWORD: password,
                        }
                        return await self.async_step_totp()
                    return await self._async_finish(
                        client,
                        {
                            CONF_EMAIL: email,
                            CONF_PASSWORD: password,
                        },
                    )
                except WrongAccountError:
                    return self._show_reauth_method({"base": "wrong_account"})
                except Sub2APICredentialsError:
                    return self._show_reauth_method({"base": "invalid_credentials"})
                except Sub2APIConnectionError:
                    return self._show_reauth_method({"base": "cannot_connect"})
                except (Sub2APIAuthError, Sub2APIError, ValueError):
                    return self._show_reauth_method({"base": "invalid_auth"})

        return await self.async_step_reauth_confirm()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow an existing entry to switch authentication methods."""

        if not hasattr(self, "_reauth_entry"):
            self._reauth_entry = self._get_reconfigure_entry()
            self._base_url = self._reauth_entry.data[CONF_BASE_URL]
            current_method = self._reauth_entry.data.get(
                CONF_AUTH_METHOD, AUTH_METHOD_TOKEN
            )
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=_auth_method_schema(current_method),
            )

        if user_input is not None:
            self._auth_method = str(user_input[CONF_AUTH_METHOD])
            if self._auth_method == AUTH_METHOD_CREDENTIALS:
                return await self.async_step_credentials()
            return await self.async_step_tokens()

        current_method = self._reauth_entry.data.get(
            CONF_AUTH_METHOD, AUTH_METHOD_TOKEN
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_auth_method_schema(current_method),
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how to reconnect an existing account."""

        if user_input is not None:
            self._auth_method = str(user_input[CONF_AUTH_METHOD])
            if self._auth_method == AUTH_METHOD_CREDENTIALS:
                return await self.async_step_credentials()
            return await self.async_step_tokens()
        return self._show_reauth_method({})

    async def _async_finish(
        self,
        client: Sub2APIClient,
        credentials: dict[str, str],
    ) -> ConfigFlowResult:
        user = await client.async_get_user()
        await client.async_get_subscriptions()

        data = {
            CONF_BASE_URL: self._base_url,
            CONF_AUTH_METHOD: self._auth_method,
            CONF_ACCESS_TOKEN: client.access_token,
            CONF_REFRESH_TOKEN: client.refresh_token,
            CONF_USER_ID: user.user_id,
            CONF_USERNAME: user.username or user.email,
            **credentials,
        }

        reauth_entry: Sub2APIConfigEntry | None = getattr(self, "_reauth_entry", None)
        if reauth_entry is not None:
            if user.user_id != reauth_entry.data[CONF_USER_ID]:
                raise WrongAccountError
            self.hass.config_entries.async_update_entry(
                reauth_entry, version=self.VERSION
            )
            return self.async_update_reload_and_abort(reauth_entry, data=data)

        await self.async_set_unique_id(
            f"{site_identifier(self._base_url)}:{user.user_id}"
        )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=_entry_title(self._base_url, user), data=data
        )

    def _new_client(
        self,
        access_token: str = "",
        refresh_token: str = "",
        *,
        email: str = "",
        password: str = "",
    ) -> Sub2APIClient:
        return Sub2APIClient(
            async_get_clientsession(self.hass),
            self._base_url,
            access_token,
            refresh_token,
            email=email,
            password=password,
        )

    def _show_reauth_method(self, errors: dict[str, str]) -> ConfigFlowResult:
        current_method = self._reauth_entry.data.get(
            CONF_AUTH_METHOD, AUTH_METHOD_TOKEN
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_auth_method_schema(current_method),
            errors=errors,
        )

    @property
    def _saved_email(self) -> str | None:
        reauth_entry: Sub2APIConfigEntry | None = getattr(self, "_reauth_entry", None)
        if reauth_entry is None:
            return None
        return reauth_entry.data.get(CONF_EMAIL)


def _credentials_schema(email: str | None) -> vol.Schema:
    email_key = (
        vol.Required(CONF_EMAIL, default=email) if email else vol.Required(CONF_EMAIL)
    )
    return vol.Schema(
        {
            email_key: TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


def _auth_method_schema(current_method: str) -> vol.Schema:
    return vol.Schema(
        {vol.Required(CONF_AUTH_METHOD, default=current_method): AUTH_METHOD_SELECTOR}
    )


def _entry_title(base_url: str, user: UserInfo) -> str:
    account = user.username or user.email or str(user.user_id)
    host = urlsplit(base_url).hostname or base_url
    return f"sub2API {account} ({host})"
