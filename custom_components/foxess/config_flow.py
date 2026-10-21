"""Config flow for FoxESS integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from aiohttp import ClientError
import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME, UnitOfEnergy
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    ConstantSelector,
    ConstantSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .sensor import (
    _AUTH_ERRNO,
    _ENDPOINT_OA_DOMAIN,
    CONF_APIKEY,
    CONF_DEVICEID,
    CONF_DEVICESN,
    CONF_ENERGY_GENERATED_SANITY,
    CONF_EVO,
    CONF_EXTPV,
    CONF_GET_VARIABLES,
    CONF_REDUCE_API_CALLS,
    CONF_V1_API,
    CONF_XTZONE,
    DEFAULT_ENERGY_GENERATED_SANITY,
    DEFAULT_NAME,
    DEFAULT_REDUCE_API_CALLS,
    YAML_CONFIGS_KEY,
    GetAuth,
    waitforAPI,
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
        # Rate limit guard: FoxESS OpenAPI enforces 1 request/second across account
        await waitforAPI()
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
        if errno in _AUTH_ERRNO:
            _LOGGER.warning("FoxESS API rejected credentials with errno: %s", errno)
            return [], "invalid_auth"
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

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle automatic import from YAML configuration."""
        device_sn = import_data[CONF_DEVICESN]
        await self.async_set_unique_id(device_sn)
        self._abort_if_unique_id_configured()

        persistent_notification.async_create(
            self.hass,
            f"FoxESS configuration for device {device_sn} was imported into Home Assistant from configuration.yaml.\n\n"
            "You can safely remove the `foxess` platform entry from your configuration.yaml.",
            title="FoxESS Configuration Imported",
            notification_id=f"foxess_import_{device_sn}",
        )

        return self.async_create_entry(
            title=f"{import_data.get(CONF_NAME, DEFAULT_NAME)} ({device_sn})",
            data={
                CONF_APIKEY: import_data[CONF_APIKEY],
                CONF_DEVICESN: device_sn,
                CONF_DEVICEID: import_data.get(CONF_DEVICEID, device_sn),
                CONF_NAME: import_data.get(CONF_NAME, DEFAULT_NAME),
                CONF_EXTPV: import_data.get(CONF_EXTPV, False),
                CONF_EVO: import_data.get(CONF_EVO, False),
                CONF_XTZONE: import_data.get(CONF_XTZONE, False),
                CONF_GET_VARIABLES: import_data.get(CONF_GET_VARIABLES, False),
                CONF_V1_API: import_data.get(CONF_V1_API, True),
                CONF_ENERGY_GENERATED_SANITY: import_data.get(
                    CONF_ENERGY_GENERATED_SANITY, DEFAULT_ENERGY_GENERATED_SANITY
                ),
                CONF_REDUCE_API_CALLS: import_data.get(
                    CONF_REDUCE_API_CALLS, DEFAULT_REDUCE_API_CALLS
                ),
            },
        )

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
                vol.Schema(
                    {
                        vol.Required(CONF_APIKEY): TextSelector(
                            TextSelectorConfig(type=TextSelectorType.PASSWORD)
                        )
                    }
                ),
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
                    title=f"{name} ({device_sn})",
                    data={
                        CONF_APIKEY: self._api_key,
                        CONF_DEVICESN: device_sn,
                        CONF_DEVICEID: device_sn,
                        CONF_NAME: name,
                        CONF_EXTPV: user_input.get(CONF_EXTPV, False),
                        CONF_ENERGY_GENERATED_SANITY: DEFAULT_ENERGY_GENERATED_SANITY,
                        CONF_REDUCE_API_CALLS: user_input.get(
                            CONF_REDUCE_API_CALLS, DEFAULT_REDUCE_API_CALLS
                        ),
                    },
                )

        options = [
            SelectOptionDict(
                value=d["deviceSN"],
                label=(f"{d['deviceSN']} ({d.get('deviceType', '?')})"),
            )
            for d in self._devices
        ]

        suggested_values = dict(user_input or {})
        if CONF_DEVICESN not in suggested_values and self._devices and len(self._devices) == 1:
            suggested_values[CONF_DEVICESN] = self._devices[0]["deviceSN"]

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
                        vol.Optional(
                            CONF_REDUCE_API_CALLS, default=DEFAULT_REDUCE_API_CALLS
                        ): bool,
                    }
                ),
                suggested_values,
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
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APIKEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"device_sn": reauth_entry.data[CONF_DEVICESN]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FoxESSOptionsFlowHandler:
        """Get the options flow for this handler."""
        return FoxESSOptionsFlowHandler()


class FoxESSOptionsFlowHandler(OptionsFlow):
    """Handle options flow for FoxESS."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage FoxESS options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input_copy = dict(user_input)
            user_input_copy.pop(CONF_DEVICESN, None)
            new_api_key = user_input_copy.get(CONF_APIKEY)
            current_api_key = self.config_entry.options.get(
                CONF_APIKEY, self.config_entry.data.get(CONF_APIKEY)
            )
            if new_api_key and new_api_key != current_api_key:
                _, error = await _fetch_device_list(self.hass, new_api_key)
                if error in ("invalid_auth", "cannot_connect"):
                    errors["base"] = error

            if not errors:
                return self.async_create_entry(title="", data=user_input_copy)

        current_options = self.config_entry.options
        current_data = self.config_entry.data
        device_sn = current_data.get(CONF_DEVICESN, "")
        name = current_data.get(CONF_NAME, DEFAULT_NAME)
        sanity_check = float(
            current_options.get(
                CONF_ENERGY_GENERATED_SANITY,
                current_data.get(
                    CONF_ENERGY_GENERATED_SANITY, DEFAULT_ENERGY_GENERATED_SANITY
                ),
            )
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DEVICESN,
                        default=device_sn,
                    ): ConstantSelector(
                        ConstantSelectorConfig(
                            value=device_sn,
                            label=f"{name} ({device_sn})",
                        )
                    ),
                    vol.Required(
                        CONF_APIKEY,
                        default=current_options.get(
                            CONF_APIKEY, current_data.get(CONF_APIKEY, "")
                        ),
                    ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                    vol.Optional(
                        CONF_ENERGY_GENERATED_SANITY,
                        default=sanity_check,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                        )
                    ),
                    vol.Optional(
                        CONF_REDUCE_API_CALLS,
                        default=current_options.get(
                            CONF_REDUCE_API_CALLS,
                            current_data.get(
                                CONF_REDUCE_API_CALLS, DEFAULT_REDUCE_API_CALLS
                            ),
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_EXTPV,
                        default=current_options.get(
                            CONF_EXTPV, current_data.get(CONF_EXTPV, False)
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_EVO,
                        default=current_options.get(
                            CONF_EVO, current_data.get(CONF_EVO, False)
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_XTZONE,
                        default=current_options.get(
                            CONF_XTZONE, current_data.get(CONF_XTZONE, False)
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_GET_VARIABLES,
                        default=current_options.get(
                            CONF_GET_VARIABLES, current_data.get(CONF_GET_VARIABLES, False)
                        ),
                    ): bool,
                }
            ),
            description_placeholders={"device_sn": device_sn, "name": name},
            errors=errors,
        )
