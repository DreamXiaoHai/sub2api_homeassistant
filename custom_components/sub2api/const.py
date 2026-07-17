"""Constants and runtime types for the sub2API integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

if TYPE_CHECKING:
    from .api import Sub2APIClient
    from .coordinator import (
        Sub2APIDataUpdateCoordinator,
        Sub2APIUsageDataUpdateCoordinator,
    )

DOMAIN = "sub2api"
PLATFORMS = (Platform.SENSOR,)

CONF_ACCESS_TOKEN = "access_token"
CONF_BASE_URL = "base_url"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_USER_ID = "user_id"
CONF_USERNAME = "username"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)


@dataclass(slots=True)
class Sub2APIRuntimeData:
    """Runtime objects associated with a config entry."""

    client: Sub2APIClient
    coordinator: Sub2APIDataUpdateCoordinator
    usage_coordinator: Sub2APIUsageDataUpdateCoordinator


type Sub2APIConfigEntry = ConfigEntry[Sub2APIRuntimeData]
