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
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_POWER,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_TEMPERATURE,
    PLATFORM_SCHEMA,
    STATE_CLASS_TOTAL_INCREASING,
    STATE_CLASS_TOTAL,
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
    TEMP_CELSIUS,

)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)


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
_ENDPOINT_EARNINGS = "https://www.foxesscloud.com/c/v0/device/earnings?deviceID="
_ENDPOINT_RAW = "https://www.foxesscloud.com/c/v0/device/history/raw"
_ENDPOINT_REPORT = "https://www.foxesscloud.com/c/v0/device/history/report"
_ENDPOINT_ADDRESSBOOK = "https://www.foxesscloud.com/c/v0/device/addressbook?deviceID="

METHOD_POST = "POST"
METHOD_GET = "GET"


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

BATTERY_LEVELS = {"High": 80, "Medium": 50, "Low": 25, "Empty": 10}

CONF_DEVICEID = "deviceID"

CONF_SYSTEM_ID = "system_id"

DEFAULT_NAME = "FoxESS"
DEFAULT_VERIFY_SSL = True

SCAN_INTERVAL = timedelta(minutes=5)

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
        allData = {}
        token = await authAndgetToken(hass, username, hashedPassword)
        user_agent = user_agent_rotator.get_random_user_agent()
        headersData = {"token": token, "User-Agent": user_agent}

        await getErnings(hass, headersData, allData, deviceID)
        await getAddresbook(hass, headersData, allData, deviceID)
        await getRaw(hass, headersData, allData, deviceID)
        await getReport(hass, headersData, allData, deviceID)

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

    async_add_entities([FoxESSPV1Power(coordinator, name, deviceID), FoxESSPV2Power(coordinator, name, deviceID), FoxESSPV3Power(coordinator, name, deviceID), FoxESSPV4Power(coordinator, name, deviceID), FoxESSBatTemp(coordinator, name, deviceID), FoxESSBatSoC(coordinator, name, deviceID), FoxESSSolarPower(coordinator, name, deviceID), FoxESSEnergySolar(coordinator, name, deviceID), FoxESSInverter(coordinator, name, deviceID), FoxESSPGenerationPower(coordinator, name, deviceID), FoxESSGridConsumptionPower(
        coordinator, name, deviceID), FoxESSFeedInPower(coordinator, name, deviceID), FoxESSBatDischargePower(coordinator, name, deviceID), FoxESSBatChargePower(coordinator, name, deviceID), FoxESSLoadPower(coordinator, name, deviceID), FoxESSEnergyGenerated(coordinator, name, deviceID), FoxESSEnergyGridConsumption(coordinator, name, deviceID), FoxESSEnergyFeedin(coordinator, name, deviceID), FoxESSEnergyBatCharge(coordinator, name, deviceID), FoxESSEnergyBatDischarge(coordinator, name, deviceID), FoxESSEnergyLoad(coordinator, name, deviceID)])


async def authAndgetToken(hass, username, hashedPassword):

    payloadAuth = {"user": username, "password": hashedPassword}
    user_agent = user_agent_rotator.get_random_user_agent() 
    headersAuth = {"Content-Type": "application/json;charset=UTF-8",
                   "Accept": "application/json, text/plain, */*", "lang": "en", "User-Agent": user_agent}

    restAuth = RestData(hass, METHOD_POST, _ENDPOINT_AUTH, None,
                        headersAuth, None, payloadAuth, DEFAULT_VERIFY_SSL)

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


async def getErnings(hass, headersData, allData, deviceID):
    restEarnings = RestData(hass, METHOD_GET, _ENDPOINT_EARNINGS +
                            deviceID, None, headersData, None, None, DEFAULT_VERIFY_SSL)
    await restEarnings.async_update()

    response = json.loads(restEarnings.data)

    if response["result"] is None:
        if response["errno"] is not None and response["errno"] == 41930:
            raise UpdateFailed(
                f"Unable to get data from FoxESS - bad deviceID! - Read more how on thta topic: https://github.com/macxq/foxess-ha#-configuration  {restEarnings.data}")
        else:
            raise UpdateFailed(
                f"Unable to get data from FoxESS: {restEarnings.data}")
    else:
        _LOGGER.debug(
            "FoxESS Earnings data fetched correcly "+restEarnings.data)
        allData['earnings'] = json.loads(restEarnings.data)


