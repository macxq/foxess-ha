"""Config flow for FoxESS integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from aiohttp import ClientError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .sensor import (
    _ENDPOINT_OA_DOMAIN,
    CONF_APIKEY,
    CONF_DEVICEID,
    CONF_DEVICESN,
    CONF_EXTPV,
    DEFAULT_NAME,
    YAML_CONFIGS_KEY,
    GetAuth,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "foxess"

_DEVICE_LIST_PATH = "/op/v0/device/list"
_DEVICE_LIST_ENDPOINT = _ENDPOINT_OA_DOMAIN + _DEVICE_LIST_PATH


async def _fetch_device_list(hass, api_key: str) -> tuple[list[dict], str | None]:
    """Fetch the device list from FoxESS Cloud.

    Returns (devices, error_key). On success error_key is None and devices
    contains the list of device dicts from the API (deviceSN, deviceType, etc.).
    """
    headers = GetAuth().get_signature(token=api_key, path=_DEVICE_LIST_PATH)
    session = async_get_clientsession(hass, verify_ssl=False)
    try:
        # This assumes that the user has a maximum of 25 inverters.
        resp = await session.post(
            _DEVICE_LIST_ENDPOINT,
            headers=headers,
            json={"currentPage": 1, "pageSize": 25},
            timeout=30,
        )
        if resp.status == 401:
            _LOGGER.warning("FoxESS API rejected credentials (HTTP 401)")
            return [], "invalid_auth"
        data = await resp.json(content_type=None)
    except ClientError:
        _LOGGER.exception("Connection error fetching FoxESS device list")
        return [], "cannot_connect"

    if not isinstance(data, dict):
        _LOGGER.error("Unexpected response body from FoxESS device list API: %r", data)
        return [], "cannot_connect"

    errno = data.get("errno", -1)
    if errno != 0:
        _LOGGER.error("Unexpected errno from FoxESS device list API: %s", errno)
        return [], "cannot_connect"

    devices: list[dict] = data.get("result", {}).get("data", [])
    if not devices:
        return [], "no_devices"

    return devices, None



class FoxESSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FoxESS."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._api_key: str | None = None
        self._devices: list[dict] | None = None

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle the initial step — collect API key and discover devices."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_APIKEY]
            devices, error = await _fetch_device_list(self.hass, api_key)
            if error:
                errors["base"] = error
            else:
                self._api_key = api_key
                self._devices = devices
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_APIKEY): str}),
                user_input or {},
            ),
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle device selection."""
        assert self._api_key is not None
        assert self._devices is not None

        errors: dict[str, str] = {}

        if user_input is not None:
            device_sn = user_input[CONF_DEVICESN]
            name = user_input.get(CONF_NAME, DEFAULT_NAME)

            current_entries = self._async_current_entries()
            yaml_configs = self.hass.data.get(YAML_CONFIGS_KEY, {})

            if device_sn in yaml_configs:
                errors[CONF_DEVICESN] = "yaml_device_already_configured"
            elif any(e.unique_id == device_sn for e in current_entries):
                errors[CONF_DEVICESN] = "already_configured"

            if any(cfg.get(CONF_NAME) == name for cfg in yaml_configs.values()):
                errors[CONF_NAME] = "yaml_name_already_in_use"
            elif any(e.data.get(CONF_NAME) == name for e in current_entries):
                errors[CONF_NAME] = "name_already_in_use"

            if not errors:
                await self.async_set_unique_id(device_sn)
                return self.async_create_entry(
                    title=device_sn,
                    data={
                        CONF_APIKEY: self._api_key,
                        CONF_DEVICESN: device_sn,
                        CONF_DEVICEID: device_sn,
                        CONF_NAME: name,
                        CONF_EXTPV: user_input.get(CONF_EXTPV, False),
                    },
                )

        options = [
            SelectOptionDict(
                value=d["deviceSN"],
                label=(f"{d['deviceSN']} ({d.get('deviceType', '?')})"),
            )
            for d in self._devices
        ]

        return self.async_show_form(
            step_id="device",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_DEVICESN): SelectSelector(
                            SelectSelectorConfig(
                                options=options,
                                mode=SelectSelectorMode.DROPDOWN,
                            )
                        ),
                        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                        vol.Optional(CONF_EXTPV, default=False): bool,
                    }
                ),
                user_input or {},
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, _entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Triggered automatically by HA when ConfigEntryAuthFailed is raised."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Show a form asking only for the new API key."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            _, error = await _fetch_device_list(self.hass, user_input[CONF_APIKEY])
            if error in (None, "no_devices"):
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_APIKEY: user_input[CONF_APIKEY]},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_APIKEY): str}),
            description_placeholders={"device_sn": reauth_entry.data[CONF_DEVICESN]},
            errors=errors,
        )
