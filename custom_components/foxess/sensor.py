from __future__ import annotations

from collections import namedtuple
from datetime import timedelta
from datetime import datetime
import logging
import json
import hashlib

import voluptuous as vol

from homeassistant.components.rest.data import RestData
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
    PLATFORM_SCHEMA,
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
    UnitOfEnergy,
    POWER_KILO_WATT,
    ENERGY_KILO_WATT_HOUR,
    TEMP_CELSIUS,
    UnitOfEnergy,
    ELECTRIC_POTENTIAL_VOLT,
    ELECTRIC_CURRENT_AMPERE,
    FREQUENCY_HERTZ,
    POWER_VOLT_AMPERE_REACTIVE,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util.ssl import SSLCipherList

from homeassistant.helpers.icon import icon_for_battery_level
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from random_user_agent.user_agent import UserAgent
from random_user_agent.params import SoftwareName, OperatingSystem

software_names = [SoftwareName.CHROME.value]
operating_systems = [OperatingSystem.WINDOWS.value, OperatingSystem.LINUX.value]
user_agent_rotator = UserAgent(software_names=software_names, operating_systems=operating_systems, limit=100)

_LOGGER = logging.getLogger(__name__)
_ENDPOINT_AUTH = "https://www.foxesscloud.com/c/v0/user/login"
_ENDPOINT_RAW = "https://www.foxesscloud.com/c/v0/device/history/raw"
_ENDPOINT_REPORT = "https://www.foxesscloud.com/c/v0/device/history/report"
_ENDPOINT_ADDRESSBOOK = "https://www.foxesscloud.com/c/v0/device/addressbook?deviceID="

METHOD_POST = "POST"
METHOD_GET = "GET"
DEFAULT_ENCODING = "UTF-8"


ATTR_DEVICE_SN = "deviceSN"
ATTR_PLANTNAME = "plantName"
ATTR_MODULESN = "moduleSN"
ATTR_DEVICE_TYPE = "deviceType"
ATTR_STATUS = "status"
ATTR_COUNTRY = "country"
ATTR_COUNTRYCODE = "countryCode"
ATTR_CITY = "city"
ATTR_ADDRESS = "address"
ATTR_FEEDINDATE = "feedinDate"
ATTR_LASTCLOUDSYNC = "lastCloudSync"

BATTERY_LEVELS = {"High": 80, "Medium": 50, "Low": 25, "Empty": 10}

CONF_DEVICEID = "deviceID"

CONF_SYSTEM_ID = "system_id"

DEFAULT_NAME = "FoxESS"
DEFAULT_VERIFY_SSL = True

SCAN_INTERVAL = timedelta(minutes=3)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_DEVICEID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)