async def getAddresbook(hass, headersData, allData, deviceID):

    # Don't bother pulling the address book again if we've already
    # got data cached in memory. It doesn't change enough to be
    # worth hitting the API each time.
    if allData.get('addressbook', []):
        return

    restAddressBook = RestData(hass, METHOD_GET, _ENDPOINT_ADDRESSBOOK +
                               deviceID, None, headersData, None, None, DEFAULT_VERIFY_SSL)
    await restAddressBook.async_update()

    if restAddressBook.data is None:
        _LOGGER.error("Unable to get Addressbook data from FoxESS Cloud")
        return False
    else:
        _LOGGER.debug(
            "FoxESS Addressbook data fetched correcly "+restAddressBook.data)
        allData['addressbook'] = json.loads(restAddressBook.data)


async def getReport(hass, headersData, allData, deviceID):
    now = datetime.now()

    reportData = '{"deviceID":"'+deviceID+'","reportType":"month","variables":["feedin","generation","gridConsumption","chargeEnergyToTal","dischargeEnergyToTal","loads"],"queryDate":{"year":'+now.strftime(
        "%Y")+',"month":'+now.strftime("%_m")+'}}'

    restReport = RestData(hass, METHOD_POST, _ENDPOINT_REPORT,
                          None, headersData, None, reportData, DEFAULT_VERIFY_SSL)

    await restReport.async_update()

    if restReport.data is None:
        _LOGGER.error("Unable to get Report data from FoxESS Cloud")
        return False
    else:
        _LOGGER.debug("FoxESS Report data fetched correcly " +
                      restReport.data[:150] + " ... ")
        allData['report'] = {}
        for item in json.loads(restReport.data)['result']:
            variableName = item['variable']
            allData['report'][variableName] = None
            for dataItem in item['data']:
                if dataItem['index'] == int(now.strftime("%d")):
                    allData['report'][variableName] = dataItem['value']


async def getRaw(hass, headersData, allData, deviceID):
    now = datetime.now()

    rawData = '{"deviceID":"'+deviceID+'","variables":["generationPower","feedinPower","batChargePower","batDischargePower","gridConsumptionPower","loadsPower","SoC","batTemperature","pv1Power","pv2Power","pv3Power","pv4Power"],"timespan":"day","beginDate":{"year":'+now.strftime(
        "%Y")+',"month":'+now.strftime("%_m")+',"day":'+now.strftime("%_d")+'}}'

    restRaw = RestData(hass, METHOD_POST, _ENDPOINT_RAW,
                       None, headersData, None, rawData, DEFAULT_VERIFY_SSL)
    await restRaw.async_update()

    if restRaw.data is None:
        _LOGGER.error("Unable to get Raw data from FoxESS Cloud")
        return False
    else:
        _LOGGER.debug("FoxESS Raw data fetched correcly " +
                      restRaw.data[:150] + " ... ")
        allData['raw'] = {}
        for item in json.loads(restRaw.data)['result']:
            variableName = item['variable']
            lastElement = len(item["data"]) - 1
            if lastElement > 0:
                allData['raw'][variableName] = item["data"][lastElement]["value"]
            else:
                allData['raw'][variableName] = None


class FoxESSPGenerationPower(CoordinatorEntity, SensorEntity):
    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Generation Power")
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
        return self.coordinator.data["earnings"]["result"]["power"]


