"""Config flow for FoxESS integration."""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import logging
import time
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

_LOGGER = logging.getLogger(__name__)

DOMAIN = "foxess"

CONF_API_KEY = "apiKey"
CONF_DEVICE_SN = "deviceSN"
CONF_DEVICE_ID = "deviceID"
CONF_EXTPV = "extendPV"
DEFAULT_NAME = "FoxESS"

_DEVICE_LIST_ENDPOINT = "https://www.foxesscloud.com/op/v0/device/list"
_DEVICE_LIST_PATH = "/op/v0/device/list"


def _build_headers(api_key: str, path: str) -> dict:
    timestamp = round(time.time() * 1000)
    signature_text = rf"{path}\r\n{api_key}\r\n{timestamp}"
    signature = hashlib.md5(signature_text.encode("UTF-8")).hexdigest()
    return {
        "token": api_key,
        "lang": "en",
        "timestamp": str(timestamp),
        "Content-Type": "application/json",
        "signature": signature,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Connection": "close",
    }


async def _fetch_device_list(
    hass, api_key: str
) -> tuple[list[dict], str | None]:
    """Fetch the device list from FoxESS Cloud.

    Returns (devices, error_key). On success error_key is None and devices
    contains the list of device dicts from the API (deviceSN, deviceType, etc.).
    """
    headers = _build_headers(api_key, _DEVICE_LIST_PATH)
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

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — collect API key and discover devices."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            devices, error = await _fetch_device_list(self.hass, api_key)
            if error:
                errors["base"] = error
            else:
                self._api_key = api_key
                self._devices = devices
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
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
            device_sn = user_input[CONF_DEVICE_SN]
            name = user_input.get(CONF_NAME, DEFAULT_NAME)
            await self.async_set_unique_id(device_sn)
            self._abort_if_unique_id_configured()
            existing_names = {
                entry.data.get(CONF_NAME)
                for entry in self.hass.config_entries.async_entries(DOMAIN)
            }
            if name in existing_names:
                errors[CONF_NAME] = "name_already_in_use"
            else:
                return self.async_create_entry(
                    title=device_sn,
                    data={
                        CONF_API_KEY: self._api_key,
                        CONF_DEVICE_SN: device_sn,
                        CONF_DEVICE_ID: device_sn,
                        CONF_NAME: name,
                        CONF_EXTPV: user_input.get(CONF_EXTPV, False),
                    },
                )

        options = [
            SelectOptionDict(
                value=d["deviceSN"],
                label=(
                    f"{d['deviceSN']} ({d.get('deviceType', '?')})"
                ),
            )
            for d in self._devices
        ]

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_SN): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Optional(CONF_EXTPV, default=False): bool,
                }
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
            _, error = await _fetch_device_list(self.hass, user_input[CONF_API_KEY])
            if error in (None, "no_devices"):
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_API_KEY: user_input[CONF_API_KEY]},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            description_placeholders={"device_sn": reauth_entry.data[CONF_DEVICE_SN]},
            errors=errors,
        )
