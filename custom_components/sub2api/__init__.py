"""sub2API subscription integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Sub2APIClient
from .const import (
    AUTH_METHOD_CREDENTIALS,
    AUTH_METHOD_TOKEN,
    CONF_ACCESS_TOKEN,
    CONF_AUTH_METHOD,
    CONF_BASE_URL,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    PLATFORMS,
    Sub2APIConfigEntry,
    Sub2APIRuntimeData,
)
from .coordinator import (
    Sub2APIDataUpdateCoordinator,
    Sub2APIUsageDataUpdateCoordinator,
)


async def async_setup_entry(hass: HomeAssistant, entry: Sub2APIConfigEntry) -> bool:
    """Set up sub2API from a config entry."""

    @callback
    def async_update_tokens(access_token: str, refresh_token: str) -> None:
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_ACCESS_TOKEN: access_token,
                CONF_REFRESH_TOKEN: refresh_token,
            },
        )

    client = Sub2APIClient(
        async_get_clientsession(hass),
        entry.data[CONF_BASE_URL],
        entry.data[CONF_ACCESS_TOKEN],
        entry.data[CONF_REFRESH_TOKEN],
        async_update_tokens,
        email=(
            entry.data.get(CONF_EMAIL, "")
            if entry.data.get(CONF_AUTH_METHOD) == AUTH_METHOD_CREDENTIALS
            else ""
        ),
        password=(
            entry.data.get(CONF_PASSWORD, "")
            if entry.data.get(CONF_AUTH_METHOD) == AUTH_METHOD_CREDENTIALS
            else ""
        ),
    )
    coordinator = Sub2APIDataUpdateCoordinator(hass, client, entry)
    usage_coordinator = Sub2APIUsageDataUpdateCoordinator(hass, client, entry)
    entry.runtime_data = Sub2APIRuntimeData(client, coordinator, usage_coordinator)

    await coordinator.async_config_entry_first_refresh()
    await usage_coordinator.async_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Sub2APIConfigEntry) -> bool:
    """Unload a sub2API config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: Sub2APIConfigEntry) -> bool:
    """Migrate token-only entries to the explicit hybrid authentication schema."""

    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_AUTH_METHOD: AUTH_METHOD_TOKEN},
            version=2,
        )
    return True
