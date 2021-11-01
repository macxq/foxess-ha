from __future__ import annotations

from collections import namedtuple
from datetime import timedelta
from datetime import datetime
import logging
import json
import hashlib

import voluptuous as vol

from homeassistant.components.rest.data import RestData
from homeassistant.components.sensor import (
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_POWER,
    PLATFORM_SCHEMA,
    STATE_CLASS_TOTAL_INCREASING,
    STATE_CLASS_MEASUREMENT,
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
    POWER_KILO_WATT,

)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)



from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)
_ENDPOINT_AUTH = "https://www.foxesscloud.com/c/v0/user/login"
_ENDPOINT_EARNINGS = "https://www.foxesscloud.com/c/v0/device/earnings?deviceID="
_ENDPOINT_RAW = "https://www.foxesscloud.com/c/v0/device/history/raw"
_ENDPOINT_REPORT = "https://www.foxesscloud.com/c/v0/device/history/report"

ATTR_ENERGY_GENERATION = "energy_generation"
ATTR_POWER_GENERATION = "power_generation"
CONF_DEVICEID = "deviceID"

CONF_SYSTEM_ID = "system_id"

DEFAULT_NAME = "FoxESS"
DEFAULT_VERIFY_SSL = True

SCAN_INTERVAL = timedelta(minutes=1)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_DEVICEID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the FoxESS sensor."""
    name = config.get(CONF_NAME)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    deviceID = config.get(CONF_DEVICEID)

    hashedPassword = hashlib.md5(password.encode()).hexdigest()    


    async def async_update_data():
        methodAuth = "POST"
        payloadAuth = {"user": username ,"password":hashedPassword} 
        headersAuth = {"Content-Type":"application/json;charset=UTF-8","Accept":"application/json, text/plain, */*","lang":"en"}

        restAuth = RestData(hass, methodAuth, _ENDPOINT_AUTH, None, headersAuth, None, payloadAuth, DEFAULT_VERIFY_SSL)
        await restAuth.async_update()


        if restAuth.data is None:
            _LOGGER.error("Unable to login to FoxESS Cloud - No data recived")
            return False
        
        response = json.loads(restAuth.data)
        
        if response["result"] is None or response["result"]["token"] is  None:
            _LOGGER.error("Unable to login to FoxESS Cloud: "+ restAuth.data)
            return False
        else:
            _LOGGER.debug("Login succesfull"+ restAuth.data)

        token = response["result"]["token"]
        methodData = "GET" 
        headersData = {"token":token}

        restEarnings = RestData(hass, methodData, _ENDPOINT_EARNINGS+deviceID, None, headersData, None, None, DEFAULT_VERIFY_SSL)
        await restEarnings.async_update()

        allData = {}

        if restEarnings.data is None:
            _LOGGER.error("Unable to get Earnings data from FoxESS Cloud")
            return False
        else:
            _LOGGER.debug("FoxESS Earnings data fetched correcly "+restEarnings.data)
            allData['earnings'] = json.loads(restEarnings.data)


        now = datetime.now()
        
        methodRaw = "POST" 
        rawData = '{"deviceID":"'+deviceID+'","variables":["generationPower","feedinPower","batChargePower","batDischargePower","gridConsumptionPower"],"timespan":"day","beginDate":{"year":'+now.strftime("%Y")+',"month":'+now.strftime("%_m")+',"day":'+now.strftime("%_d")+'}}'


        restRaw = RestData(hass, methodRaw, _ENDPOINT_RAW, None, headersData, None, rawData, DEFAULT_VERIFY_SSL)
        await restRaw.async_update()

        if restRaw.data is None:
            _LOGGER.error("Unable to get Raw data from FoxESS Cloud")
            return False
        else:
            _LOGGER.debug("FoxESS Raw data fetched correcly "+restRaw.data[:150] +" ... ")
            allData['raw'] = {}
            for item in json.loads(restRaw.data)['result']:
                    variableName  = item['variable']
                    lastElement =  len(item["data"]) -1
                    if lastElement > 0:
                        allData['raw'][variableName] = item["data"][lastElement]["value"]
                    else:
                        allData['raw'][variableName] =  None

        
        reportData =  '{"deviceID":"'+deviceID+'","reportType":"month","variables":["feedin","generation","gridConsumption","chargeEnergyToTal","dischargeEnergyToTal"],"queryDate":{"year":'+now.strftime("%Y")+',"month":'+now.strftime("%_m")+'}}'


        restReport= RestData(hass, methodRaw, _ENDPOINT_REPORT, None, headersData, None, reportData, DEFAULT_VERIFY_SSL)
        await restReport.async_update()

        if restReport.data is None:
            _LOGGER.error("Unable to get Report data from FoxESS Cloud")
            return False
        else:
            _LOGGER.debug("FoxESS Report data fetched correcly "+restReport.data[:150] +" ... ")
            allData['report'] = {}
            for item in json.loads(restReport.data)['result']:
                variableName  = item['variable']
                allData['report'][variableName] = None
                for dataItem in item['data']:
                    if dataItem['index'] == int(now.strftime("%d")):
                        allData['report'][variableName] = dataItem['value'] 

        
        _LOGGER.debug(allData)  
        
        return allData
        

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        # Name of the data. For logging purposes.
        name=DEFAULT_NAME,
        update_method=async_update_data,
        # Polling interval. Will only be polled if there are subscribers.
        update_interval=timedelta(seconds=60),
    )
     
    await coordinator.async_config_entry_first_refresh()

 
    async_add_entities([FoxESSPGenerationPower(coordinator, name, deviceID), FoxESSGridConsumptionPower(coordinator, name, deviceID), FoxESSFeedInPower(coordinator, name, deviceID), FoxESSBatDischargePower(coordinator, name, deviceID), FoxESSBatChargePower(coordinator, name, deviceID), FoxESSEnergyGenerated(coordinator, name, deviceID), FoxESSEnergyGridConsumption(coordinator, name, deviceID), FoxESSEnergyFeedin(coordinator, name, deviceID), FoxESSEnergyBatCharge(coordinator, name, deviceID), FoxESSEnergyBatDischarge(coordinator, name, deviceID)])


class FoxESSPGenerationPower(CoordinatorEntity,SensorEntity):
    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator,name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Generation Power")
        self._attr_name = name+" - Generation Power"
        self._attr_unique_id=deviceID+"-generation-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        return  self.coordinator.data["earnings"]["result"]["power"]

class FoxESSGridConsumptionPower(CoordinatorEntity,SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Grid Consumption Power")
        self._attr_name = name+" - Grid Consumption Power"
        self._attr_unique_id=deviceID+"grid-consumption-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        return  self.coordinator.data["raw"]["gridConsumptionPower"]

class FoxESSFeedInPower(CoordinatorEntity,SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - FeedIn Power")
        self._attr_name = name+" - FeedIn Power"
        self._attr_unique_id=deviceID+"feedIn-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        return  self.coordinator.data["raw"]["feedinPower"]   

class FoxESSBatDischargePower(CoordinatorEntity,SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Bat Discharge Power")
        self._attr_name = name+" - Bat Discharge Power"
        self._attr_unique_id=deviceID+"bat-discharge-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        return  self.coordinator.data["raw"]["batDischargePower"]   

class FoxESSBatChargePower(CoordinatorEntity,SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Bat Charge Power")
        self._attr_name = name+" - Bat Charge Power"
        self._attr_unique_id=deviceID+"bat-charge-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        return  self.coordinator.data["raw"]["batChargePower"]   


class FoxESSEnergyGenerated(CoordinatorEntity,SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Energy Generated")
        self._attr_name = name+" - Energy Generated"
        self._attr_unique_id=deviceID+"energy-generated"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        return  self.coordinator.data["earnings"]["result"]["today"]["generation"]

class FoxESSEnergyGridConsumption(CoordinatorEntity,SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Grid Consumption")
        self._attr_name = name+" - Grid Consumption"
        self._attr_unique_id=deviceID+"grid-consumption"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        return  self.coordinator.data["report"]["gridConsumption"]

class FoxESSEnergyFeedin(CoordinatorEntity,SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - FeedIn")
        self._attr_name = name+" - FeedIn"
        self._attr_unique_id=deviceID+"feedIn"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        return  self.coordinator.data["report"]["feedin"]

class FoxESSEnergyBatCharge(CoordinatorEntity,SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Bat Charge")
        self._attr_name = name+" - Bat Charge"
        self._attr_unique_id=deviceID+"bat-charge"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        return  self.coordinator.data["report"]["chargeEnergyToTal"]

class FoxESSEnergyBatDischarge(CoordinatorEntity,SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Bat Discharge")
        self._attr_name = name+" - Bat Discharge"
        self._attr_unique_id=deviceID+"bat-discharge"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        return  self.coordinator.data["report"]["dischargeEnergyToTal"]

