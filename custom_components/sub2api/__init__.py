"""sub2API subscription integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Sub2APIClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL,
    CONF_REFRESH_TOKEN,
    PLATFORMS,
    Sub2APIConfigEntry,
    Sub2APIRuntimeData,
)
from .coordinator import Sub2APIDataUpdateCoordinator


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
    )
    coordinator = Sub2APIDataUpdateCoordinator(hass, client, entry)
    entry.runtime_data = Sub2APIRuntimeData(client, coordinator)

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Sub2APIConfigEntry) -> bool:
    """Unload a sub2API config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
