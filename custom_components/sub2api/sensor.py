"""Sensor platform for sub2API quotas and token usage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import site_identifier
from .const import CONF_BASE_URL, CONF_USER_ID, DOMAIN, Sub2APIConfigEntry
from .coordinator import (
    Sub2APIDataUpdateCoordinator,
    Sub2APIUsageDataUpdateCoordinator,
)
from .models import DashboardStats, Subscription, UsageWindow


@dataclass(frozen=True, kw_only=True)
class Sub2APISensorDescription(SensorEntityDescription):
    """Describe a sub2API subscription sensor."""

    window: str
    metric: str
    value_fn: Callable[[UsageWindow], Any]


@dataclass(frozen=True, kw_only=True)
class Sub2APIAccountSensorDescription(SensorEntityDescription):
    """Describe an account-level sub2API token sensor."""

    period: str


SENSOR_DESCRIPTIONS = (
    Sub2APISensorDescription(
        key="daily_used",
        translation_key="daily_used",
        window="daily",
        metric="used",
        value_fn=lambda window: window.used_usd,
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
    ),
    Sub2APISensorDescription(
        key="daily_limit",
        translation_key="daily_limit",
        window="daily",
        metric="limit",
        value_fn=lambda window: window.limit_usd,
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
    ),
    Sub2APISensorDescription(
        key="daily_reset",
        translation_key="daily_reset",
        window="daily",
        metric="reset",
        value_fn=lambda window: window.resets_at,
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    Sub2APISensorDescription(
        key="weekly_used",
        translation_key="weekly_used",
        window="weekly",
        metric="used",
        value_fn=lambda window: window.used_usd,
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
    ),
    Sub2APISensorDescription(
        key="weekly_limit",
        translation_key="weekly_limit",
        window="weekly",
        metric="limit",
        value_fn=lambda window: window.limit_usd,
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
    ),
    Sub2APISensorDescription(
        key="weekly_reset",
        translation_key="weekly_reset",
        window="weekly",
        metric="reset",
        value_fn=lambda window: window.resets_at,
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

ACCOUNT_SENSOR_DESCRIPTIONS = (
    Sub2APIAccountSensorDescription(
        key="today_tokens",
        translation_key="today_tokens",
        period="today",
        native_unit_of_measurement="tokens",
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        icon="mdi:calendar-today",
    ),
    Sub2APIAccountSensorDescription(
        key="total_tokens",
        translation_key="total_tokens",
        period="total",
        native_unit_of_measurement="tokens",
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        icon="mdi:counter",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Sub2APIConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors and discover new subscriptions after refreshes."""

    coordinator = entry.runtime_data.coordinator
    usage_coordinator = entry.runtime_data.usage_coordinator
    known: set[tuple[int, str]] = set()

    async_add_entities(
        Sub2APIAccountTokenSensor(usage_coordinator, entry, description)
        for description in ACCOUNT_SENSOR_DESCRIPTIONS
    )

    @callback
    def async_add_missing_entities() -> None:
        entities: list[Sub2APISubscriptionSensor] = []
        for subscription in coordinator.data.values():
            for description in SENSOR_DESCRIPTIONS:
                entity_key = (subscription.subscription_id, description.key)
                if entity_key in known:
                    continue
                if getattr(subscription, description.window) is None:
                    continue
                known.add(entity_key)
                entities.append(
                    Sub2APISubscriptionSensor(
                        coordinator, entry, subscription.subscription_id, description
                    )
                )
        if entities:
            async_add_entities(entities)

    async_add_missing_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_add_missing_entities))


class Sub2APIAccountTokenSensor(
    CoordinatorEntity[Sub2APIUsageDataUpdateCoordinator], SensorEntity
):
    """One account-level token total from the sub2API dashboard."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Sub2APIUsageDataUpdateCoordinator,
        entry: Sub2APIConfigEntry,
        description: Sub2APIAccountSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._site_id = site_identifier(entry.data[CONF_BASE_URL])
        self._user_id = entry.data[CONF_USER_ID]
        self._base_url = entry.data[CONF_BASE_URL]
        self._device_name = entry.title
        self._attr_unique_id = f"{self._site_id}_{self._user_id}_{description.key}"

    @property
    def _stats(self) -> DashboardStats | None:
        return self.coordinator.data

    @property
    def available(self) -> bool:
        return super().available and self._stats is not None

    @property
    def native_value(self) -> int | None:
        stats = self._stats
        if stats is None:
            return None
        return getattr(stats, f"{self.entity_description.period}_tokens")

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        stats = self._stats
        if stats is None:
            return {}
        prefix = self.entity_description.period
        return {
            "input_tokens": getattr(stats, f"{prefix}_input_tokens"),
            "output_tokens": getattr(stats, f"{prefix}_output_tokens"),
            "cache_creation_tokens": getattr(stats, f"{prefix}_cache_creation_tokens"),
            "cache_read_tokens": getattr(stats, f"{prefix}_cache_read_tokens"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._site_id}_{self._user_id}_account")},
            name=self._device_name,
            manufacturer="sub2API",
            model="User dashboard",
            configuration_url=self._base_url,
        )


class Sub2APISubscriptionSensor(
    CoordinatorEntity[Sub2APIDataUpdateCoordinator], SensorEntity
):
    """One quota value for one sub2API subscription."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Sub2APIDataUpdateCoordinator,
        entry: Sub2APIConfigEntry,
        subscription_id: int,
        description: Sub2APISensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._subscription_id = subscription_id
        self._site_id = site_identifier(entry.data[CONF_BASE_URL])
        self._user_id = entry.data[CONF_USER_ID]
        self._base_url = entry.data[CONF_BASE_URL]
        self._attr_unique_id = (
            f"{self._site_id}_{self._user_id}_{subscription_id}_{description.key}"
        )

    @property
    def _subscription(self) -> Subscription | None:
        return self.coordinator.data.get(self._subscription_id)

    @property
    def _window(self) -> UsageWindow | None:
        subscription = self._subscription
        if subscription is None:
            return None
        return getattr(subscription, self.entity_description.window)

    @property
    def available(self) -> bool:
        window = self._window
        if not super().available or window is None:
            return False
        if self.entity_description.metric == "reset":
            return window.resets_at is not None
        return True

    @property
    def native_value(self) -> float | datetime | None:
        window = self._window
        return self.entity_description.value_fn(window) if window else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        subscription = self._subscription
        window = self._window
        if subscription is None or window is None:
            return {}

        attributes: dict[str, Any] = {
            "subscription_id": subscription.subscription_id,
            "group_id": subscription.group_id,
            "group_name": subscription.group_name,
            "platform": subscription.platform,
            "status": subscription.status,
        }
        if self.entity_description.metric == "used":
            attributes.update(
                {
                    "remaining_usd": window.remaining_usd,
                    "percentage": window.percentage,
                    "window_start": (
                        window.window_start.isoformat() if window.window_start else None
                    ),
                }
            )
        elif self.entity_description.metric == "reset":
            attributes["resets_in_seconds"] = window.resets_in_seconds
        return attributes

    @property
    def device_info(self) -> DeviceInfo:
        subscription = self._subscription
        name = (
            subscription.group_name
            if subscription
            else f"Subscription {self._subscription_id}"
        )
        model = (
            subscription.platform
            if subscription and subscription.platform
            else "Subscription"
        )
        return DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    f"{self._site_id}_{self._user_id}_{self._subscription_id}",
                )
            },
            name=name,
            manufacturer="sub2API",
            model=model,
            configuration_url=self._base_url,
        )