class FoxESSGridConsumptionPower(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Grid Consumption Power")
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
        return self.coordinator.data["raw"]["gridConsumptionPower"]


class FoxESSFeedInPower(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - FeedIn Power")
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
        return self.coordinator.data["raw"]["feedinPower"]


class FoxESSBatDischargePower(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Bat Discharge Power")
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
        return self.coordinator.data["raw"]["batDischargePower"]


class FoxESSBatChargePower(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Bat Charge Power")
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
        return self.coordinator.data["raw"]["batChargePower"]


class FoxESSLoadPower(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Load Power")
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
        return self.coordinator.data["raw"]["loadsPower"]


class FoxESSPV1Power(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - PV1 Power")
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
    def native_value(self) -> str | None:
        return self.coordinator.data["raw"]["pv1Power"]


class FoxESSPV2Power(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - PV2 Power")
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
    def native_value(self) -> str | None:
        return self.coordinator.data["raw"]["pv2Power"]


class FoxESSPV3Power(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - PV3 Power")
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
    def native_value(self) -> str | None:
        return self.coordinator.data["raw"]["pv3Power"]


class FoxESSPV4Power(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - PV4 Power")
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
    def native_value(self) -> str | None:
        return self.coordinator.data["raw"]["pv4Power"]


class FoxESSEnergyGenerated(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Energy Generated")
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
        if self.coordinator.data["earnings"]["result"]["today"]["generation"] == 0:
            energygenerated = None
        else:
            energygenerated = self.coordinator.data["earnings"]["result"]["today"]["generation"]
        return energygenerated


class FoxESSEnergyGridConsumption(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Grid Consumption")
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
        if self.coordinator.data["report"]["gridConsumption"] == 0:
            energygrid = None
        else:
            energygrid = self.coordinator.data["report"]["gridConsumption"]
        return energygrid


class FoxESSEnergyFeedin(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - FeedIn")
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
        if self.coordinator.data["report"]["feedin"] == 0:
            energyfeedin = None
        else:
            energyfeedin = self.coordinator.data["report"]["feedin"]
        return energyfeedin


class FoxESSEnergyBatCharge(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Bat Charge")
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
        if self.coordinator.data["report"]["chargeEnergyToTal"] == 0:
            energycharge = None
        else:
            energycharge = self.coordinator.data["report"]["chargeEnergyToTal"]
        return energycharge


class FoxESSEnergyBatDischarge(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Bat Discharge")
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
        if self.coordinator.data["report"]["dischargeEnergyToTal"] == 0:
            energydischarge = None
        else:
            energydischarge = self.coordinator.data["report"]["dischargeEnergyToTal"]
        return energydischarge


class FoxESSEnergyLoad(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Load")
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
        if self.coordinator.data["report"]["loads"] == 0:
            energyload = None
        else:
            energyload = self.coordinator.data["report"]["loads"]
        return energyload


class FoxESSInverter(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Inverter")
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
                ATTR_FEEDINDATE
            ],
        )

    @property
    def native_value(self) -> str | None:
        if int(self.coordinator.data["addressbook"]["result"]["status"]) == 1:
            return "on-line"
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
            ATTR_FEEDINDATE: self.coordinator.data["addressbook"]["result"][ATTR_FEEDINDATE]
        }


class FoxESSEnergySolar(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Solar")
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
        loads = float(self.coordinator.data["report"]["loads"])
        charge = float(self.coordinator.data["report"]["chargeEnergyToTal"])
        feedIn = float(self.coordinator.data["report"]["feedin"])
        gridConsumption = float(
            self.coordinator.data["report"]["gridConsumption"])
        discharge = float(
            self.coordinator.data["report"]["dischargeEnergyToTal"])

        return loads + charge + feedIn - gridConsumption - discharge


class FoxESSSolarPower(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Solar Power")
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

        return loads + charge + feedIn - gridConsumption - discharge


class FoxESSBatSoC(CoordinatorEntity, SensorEntity):

    _attr_device_class = DEVICE_CLASS_BATTERY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Bat SoC")
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
        return self.coordinator.data["raw"]["SoC"]

    @property
    def icon(self):
        return icon_for_battery_level(battery_level=self.native_value, charging=None)


class FoxESSBatTemp(CoordinatorEntity, SensorEntity):

    _attr_device_class = DEVICE_CLASS_TEMPERATURE
    _attr_native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Entity - Bat Temperature")
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
        return self.coordinator.data["raw"]["batTemperature"]
