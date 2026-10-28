"""The Foxess cloud integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .api import FoxESSApiClient
from .const import DOMAIN, FetchResult
from .sensor import FoxDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER, Platform.SWITCH]

SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_SET_FORCE_CHARGE_TIMES = "set_force_charge_times"

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("device_sn"): cv.string,
        vol.Required("groups"): vol.All(
            cv.ensure_list,
            [vol.Schema(dict)],
        ),
        vol.Optional("enable", default=True): cv.boolean,
        vol.Optional("is_default", default=False): cv.boolean,
    }
)


def _parse_time_param(value: Any) -> dict[str, int]:
    """Parse hour and minute from string, dict, or time object."""
    if isinstance(value, dict) and "hour" in value and "minute" in value:
        return {"hour": int(value["hour"]), "minute": int(value["minute"])}
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return {"hour": int(value.hour), "minute": int(value.minute)}
    if isinstance(value, str):
        parts = value.strip().split(":")
        if len(parts) >= 2:
            return {"hour": int(parts[0]), "minute": int(parts[1])}
    return {"hour": 0, "minute": 0}


SET_FORCE_CHARGE_TIMES_SCHEMA = vol.Schema(
    {
        vol.Required("device_sn"): cv.string,
        vol.Optional("enable_1", default=True): cv.boolean,
        vol.Optional("start_time_1"): vol.Any(cv.string, cv.time, dict),
        vol.Optional("end_time_1"): vol.Any(cv.string, cv.time, dict),
        vol.Optional("enable_2", default=False): cv.boolean,
        vol.Optional("start_time_2"): vol.Any(cv.string, cv.time, dict),
        vol.Optional("end_time_2"): vol.Any(cv.string, cv.time, dict),
    }
)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register FoxESS domain services."""

    def _get_target_device_info(device_sn: str):
        domain_data = hass.data.get(DOMAIN, {})
        for entry_info in domain_data.values():
            if not isinstance(entry_info, dict):
                continue
            coord = entry_info.get("coordinator")
            coord_sn = entry_info.get("deviceSN") or getattr(coord, "devicesn", None)
            if coord_sn == device_sn:
                return (
                    coord,
                    entry_info.get("client") or FoxESSApiClient(hass),
                    entry_info.get("apiKey") or getattr(coord, "apiKey", None),
                )
        return None, None, None

    async def async_handle_set_schedule(call: ServiceCall) -> None:
        """Handle foxess.set_schedule service call."""
        device_sn: str = call.data["device_sn"]
        groups: list[dict[str, Any]] = call.data["groups"]
        enable: bool = call.data.get("enable", True)
        is_default: bool = call.data.get("is_default", False)

        target_coordinator, client, target_api_key = _get_target_device_info(device_sn)
        if not target_api_key:
            raise HomeAssistantError(f"FoxESS device with SN '{device_sn}' not found")

        res, resp, _ = await client.async_set_scheduler_groups(
            device_sn, target_api_key, groups, is_default
        )
        if res is not FetchResult.OK or not resp or resp.get("errno") != 0:
            raise HomeAssistantError(
                f"Failed to set scheduler groups for {device_sn}: {resp.get('msg') if resp else 'No response'}"
            )

        if enable:
            res_flag, resp_flag, _ = await client.async_set_scheduler_flag(
                device_sn, target_api_key, True
            )
            if res_flag is not FetchResult.OK or not resp_flag or resp_flag.get("errno") != 0:
                raise HomeAssistantError(
                    f"Failed to enable scheduler flag for {device_sn}: {resp_flag.get('msg') if resp_flag else 'No response'}"
                )
            if target_coordinator and isinstance(getattr(target_coordinator, "data", None), dict):
                target_coordinator.data["schedulerEnabled"] = True

        if target_coordinator and isinstance(getattr(target_coordinator, "data", None), dict):
            target_coordinator.data["schedulerGroups"] = groups
            await target_coordinator.async_request_refresh()

    async def async_handle_set_force_charge_times(call: ServiceCall) -> None:
        """Handle foxess.set_force_charge_times service call."""
        device_sn: str = call.data["device_sn"]
        enable_1: bool = call.data.get("enable_1", True)
        start_time_1 = _parse_time_param(call.data.get("start_time_1"))
        end_time_1 = _parse_time_param(call.data.get("end_time_1"))
        enable_2: bool = call.data.get("enable_2", False)
        start_time_2 = _parse_time_param(call.data.get("start_time_2"))
        end_time_2 = _parse_time_param(call.data.get("end_time_2"))

        target_coordinator, client, target_api_key = _get_target_device_info(device_sn)
        if not target_api_key:
            raise HomeAssistantError(f"FoxESS device with SN '{device_sn}' not found")

        res, resp, _ = await client.async_set_force_charge_times(
            device_sn,
            target_api_key,
            start_time_1=start_time_1,
            end_time_1=end_time_1,
            enable_1=enable_1,
            start_time_2=start_time_2,
            end_time_2=end_time_2,
            enable_2=enable_2,
        )
        if res is not FetchResult.OK or not resp or resp.get("errno") != 0:
            raise HomeAssistantError(
                f"Failed to set force charge times for {device_sn}: {resp.get('msg') if resp else 'No response'}"
            )

        if target_coordinator and isinstance(getattr(target_coordinator, "data", None), dict):
            target_coordinator.data["forceChargeTimes"] = {
                "enable1": 1 if enable_1 else 0,
                "enable2": 1 if enable_2 else 0,
                "startTime1": start_time_1,
                "endTime1": end_time_1,
                "startTime2": start_time_2,
                "endTime2": end_time_2,
            }
            await target_coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_SCHEDULE,
            async_handle_set_schedule,
            schema=SET_SCHEDULE_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_FORCE_CHARGE_TIMES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_FORCE_CHARGE_TIMES,
            async_handle_set_force_charge_times,
            schema=SET_FORCE_CHARGE_TIMES_SCHEMA,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up FoxESS from a config entry."""
    client = FoxESSApiClient(hass)
    config = {**entry.data, **entry.options}
    coordinator = FoxDataUpdateCoordinator(
        hass,
        config=config,
        config_entry=entry,
        client=client,
    )

    await coordinator.async_config_entry_first_refresh()

    has_battery = coordinator.data.get("addressbook", {}).get("hasBattery")
    if has_battery is not None and entry.data.get("has_battery") != has_battery:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "has_battery": has_battery}
        )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    async_setup_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            hass.data[DOMAIN].pop(entry.entry_id)
        if DOMAIN in hass.data and not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
            if hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
                hass.services.async_remove(DOMAIN, SERVICE_SET_SCHEDULE)
            if hass.services.has_service(DOMAIN, SERVICE_SET_FORCE_CHARGE_TIMES):
                hass.services.async_remove(DOMAIN, SERVICE_SET_FORCE_CHARGE_TIMES)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