token = None

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the FoxESS sensor."""
    name = config.get(CONF_NAME)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    deviceID = config.get(CONF_DEVICEID)

    hashedPassword = hashlib.md5(password.encode()).hexdigest()

    async def async_update_data():
        _LOGGER.debug("Updating data from https://www.foxesscloud.com/")

        allData = {
            "report":{},
            "reportDailyGeneration": {},
            "raw":{},
            "online":False
        }

        global token
        if token is None:
            _LOGGER.debug("Token is empty, authenticating for the firts time")
            token = await authAndgetToken(hass, username, hashedPassword)

        user_agent = user_agent_rotator.get_random_user_agent()
        headersData = {"token": token,
                       "User-Agent": user_agent,
                       "Accept": "application/json, text/plain, */*",
                       "lang": "en",
                       "sec-ch-ua-platform": "macOS",
                       "Sec-Fetch-Site": "same-origin",
                       "Sec-Fetch-Mode": "cors",
                       "Sec-Fetch-Dest": "empty",
                       "Referer": "https://www.foxesscloud.com/bus/device/inverterDetail?id=xyz&flowType=1&status=1&hasPV=true&hasBattery=false",
                       "Accept-Language":"en-US;q=0.9,en;q=0.8,de;q=0.7,nl;q=0.6",
                       "Connection": "keep-alive",
                       "X-Requested-With": "XMLHttpRequest"}

        await getAddresbook(hass, headersData, allData, deviceID, username, hashedPassword,0)


        if int(allData["addressbook"]["result"]["status"]) == 1 or int(allData["addressbook"]["result"]["status"]) == 2 or int(allData["addressbook"]["result"]["status"]) == 3:
            allData["online"] = True
            await getRaw(hass, headersData, allData, deviceID)
            await getReport(hass, headersData, allData, deviceID)
            await getReportDailyGeneration(hass, headersData, allData, deviceID)
        else:
            _LOGGER.debug("Inverter is off-line, not fetching addictional data")

        _LOGGER.debug(allData)

        return allData

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        # Name of the data. For logging purposes.
        name=DEFAULT_NAME,
        update_method=async_update_data,
        # Polling interval. Will only be polled if there are subscribers.
        update_interval=SCAN_INTERVAL,
    )

    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        _LOGGER.error(
            "FoxESS Cloud initializaction failed, fix error and restar ha")
        return False

    async_add_entities([
        FoxESSPV1Current(coordinator, name, deviceID),
        FoxESSPV1Power(coordinator, name, deviceID),
        FoxESSPV1Volt(coordinator, name, deviceID),
        FoxESSPV2Current(coordinator, name, deviceID),
        FoxESSPV2Power(coordinator, name, deviceID),
        FoxESSPV2Volt(coordinator, name, deviceID),
        FoxESSPV3Current(coordinator, name, deviceID),
        FoxESSPV3Power(coordinator, name, deviceID),
        FoxESSPV3Volt(coordinator, name, deviceID),
        FoxESSPV4Current(coordinator, name, deviceID),
        FoxESSPV4Power(coordinator, name, deviceID),
        FoxESSPV4Volt(coordinator, name, deviceID),
        FoxESSPVPower(coordinator, name, deviceID),
        FoxESSRCurrent(coordinator, name, deviceID),
        FoxESSRFreq(coordinator, name, deviceID),
        FoxESSRPower(coordinator, name, deviceID),
        FoxESSMeter2Power(coordinator, name, deviceID),
        FoxESSRVolt(coordinator, name, deviceID),
        FoxESSSCurrent(coordinator, name, deviceID),
        FoxESSSFreq(coordinator, name, deviceID),
        FoxESSSPower(coordinator, name, deviceID),
        FoxESSSVolt(coordinator, name, deviceID),
        FoxESSTCurrent(coordinator, name, deviceID),
        FoxESSTFreq(coordinator, name, deviceID),
        FoxESSTPower(coordinator, name, deviceID),
        FoxESSTVolt(coordinator, name, deviceID),
        FoxESSReactivePower(coordinator, name, deviceID),
        FoxESSBatTemp(coordinator, name, deviceID),
        FoxESSAmbientTemp(coordinator, name, deviceID),
        FoxESSBoostTemp(coordinator, name, deviceID),
        FoxESSInvTemp(coordinator, name, deviceID),
        FoxESSBatSoC(coordinator, name, deviceID),
        FoxESSSolarPower(coordinator, name, deviceID),
        FoxESSEnergySolar(coordinator, name, deviceID),
        FoxESSInverter(coordinator, name, deviceID),
        FoxESSGenerationPower(coordinator, name, deviceID),
        FoxESSGridConsumptionPower(coordinator, name, deviceID),
        FoxESSFeedInPower(coordinator, name, deviceID),
        FoxESSBatDischargePower(coordinator, name, deviceID),
        FoxESSBatChargePower(coordinator, name, deviceID),
        FoxESSLoadPower(coordinator, name, deviceID),
        FoxESSEnergyGenerated(coordinator, name, deviceID),
        FoxESSEnergyGridConsumption(coordinator, name, deviceID),
        FoxESSEnergyFeedin(coordinator, name, deviceID),
        FoxESSEnergyBatCharge(coordinator, name, deviceID),
        FoxESSEnergyBatDischarge(coordinator, name, deviceID),
        FoxESSEnergyLoad(coordinator, name, deviceID)
    ])


async def authAndgetToken(hass, username, hashedPassword):

    #https://github.com/macxq/foxess-ha/issues/93#issuecomment-1319326849
#    payloadAuth = {"user": username, "password": hashedPassword}
    payloadAuth = f'user={username}&password={hashedPassword}'
    user_agent = user_agent_rotator.get_random_user_agent()
    headersAuth = {"User-Agent": user_agent,
                   "Accept": "application/json, text/plain, */*",
                   "lang": "en",
                   "sec-ch-ua-platform": "macOS",
                   "Sec-Fetch-Site": "same-origin",
                   "Sec-Fetch-Mode": "cors",
                   "Sec-Fetch-Dest": "empty",
                   "Referer": "https://www.foxesscloud.com/bus/device/inverterDetail?id=xyz&flowType=1&status=1&hasPV=true&hasBattery=false",
                   "Accept-Language":"en-US;q=0.9,en;q=0.8,de;q=0.7,nl;q=0.6",
                   "Connection": "keep-alive",
                    "X-Requested-With": "XMLHttpRequest"}

    restAuth = RestData(hass, METHOD_POST, _ENDPOINT_AUTH, DEFAULT_ENCODING,  None,
                        headersAuth, None, payloadAuth, DEFAULT_VERIFY_SSL, SSLCipherList.PYTHON_DEFAULT)

    await restAuth.async_update()

    if restAuth.data is None:
        _LOGGER.error("Unable to login to FoxESS Cloud - No data recived")
        return False

    response = json.loads(restAuth.data)

    if response["result"] is None:
        if response["errno"] is not None and response["errno"] == 41807:
            raise UpdateFailed(
                f"Unable to login to FoxESS Cloud - bad username or password! {restAuth.data}")
        else:
            raise UpdateFailed(
                f"Error communicating with API: {restAuth.data}")
    else:
        _LOGGER.debug("Login succesfull" + restAuth.data)

    token = response["result"]["token"]
    return token


async def getAddresbook(hass, headersData, allData, deviceID,username, hashedPassword,tokenRefreshRetrys):
    restAddressBook = RestData(hass, METHOD_GET, _ENDPOINT_ADDRESSBOOK +
                               deviceID, DEFAULT_ENCODING,  None, headersData, None, None, DEFAULT_VERIFY_SSL, SSLCipherList.PYTHON_DEFAULT)
    await restAddressBook.async_update()

    if restAddressBook.data is None:
        _LOGGER.error("Unable to get Addressbook data from FoxESS Cloud")
        return False
    else:
        response = json.loads(restAddressBook.data)
        if response["errno"] is not None and (response["errno"] == 41809 or response["errno"] == 41808):
                global token
                _LOGGER.debug(f"Token has expired, re-authenticating {tokenRefreshRetrys}")
                token = None
        else:
            _LOGGER.debug(
                "FoxESS Addressbook data fetched correctly "+restAddressBook.data)
            allData['addressbook'] = response

async def getReport(hass, headersData, allData, deviceID):
    now = datetime.now()


    reportData = '{"deviceID":"'+deviceID+'","reportType":"day","variables":["feedin","generation","gridConsumption","chargeEnergyToTal","dischargeEnergyToTal","loads"],"queryDate":{"year":'+now.strftime(
        "%Y")+',"month":'+now.strftime("%_m")+',"day":'+now.strftime("%_d")+'}}'

    restReport = RestData(hass, METHOD_POST, _ENDPOINT_REPORT,DEFAULT_ENCODING,
                          None, headersData, None, reportData, DEFAULT_VERIFY_SSL, SSLCipherList.PYTHON_DEFAULT)

    await restReport.async_update()

    if restReport.data is None:
        _LOGGER.error("Unable to get Report data from FoxESS Cloud")
        return False
    else:
        _LOGGER.debug("FoxESS Report data fetched correctly " +
                      restReport.data[:150] + " ... ")

        for item in json.loads(restReport.data)['result']:
            variableName = item['variable']
            allData['report'][variableName] = None
            # Daily reports break down the data hour by hour for the whole day
            # even if we're only partially through, so sum the values together
            # to get our daily total so far...
            cumulative_total = 0
            for dataItem in item['data']:
                cumulative_total += dataItem['value']
            allData['report'][variableName] = cumulative_total


async def getReportDailyGeneration(hass, headersData, allData, deviceID):
    now = datetime.now()

    generationData = ('{"deviceID":"' + deviceID + '","reportType": "month",' + '"variables": ["generation"],' + '"queryDate": {' + '"year":' + now.strftime(
        "%Y") + ',"month":' + now.strftime("%_m") + ',"day":' + now.strftime("%_d") + ',"hour":' + now.strftime("%_H") + "}}")

    restGeneration = RestData(
        hass,
        METHOD_POST,
        _ENDPOINT_REPORT,
        DEFAULT_ENCODING,
        None,
        headersData,
        None,
        generationData,
        DEFAULT_VERIFY_SSL,
        SSLCipherList.PYTHON_DEFAULT
    )

    await restGeneration.async_update()

    if restGeneration.data is None:
        _LOGGER.error("Unable to get daily generation from FoxESS Cloud")
        return False
    else:
        _LOGGER.debug("FoxESS daily generation data fetched correctly " +
                      restGeneration.data)

        parsed = json.loads(restGeneration.data)["result"]
        allData["reportDailyGeneration"] = parsed[0]["data"][int(
            now.strftime("%d")) - 1]


async def getRaw(hass, headersData, allData, deviceID):
    now = datetime.now()

    rawData = '{"deviceID":"'+deviceID+'","variables":["ambientTemperation","batChargePower","batCurrent","batDischargePower","batTemperature","batVolt","boostTemperation","chargeEnergyToTal","chargeTemperature","dischargeEnergyToTal","dspTemperature","epsCurrentR","epsCurrentS","epsCurrentT","epsPower","epsPowerR","epsPowerS","epsPowerT","epsVoltR","epsVoltS","epsVoltT","feedin","feedin2","feedinPower","generation","generationPower","gridConsumption","gridConsumption2","gridConsumptionPower","input","invBatCurrent","invBatPower","invBatVolt","invTemperation","loads","loadsPower","loadsPowerR","loadsPowerS","loadsPowerT","meterPower","meterPower2","meterPowerR","meterPowerS","meterPowerT","PowerFactor","pv1Current","pv1Power","pv1Volt","pv2Current","pv2Power","pv2Volt","pv3Current","pv3Power","pv3Volt","pv4Current","pv4Power","pv4Volt","pvPower","RCurrent","ReactivePower","RFreq","RPower","RVolt","SCurrent","SFreq","SoC","SPower","SVolt","TCurrent","TFreq","TPower","TVolt"],"timespan":"day","beginDate":{"year":'+now.strftime(
        "%Y")+',"month":'+now.strftime("%_m")+',"day":'+now.strftime("%_d")+',"hour":0,"minute":0,"second":0}}'

    restRaw = RestData(hass, METHOD_POST, _ENDPOINT_RAW,DEFAULT_ENCODING,
                       None, headersData, None, rawData, DEFAULT_VERIFY_SSL, SSLCipherList.PYTHON_DEFAULT)
    await restRaw.async_update()

    if restRaw.data is None:
        _LOGGER.error("Unable to get Raw data from FoxESS Cloud")
        return False
    else:
        _LOGGER.debug("FoxESS Raw data fetched correctly " +
                      restRaw.data[:150] + " ... ")
        allData['raw'] = {}
        for item in json.loads(restRaw.data)['result']:
            variableName = item['variable']
            # If data is a non-empty list, pop the last value off the list, otherwise return the previously found value
            if item["data"]:
                allData['raw'][variableName] = item["data"].pop().get("value",None)


class FoxESSGenerationPower(CoordinatorEntity, SensorEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Generation Power")
        self._attr_name = name+" - Generation Power"
        self._attr_unique_id = deviceID+"-generation-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["generationPower"]
        return None


class FoxESSGridConsumptionPower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Grid Consumption Power")
        self._attr_name = name+" - Grid Consumption Power"
        self._attr_unique_id = deviceID+"grid-consumption-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["gridConsumptionPower"]
        return None


class FoxESSFeedInPower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - FeedIn Power")
        self._attr_name = name+" - FeedIn Power"
        self._attr_unique_id = deviceID+"feedIn-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["feedinPower"]
        return None


class FoxESSBatDischargePower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat Discharge Power")
        self._attr_name = name+" - Bat Discharge Power"
        self._attr_unique_id = deviceID+"bat-discharge-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["batDischargePower"]
        return None


class FoxESSBatChargePower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat Charge Power")
        self._attr_name = name+" - Bat Charge Power"
        self._attr_unique_id = deviceID+"bat-charge-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["batChargePower"]
        return None


class FoxESSLoadPower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Load Power")
        self._attr_name = name+" - Load Power"
        self._attr_unique_id = deviceID+"load-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["loadsPower"]
        return None


class FoxESSPV1Current(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV1 Current")
        self._attr_name = name+" - PV1 Current"
        self._attr_unique_id = deviceID+"pv1-current"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv1Current"]
        return None


class FoxESSPV1Power(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV1 Power")
        self._attr_name = name+" - PV1 Power"
        self._attr_unique_id = deviceID+"pv1-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv1Power"]
        return None


class FoxESSPV1Volt(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV1 Volt")
        self._attr_name = name+" - PV1 Volt"
        self._attr_unique_id = deviceID+"pv1-volt"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv1Volt"]
        return None


class FoxESSPV2Current(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV2 Current")
        self._attr_name = name+" - PV2 Current"
        self._attr_unique_id = deviceID+"pv2-current"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv2Current"]
        return None


class FoxESSPV2Power(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV2 Power")
        self._attr_name = name+" - PV2 Power"
        self._attr_unique_id = deviceID+"pv2-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv2Power"]
        return None


class FoxESSPV2Volt(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV2 Volt")
        self._attr_name = name+" - PV2 Volt"
        self._attr_unique_id = deviceID+"pv2-volt"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv2Volt"]
        return None


class FoxESSPV3Current(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV3 Current")
        self._attr_name = name+" - PV3 Current"
        self._attr_unique_id = deviceID+"pv3-current"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv3Current"]
        return None


class FoxESSPV3Power(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV3 Power")
        self._attr_name = name+" - PV3 Power"
        self._attr_unique_id = deviceID+"pv3-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv3Power"]
        return None


class FoxESSPV3Volt(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV3 Volt")
        self._attr_name = name+" - PV3 Volt"
        self._attr_unique_id = deviceID+"pv3-volt"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv3Volt"]
        return None


class FoxESSPV4Current(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV4 Current")
        self._attr_name = name+" - PV4 Current"
        self._attr_unique_id = deviceID+"pv4-current"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv4Current"]
        return None


class FoxESSPV4Power(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV4 Power")
        self._attr_name = name+" - PV4 Power"
        self._attr_unique_id = deviceID+"pv4-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv4Power"]
        return None


class FoxESSPV4Volt(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV4 Volt")
        self._attr_name = name+" - PV4 Volt"
        self._attr_unique_id = deviceID+"pv4-volt"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pv4Volt"]
        return None


class FoxESSPVPower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV Power")
        self._attr_name = name+" - PV Power"
        self._attr_unique_id = deviceID+"pv-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["pvPower"]
        return None


class FoxESSRCurrent(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - R Current")
        self._attr_name = name+" - R Current"
        self._attr_unique_id = deviceID+"r-current"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["RCurrent"]
        return None


class FoxESSRFreq(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.FREQUENCY
    _attr_native_unit_of_measurement = FREQUENCY_HERTZ

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - R Freq")
        self._attr_name = name+" - R Freq"
        self._attr_unique_id = deviceID+"r-freq"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["RFreq"]
        return None


class FoxESSRPower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - R Power")
        self._attr_name = name+" - R Power"
        self._attr_unique_id = deviceID+"r-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["RPower"]
        return None

class FoxESSMeter2Power(CoordinatorEntity, SensorEntity):

    _attr_state_class = SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Meter2 Power")
        self._attr_name = name+" - Meter2 Power"
        self._attr_unique_id = deviceID+"meter2-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["meterPower2"]
        return None 


class FoxESSRVolt(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - R Volt")
        self._attr_name = name+" - R Volt"
        self._attr_unique_id = deviceID+"r-volt"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["RVolt"]
        return None


class FoxESSSCurrent(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - S Current")
        self._attr_name = name+" - S Current"
        self._attr_unique_id = deviceID+"s-current"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["SCurrent"]
        return None


class FoxESSSFreq(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.FREQUENCY
    _attr_native_unit_of_measurement = FREQUENCY_HERTZ

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - S Freq")
        self._attr_name = name+" - S Freq"
        self._attr_unique_id = deviceID+"s-freq"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["SFreq"]
        return None


class FoxESSSPower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - S Power")
        self._attr_name = name+" - S Power"
        self._attr_unique_id = deviceID+"s-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["SPower"]
        return None


class FoxESSSVolt(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - S Volt")
        self._attr_name = name+" - S Volt"
        self._attr_unique_id = deviceID+"s-volt"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["SVolt"]
        return None


class FoxESSTCurrent(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - T Current")
        self._attr_name = name+" - T Current"
        self._attr_unique_id = deviceID+"t-current"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["TCurrent"]
        return None


class FoxESSTFreq(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.FREQUENCY
    _attr_native_unit_of_measurement = FREQUENCY_HERTZ

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - T Freq")
        self._attr_name = name+" - T Freq"
        self._attr_unique_id = deviceID+"t-freq"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["TFreq"]
        return None


class FoxESSTPower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - T Power")
        self._attr_name = name+" - T Power"
        self._attr_unique_id = deviceID+"t-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["TPower"]
        return None


class FoxESSTVolt(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - T Volt")
        self._attr_name = name+" - T Volt"
        self._attr_unique_id = deviceID+"t-volt"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["TVolt"]
        return None


class FoxESSReactivePower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.REACTIVE_POWER
    _attr_native_unit_of_measurement = POWER_VOLT_AMPERE_REACTIVE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Reactive Power")
        self._attr_name = name+" - Reactive Power"
        self._attr_unique_id = deviceID+"reactive-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["ReactivePower"] * 1000
        return None


class FoxESSEnergyGenerated(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Energy Generated")
        self._attr_name = name+" - Energy Generated"
        self._attr_unique_id = deviceID+"energy-generated"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"]:
            if self.coordinator.data["reportDailyGeneration"]["value"] == 0:
                energygenerated = None
            else:
                energygenerated = self.coordinator.data["reportDailyGeneration"]["value"]
            return energygenerated
        return None


class FoxESSEnergyGridConsumption(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Grid Consumption")
        self._attr_name = name+" - Grid Consumption"
        self._attr_unique_id = deviceID+"grid-consumption"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"]:
            if self.coordinator.data["report"]["gridConsumption"] == 0:
                energygrid = None
            else:
                energygrid = self.coordinator.data["report"]["gridConsumption"]
            return energygrid
        return None


class FoxESSEnergyFeedin(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - FeedIn")
        self._attr_name = name+" - FeedIn"
        self._attr_unique_id = deviceID+"feedIn"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"]:
            if self.coordinator.data["report"]["feedin"] == 0:
                energyfeedin = None
            else:
                energyfeedin = self.coordinator.data["report"]["feedin"]
            return energyfeedin
        return None


class FoxESSEnergyBatCharge(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat Charge")
        self._attr_name = name+" - Bat Charge"
        self._attr_unique_id = deviceID+"bat-charge"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"]:
            if self.coordinator.data["report"]["chargeEnergyToTal"] == 0:
                energycharge = None
            else:
                energycharge = self.coordinator.data["report"]["chargeEnergyToTal"]
            return energycharge
        return None


class FoxESSEnergyBatDischarge(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat Discharge")
        self._attr_name = name+" - Bat Discharge"
        self._attr_unique_id = deviceID+"bat-discharge"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"]:
            if self.coordinator.data["report"]["dischargeEnergyToTal"] == 0:
                energydischarge = None
            else:
                energydischarge = self.coordinator.data["report"]["dischargeEnergyToTal"]
            return energydischarge
        return None


class FoxESSEnergyLoad(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Load")
        self._attr_name = name+" - Load"
        self._attr_unique_id = deviceID+"load"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["online"]:
            if self.coordinator.data["report"]["loads"] == 0:
                # was getting an error on round() when load was None, changed it to 0
                energyload = 0
            else:
                energyload = self.coordinator.data["report"]["loads"]
            #round
            return round(energyload,3)
            #original
            #return energyload
        return None


class FoxESSInverter(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Inverter")
        self._attr_name = name+" - Inverter"
        self._attr_unique_id = deviceID+"Inverter"
        self._attr_icon = "mdi:solar-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
                ATTR_DEVICE_SN,
                ATTR_PLANTNAME,
                ATTR_MODULESN,
                ATTR_DEVICE_TYPE,
                ATTR_STATUS,
                ATTR_COUNTRY,
                ATTR_COUNTRYCODE,
                ATTR_CITY,
                ATTR_ADDRESS,
                ATTR_FEEDINDATE,
                ATTR_LASTCLOUDSYNC
            ],
        )

    @property
    def native_value(self) -> str | None:
        if int(self.coordinator.data["addressbook"]["result"]["status"]) == 1:
            return "on-line"
        else:
            if int(self.coordinator.data["addressbook"]["result"]["status"]) == 2:
                return "in-alarm"
            else:
                return "off-line"

    @property
    def extra_state_attributes(self):
        return {
            ATTR_DEVICE_SN: self.coordinator.data["addressbook"]["result"][ATTR_DEVICE_SN],
            ATTR_PLANTNAME: self.coordinator.data["addressbook"]["result"][ATTR_PLANTNAME],
            ATTR_MODULESN: self.coordinator.data["addressbook"]["result"][ATTR_MODULESN],
            ATTR_DEVICE_TYPE: self.coordinator.data["addressbook"]["result"][ATTR_DEVICE_TYPE],
            ATTR_COUNTRY: self.coordinator.data["addressbook"]["result"][ATTR_COUNTRY],
            ATTR_COUNTRYCODE: self.coordinator.data["addressbook"]["result"][ATTR_COUNTRYCODE],
            ATTR_CITY: self.coordinator.data["addressbook"]["result"][ATTR_CITY],
            ATTR_ADDRESS: self.coordinator.data["addressbook"]["result"][ATTR_ADDRESS],
            ATTR_FEEDINDATE: self.coordinator.data["addressbook"]["result"][ATTR_FEEDINDATE],
            ATTR_LASTCLOUDSYNC: datetime.now()
        }


class FoxESSEnergySolar(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Solar")
        self._attr_name = name+" - Solar"
        self._attr_unique_id = deviceID+"solar"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"]:
            loads = float(self.coordinator.data["report"]["loads"])
            charge = float(self.coordinator.data["report"]["chargeEnergyToTal"])
            feedIn = float(self.coordinator.data["report"]["feedin"])
            gridConsumption = float(
                self.coordinator.data["report"]["gridConsumption"])
            discharge = float(
                self.coordinator.data["report"]["dischargeEnergyToTal"])
            energysolar = round((loads + charge + feedIn - gridConsumption - discharge),3)
            if energysolar<0:
                energysolar=0
            return round(energysolar,3)
        return None


class FoxESSSolarPower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Solar Power")
        self._attr_name = name+" - Solar Power"
        self._attr_unique_id = deviceID+"solar-power"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            loads = float(self.coordinator.data["raw"]["loadsPower"])
            if self.coordinator.data["raw"]["batChargePower"] is None:
                charge = 0
            else:
                charge = float(self.coordinator.data["raw"]["batChargePower"])
            feedIn = float(self.coordinator.data["raw"]["feedinPower"])
            gridConsumption = float(
                self.coordinator.data["raw"]["gridConsumptionPower"])
            if self.coordinator.data["raw"]["batDischargePower"] is None:
                discharge = 0
            else:
                discharge = float(
                    self.coordinator.data["raw"]["batDischargePower"])

            #check if what was returned (that some time was negative) is <0, so fix it
            total = (loads + charge + feedIn - gridConsumption - discharge)
            if total<0:
                total=0
            return round(total,3)
            # original
            #return loads + charge + feedIn - gridConsumption - discharge
        return None


class FoxESSBatSoC(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat SoC")
        self._attr_name = name+" - Bat SoC"
        self._attr_unique_id = deviceID+"bat-soc"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["SoC"]
        return  None

    @property
    def icon(self):
        return icon_for_battery_level(battery_level=self.native_value, charging=None)


class FoxESSBatTemp(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat Temperature")
        self._attr_name = name+" - Bat Temperature"
        self._attr_unique_id = deviceID+"bat-temperature"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["batTemperature"]
        return None


class FoxESSAmbientTemp(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Ambient Temperature")
        self._attr_name = name+" - Ambient Temperature"
        self._attr_unique_id = deviceID+"ambient-temperature"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["ambientTemperation"]
        return None


class FoxESSBoostTemp(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Boost Temperature")
        self._attr_name = name+" - Boost Temperature"
        self._attr_unique_id = deviceID+"boost-temperature"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["boostTemperation"]
        return None


class FoxESSInvTemp(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Inv Temperature")
        self._attr_name = name+" - Inv Temperature"
        self._attr_unique_id = deviceID+"inv-temperature"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["raw"]:
            return self.coordinator.data["raw"]["invTemperation"]
        return None
