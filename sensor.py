from __future__ import annotations

from collections import namedtuple
from datetime import timedelta
from datetime import datetime
import logging
import json

import voluptuous as vol

from homeassistant.components.rest.data import RestData
from homeassistant.components.sensor import (
    DEVICE_CLASS_ENERGY,
    PLATFORM_SCHEMA,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.const import (
    ATTR_DATE,
    ATTR_TEMPERATURE,
    ATTR_TIME,
    ATTR_VOLTAGE,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_NAME,
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)
_ENDPOINT_AUTH = "https://www.foxesscloud.com/c/v0/user/login"
_ENDPOINT_DATA = "https://www.foxesscloud.com/c/v0/device/earnings?deviceID=4f1bbc87-6ebd-45d9-8931-f73275481b8e"

ATTR_ENERGY_GENERATION = "energy_generation"
ATTR_POWER_GENERATION = "power_generation"

CONF_SYSTEM_ID = "system_id"

DEFAULT_NAME = "FoxESS"
DEFAULT_VERIFY_SSL = True

SCAN_INTERVAL = timedelta(minutes=2)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the FoxESS sensor."""
    name = config.get(CONF_NAME)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    methodAuth = "POST"
    payloadAuth = {"user": username ,"password":password} 
    verify_ssl = DEFAULT_VERIFY_SSL
    headersAuth = {"Content-Type":"application/json;charset=UTF-8","Accept":"application/json, text/plain, */*","lang":"en"}

    restAuth = RestData(hass, methodAuth, _ENDPOINT_AUTH, None, headersAuth, None, payloadAuth, verify_ssl)
    await restAuth.async_update()


    if restAuth.data is None:
        _LOGGER.error("Unable to login to FoxESS Cloud ️")
        return False
    else:
        _LOGGER.debug("Login succesfull "+restAuth.data)

    token = json.loads(restAuth.data)["result"]["token"]
    methodData = "GET" 
    headersData = {"Content-Type":"application/json;charset=UTF-8","Accept":"application/json, text/plain, */*","lang":"en", "token":token}


    restData = RestData(hass, methodData, _ENDPOINT_DATA, None, headersData, None, None, verify_ssl)
    await restData.async_update()

    if restData.data is None:
        _LOGGER.error("Unable to get data from FoxESS Cloud ️")
        return False
    else:
        _LOGGER.debug("Data fetched "+restData.data)

    async_add_entities([FoxESS(restData, name)])


class FoxESS(SensorEntity):
    """Representation of a FoxESS sensor."""

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, rest, name):
        """Initialize a FoxESS sensor."""
        _LOGGER.debug("Initing Entity")
        self.rest = rest
        self._attr_name = name
        self.pvcoutput = None
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
                ATTR_ENERGY_GENERATION,
                ATTR_POWER_GENERATION,
            ],
        )

    @property
    def native_value(self):
        """Return the state of the device."""
        if self.pvcoutput is not None:
            return self.pvcoutput.energy_generation
        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the monitored installation."""
        if self.pvcoutput is not None:
            return {
                ATTR_ENERGY_GENERATION: self.pvcoutput.energy_generation,
                ATTR_POWER_GENERATION: self.pvcoutput.power_generation,
            }

    async def async_update(self):
        """Get the latest data from the PVOutput API and updates the state."""
        await self.rest.async_update()
        self._async_update_from_rest_data()

    async def async_added_to_hass(self):
        """Ensure the data from the initial update is reflected in the state."""
        self._async_update_from_rest_data()

    @callback
    def _async_update_from_rest_data(self):
        """Update state from the rest data."""

        jsonData = json.loads(self.rest.data)
        now = datetime.now()

        self.pvcoutput = self.status._make([now.strftime("%Y%m%d"),now.strftime("%H:%M"),jsonData["result"]["today"]["generation"],jsonData["result"]["power"]])
        _LOGGER.debug(self.pvcoutput)