"""Number platform for FoxESS battery SoC configuration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
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
    """Set up FoxESS number entities from a config entry."""
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
            "Inverter %s has no battery fitted, skipping Number entities",
            getattr(coordinator, "devicesn", None),
        )
        async_add_entities([])
        return

    name = getattr(coordinator, "inverter_name", None) or entry.data.get("name", "FoxESS")
    device_sn = getattr(coordinator, "devicesn", None) or entry.data.get("deviceSN")
    device_id = getattr(coordinator, "deviceID", None) or device_sn
    api_key = getattr(coordinator, "apiKey", None) or entry.data.get("apiKey")

    async_add_entities(
        [
            FoxESSBatMinSoCNumber(coordinator, name, device_id, device_sn, api_key),
            FoxESSBatMinSoCOnGridNumber(coordinator, name, device_id, device_sn, api_key),
        ]
    )


class _FoxESSBaseSoCNumber(CoordinatorEntity, NumberEntity):
    """Base class for FoxESS SoC number entities."""

    _attr_native_min_value = 10
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        coordinator: Any,
        name: str,
        device_id: str,
        device_sn: str,
        api_key: str,
    ) -> None:
        """Initialize base SoC number entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device_sn = device_sn
        self._api_key = api_key
        self._client = FoxESSApiClient(coordinator.hass if hasattr(coordinator, "hass") else None)

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


class FoxESSBatMinSoCNumber(_FoxESSBaseSoCNumber):
    """Number entity for minimum battery State of Charge (Min SoC)."""

    _attr_icon = "mdi:battery-low"

    def __init__(
        self,
        coordinator: Any,
        name: str,
        device_id: str,
        device_sn: str,
        api_key: str,
    ) -> None:
        """Initialize Min SoC entity."""
        super().__init__(coordinator, name, device_id, device_sn, api_key)
        self._attr_name = f"{name} - Min SoC"
        self._attr_unique_id = f"{device_id}_min_soc"

    @property
    def native_value(self) -> float | None:
        """Return current Min SoC value."""
        data = getattr(self.coordinator, "data", {}) or {}
        battery = data.get("battery", {}) if isinstance(data, dict) else {}
        val = battery.get("minSoc")
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set Min SoC with cross-clamping to minSocOnGrid."""
        new_min_soc = int(value)
        data = getattr(self.coordinator, "data", {}) or {}
        battery = data.get("battery", {}) if isinstance(data, dict) else {}
        current_grid = battery.get("minSocOnGrid")
        target_grid = max(new_min_soc, int(current_grid)) if current_grid is not None else new_min_soc

        res, resp, _ = await self._client.async_set_battery_soc(
            self._device_sn, self._api_key, new_min_soc, target_grid
        )
        if res is not FetchResult.OK or not resp or resp.get("errno") != 0:
            raise HomeAssistantError(
                f"Failed to set FoxESS battery SoC: {resp.get('msg') if resp else 'No response'}"
            )

        if isinstance(self.coordinator.data, dict):
            self.coordinator.data.setdefault("battery", {})
            self.coordinator.data["battery"]["minSoc"] = new_min_soc
            self.coordinator.data["battery"]["minSocOnGrid"] = target_grid
            if self.hass is not None:
                self.async_write_ha_state()

        await self.coordinator.async_request_refresh()


class FoxESSBatMinSoCOnGridNumber(_FoxESSBaseSoCNumber):
    """Number entity for minimum battery State of Charge on grid (Min SoC on Grid)."""

    _attr_icon = "mdi:battery-arrow-up"

    def __init__(
        self,
        coordinator: Any,
        name: str,
        device_id: str,
        device_sn: str,
        api_key: str,
    ) -> None:
        """Initialize Min SoC on Grid entity."""
        super().__init__(coordinator, name, device_id, device_sn, api_key)
        self._attr_name = f"{name} - Min SoC on Grid"
        self._attr_unique_id = f"{device_id}_min_soc_on_grid"

    @property
    def native_value(self) -> float | None:
        """Return current Min SoC on Grid value."""
        data = getattr(self.coordinator, "data", {}) or {}
        battery = data.get("battery", {}) if isinstance(data, dict) else {}
        val = battery.get("minSocOnGrid")
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set Min SoC on Grid with cross-clamping to minSoc."""
        new_grid_soc = int(value)
        data = getattr(self.coordinator, "data", {}) or {}
        battery = data.get("battery", {}) if isinstance(data, dict) else {}
        current_min = battery.get("minSoc")
        target_min = min(new_grid_soc, int(current_min)) if current_min is not None else new_grid_soc

        res, resp, _ = await self._client.async_set_battery_soc(
            self._device_sn, self._api_key, target_min, new_grid_soc
        )
        if res is not FetchResult.OK or not resp or resp.get("errno") != 0:
            raise HomeAssistantError(
                f"Failed to set FoxESS battery SoC: {resp.get('msg') if resp else 'No response'}"
            )

        if isinstance(self.coordinator.data, dict):
            self.coordinator.data.setdefault("battery", {})
            self.coordinator.data["battery"]["minSoc"] = target_min
            self.coordinator.data["battery"]["minSocOnGrid"] = new_grid_soc
            if self.hass is not None:
                self.async_write_ha_state()

        await self.coordinator.async_request_refresh()
