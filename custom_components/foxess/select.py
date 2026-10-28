"""Select entity platform for FoxESS Work Mode control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
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

WORK_MODES = ["Self-Use", "Feed-in", "Backup", "Peak Shaving"]
READ_ONLY_WORK_MODES = ["ForceCharge", "ForceDischarge"]

OPTIONS_TO_API = {
    "Self-Use": "SelfUse",
    "Feed-in": "Feedin",
    "Backup": "Backup",
    "Peak Shaving": "PeakShaving",
}

API_TO_OPTIONS = {v: k for k, v in OPTIONS_TO_API.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up FoxESS select entities from a config entry."""
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
            "Inverter %s has no battery fitted, skipping Work Mode select",
            getattr(coordinator, "devicesn", None),
        )
        async_add_entities([])
        return

    name = getattr(coordinator, "inverter_name", None) or entry.data.get("name", "FoxESS")
    device_sn = getattr(coordinator, "devicesn", None) or entry.data.get("deviceSN")
    device_id = getattr(coordinator, "deviceID", None) or device_sn
    api_key = getattr(coordinator, "apiKey", None) or entry.data.get("apiKey")

    async_add_entities(
        [FoxESSWorkModeSelect(coordinator, name, device_id, device_sn, api_key)]
    )


class FoxESSWorkModeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for changing inverter work mode."""

    _attr_icon = "mdi:battery-sync"

    def __init__(
        self,
        coordinator: Any,
        name: str,
        device_id: str,
        device_sn: str,
        api_key: str,
    ) -> None:
        """Initialize the Work Mode select entity."""
        super().__init__(coordinator)
        self._attr_name = f"{name} - Work Mode"
        self._attr_unique_id = f"{device_id}_work_mode"
        self._device_id = device_id
        self._device_sn = device_sn
        self._api_key = api_key
        self._client = FoxESSApiClient(coordinator.hass if hasattr(coordinator, "hass") else None)

    @property
    def options(self) -> list[str]:
        """Return available work mode options."""
        return list(WORK_MODES)

    @property
    def current_option(self) -> str | None:
        """Return the current work mode."""
        data = getattr(self.coordinator, "data", {}) or {}
        raw_mode = data.get("workMode")
        if raw_mode in API_TO_OPTIONS:
            return API_TO_OPTIONS[raw_mode]
        if raw_mode in READ_ONLY_WORK_MODES:
            return raw_mode
        return None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information to group entity under inverter device."""
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

    async def async_select_option(self, option: str) -> None:
        """Change the selected work mode."""
        data = getattr(self.coordinator, "data", {}) or {}
        if data.get("schedulerEnabled"):
            raise HomeAssistantError(
                "Cannot change work mode while the Mode Scheduler is enabled. "
                "Turn off the Mode Scheduler switch first."
            )

        api_mode = OPTIONS_TO_API.get(option)
        if not api_mode:
            raise HomeAssistantError(f"Invalid work mode: {option}")

        res, resp, _ = await self._client.async_set_work_mode(
            self._device_sn, self._api_key, api_mode
        )
        if res is not FetchResult.OK or not resp or resp.get("errno") != 0:
            raise HomeAssistantError(
                f"Failed to set FoxESS work mode to '{option}': {resp.get('msg') if resp else 'No response'}"
            )

        if isinstance(self.coordinator.data, dict):
            self.coordinator.data["workMode"] = api_mode
            if self.hass is not None:
                self.async_write_ha_state()

        await self.coordinator.async_request_refresh()
