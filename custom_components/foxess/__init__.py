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


def async_setup_services(hass: HomeAssistant) -> None:
    """Register FoxESS domain services."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        return

    async def async_handle_set_schedule(call: ServiceCall) -> None:
        """Handle foxess.set_schedule service call."""
        device_sn: str = call.data["device_sn"]
        groups: list[dict[str, Any]] = call.data["groups"]
        enable: bool = call.data.get("enable", True)
        is_default: bool = call.data.get("is_default", False)

        target_coordinator: Any = None
        target_client: Any = None
        target_api_key: str | None = None

        domain_data = hass.data.get(DOMAIN, {})
        for entry_info in domain_data.values():
            if not isinstance(entry_info, dict):
                continue
            coord = entry_info.get("coordinator")
            coord_sn = entry_info.get("deviceSN") or getattr(coord, "devicesn", None)
            if coord_sn == device_sn:
                target_coordinator = coord
                target_client = entry_info.get("client")
                target_api_key = entry_info.get("apiKey") or getattr(coord, "apiKey", None)
                break

        if not target_api_key:
            raise HomeAssistantError(f"FoxESS device with SN '{device_sn}' not found")

        client = target_client or FoxESSApiClient(hass)

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

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        async_handle_set_schedule,
        schema=SET_SCHEDULE_SCHEMA,
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
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
