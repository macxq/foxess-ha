"""Switch platform for FoxESS Mode Scheduler toggle."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import FoxESSApiClient
from .const import (
    ATTR_DEVICE_TYPE,
    ATTR_MASTER,
    DOMAIN,
    FetchResult,
    _ENDPOINT_OA_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up FoxESS switch entities from a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")
    if not coordinator:
        _LOGGER.error("Coordinator not found for entry %s", entry.entry_id)
        return

    has_battery = entry.data.get("has_battery")
    if has_battery is None:
        has_battery = coordinator.data.get("addressbook", {}).get("hasBattery", False)

    if not has_battery:
        _LOGGER.debug(
            "Inverter %s has no battery fitted, skipping Switch entities",
            getattr(coordinator, "devicesn", None),
        )
        async_add_entities([])
        return

    name = getattr(coordinator, "inverter_name", None) or entry.data.get("name", "FoxESS")
    device_sn = getattr(coordinator, "devicesn", None) or entry.data.get("deviceSN")
    device_id = getattr(coordinator, "deviceID", None) or device_sn
    api_key = getattr(coordinator, "apiKey", None) or entry.data.get("apiKey")

    async_add_entities(
        [FoxESSSchedulerSwitch(coordinator, name, device_id, device_sn, api_key)]
    )


class FoxESSSchedulerSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity for enabling or disabling the FoxESS mode scheduler."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: Any,
        name: str,
        device_id: str,
        device_sn: str,
        api_key: str,
    ) -> None:
        """Initialize the Mode Scheduler switch entity."""
        super().__init__(coordinator)
        self._attr_name = f"{name} - Mode Scheduler"
        self._attr_unique_id = f"{device_id}_mode_scheduler"
        self._device_id = device_id
        self._device_sn = device_sn
        self._api_key = api_key
        self._client = FoxESSApiClient(coordinator.hass if hasattr(coordinator, "hass") else None)

    @property
    def is_on(self) -> bool:
        """Return True if mode scheduler is enabled."""
        data = getattr(self.coordinator, "data", {}) or {}
        return bool(data.get("schedulerEnabled", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return scheduler groups as entity attributes."""
        data = getattr(self.coordinator, "data", {}) or {}
        return {
            "scheduler_groups": data.get("schedulerGroups", []),
        }

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information."""
        devicesn = self._device_sn or getattr(self.coordinator, "devicesn", None)
        if not devicesn:
            return None
        inverter_name = getattr(self.coordinator, "inverter_name", None) or devicesn
        data = getattr(self.coordinator, "data", {}) or {}
        addressbook = data.get("addressbook", {}) if isinstance(data, dict) else {}
        return DeviceInfo(
            identifiers={(DOMAIN, devicesn)},
            name=inverter_name,
            manufacturer="FoxESS",
            model=addressbook.get(ATTR_DEVICE_TYPE),
            sw_version=addressbook.get(ATTR_MASTER),
            serial_number=devicesn,
            configuration_url=_ENDPOINT_OA_DOMAIN,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the mode scheduler."""
        res, resp, _ = await self._client.async_set_scheduler_flag(
            self._device_sn, self._api_key, True
        )
        if res is not FetchResult.OK or not resp or resp.get("errno") != 0:
            raise HomeAssistantError(
                f"Failed to enable FoxESS mode scheduler: {resp.get('msg') if resp else 'No response'}"
            )

        if isinstance(self.coordinator.data, dict):
            self.coordinator.data["schedulerEnabled"] = True
            if self.hass is not None:
                self.async_write_ha_state()

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the mode scheduler."""
        res, resp, _ = await self._client.async_set_scheduler_flag(
            self._device_sn, self._api_key, False
        )
        if res is not FetchResult.OK or not resp or resp.get("errno") != 0:
            raise HomeAssistantError(
                f"Failed to disable FoxESS mode scheduler: {resp.get('msg') if resp else 'No response'}"
            )

        if isinstance(self.coordinator.data, dict):
            self.coordinator.data["schedulerEnabled"] = False
            if self.hass is not None:
                self.async_write_ha_state()

        await self.coordinator.async_request_refresh()
