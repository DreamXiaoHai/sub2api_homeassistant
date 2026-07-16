"""DataUpdateCoordinator for sub2API subscription data."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Sub2APIAuthError, Sub2APIClient, Sub2APIError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, Sub2APIConfigEntry
from .models import Subscription

_LOGGER = logging.getLogger(__name__)


class Sub2APIDataUpdateCoordinator(DataUpdateCoordinator[dict[int, Subscription]]):
    """Coordinate subscription quota updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: Sub2APIClient,
        entry: Sub2APIConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[int, Subscription]:
        try:
            return await self.client.async_get_subscriptions()
        except Sub2APIAuthError as err:
            raise ConfigEntryAuthFailed("sub2API authentication expired") from err
        except (Sub2APIError, ValueError) as err:
            raise UpdateFailed(str(err)) from err
