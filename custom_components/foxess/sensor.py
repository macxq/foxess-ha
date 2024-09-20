from __future__ import annotations

from collections import namedtuple
from datetime import timedelta
from datetime import datetime
import time
import logging
import json
import hashlib
import asyncio
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
    UnitOfPower,
    UnitOfTemperature,
    UnitOfEnergy,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfFrequency,
    UnitOfReactivePower,
    PERCENTAGE,
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
_ENDPOINT_OA_DOMAIN = "https://www.foxesscloud.com"
_ENDPOINT_OA_BATTERY_SETTINGS = "/op/v0/device/battery/soc/get?sn="
_ENDPOINT_OA_REPORT = "/op/v0/device/report/query"
_ENDPOINT_OA_DEVICE_DETAIL = "/op/v0/device/detail?sn="
_ENDPOINT_OA_DEVICE_VARIABLES = "/op/v0/device/real/query"
_ENDPOINT_OA_DAILY_GENERATION = "/op/v0/device/generation?sn="

METHOD_POST = "POST"
METHOD_GET = "GET"
DEFAULT_ENCODING = "UTF-8"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_TIMEOUT = 75 # increase the size of inherited timeout, the API is a bit slow

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

CONF_APIKEY = "apiKey"
CONF_DEVICESN = "deviceSN"
CONF_DEVICEID = "deviceID"
CONF_SYSTEM_ID = "system_id"
CONF_EXTPV = "extendPV"
RETRY_NEXT_SLOT = -1

DEFAULT_NAME = "FoxESS"
DEFAULT_VERIFY_SSL = False # True

SCAN_MINUTES = 1 # number of minutes betwen API requests
SCAN_INTERVAL = timedelta(minutes=SCAN_MINUTES)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Required(CONF_APIKEY): cv.string,
        vol.Required(CONF_DEVICESN): cv.string,
        vol.Required(CONF_DEVICEID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_EXTPV): cv.boolean,
    }
)

token = None

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the FoxESS sensor."""
    global LastHour, TimeSlice, last_api
    name = config.get(CONF_NAME)
    deviceID = config.get(CONF_DEVICEID)
    deviceSN = config.get(CONF_DEVICESN)
    apiKey = config.get(CONF_APIKEY)
    ExtPV = config.get(CONF_EXTPV)
    _LOGGER.debug("API Key:" + apiKey)
    _LOGGER.debug("Device SN:" + deviceSN)
    _LOGGER.debug("Device ID:" + deviceID)
    _LOGGER.debug( f"FoxESS Scan Interval: {SCAN_MINUTES} minutes" )
    _LOGGER.debug(f"Extended PV: {ExtPV}" )
    if ExtPV != True:
        ExtPV = False
    else:
        ExtPV = True
        _LOGGER.warn("Extended PV 1-18 strings enabled" )
    TimeSlice = {}
    TimeSlice[deviceSN] = RETRY_NEXT_SLOT
    last_api = 0
    LastHour = 0
    allData = {
        "report":{},
        "reportDailyGeneration": {},
        "raw":{},
        "battery":{},
        "addressbook":{},
        "online":False
    }
    allData['addressbook']['hasBattery'] = False # assume no battery is fitted for now
    allData['addressbook']['status'] = '3' # assume inverter is off-line for now

    async def async_update_data():
        _LOGGER.debug("Updating data from https://www.foxesscloud.com/")
        global token, TimeSlice, LastHour
        hournow = datetime.now().strftime("%H") # update hour now
        _LOGGER.debug(f"Time now: {hournow}, last {LastHour}")
        TSlice = TimeSlice[deviceSN] + 1 # get the time slice for the current device and increment it
        TimeSlice[deviceSN] = TSlice
        if (TSlice % 5 == 0):
            _LOGGER.debug(f"Main Poll, interval: {deviceSN}, {TimeSlice[deviceSN]}")
            # try the openapi see if we get a response
            getError=False
            if (TSlice % 15 == 0):
                # get device detail at startup, then every 15 minutes to save api calls
                getError = await getOADeviceDetail(hass, allData, deviceSN, apiKey)
                await asyncio.sleep(2) # enforced sleep to limit demand on OpenAPI
            if getError==False:
                if allData["addressbook"]["status"] is not None:
                    statetest = int(allData["addressbook"]["status"])
                else:
                    statetest = 0
                _LOGGER.debug(f" Statetest {statetest}")
                if statetest in [1,2]:
                    allData["online"] = True
                    if TSlice==0:
                        # read in battery settings if fitted at startup, then every 60 mins
                        addfail = await getOABatterySettings(hass, allData, deviceSN, apiKey)
                        await asyncio.sleep(2) # enforced sleep to limit demand on OpenAPI
                    # main real time data fetch, followed by reports
                    getError = await getRaw(hass, allData, apiKey, deviceSN, deviceID)
                    if getError==False:
                        if (TSlice % 15 == 0): # do this at startup, every 15 minutes and on the hour change
                            await asyncio.sleep(2) # enforced sleep to limit demand on OpenAPI
                            getError = await getReport(hass, allData, apiKey, deviceSN, deviceID)
                            if getError==False:
                                if TSlice==0:
                                    # get daily generation at startup, then every 60 minutes
                                    await asyncio.sleep(2) # enforced sleep to limit demand on OpenAPI
                                    getError = await getReportDailyGeneration(hass, allData, apiKey, deviceSN, deviceID)
                                    if getError==True:
                                        _LOGGER.debug("getReportDailyGeneration False")
                            else:
                                _LOGGER.debug("getReport False")
                    else:
                        _LOGGER.debug("getRaw False")
                        if statetest==2:
                            # The inverter is in alarm, don't check every minute
                            _LOGGER.debug(f" Inverter in alarm, slowing retry response for SN:{deviceSN}")
                        else:
                            # The get variables api call failed, leave it 5 minutes
                            _LOGGER.debug(f" Failed to get device variables, slowing retry response for SN:{deviceSN}")
                        allData["online"] = False
                        getError = False
                        TSlice = 25 # forces a retry on device detail in 5 minutes
                else:
                    if statetest==3:
                        # The inverter is off-line, no raw data polling, don't update entities
                        # retry device detail call every 5 minutes until it comes back on-line
                        allData["online"] = False
                        TSlice = 25 # forces a retry on device detail in 5 minutes
                        _LOGGER.debug(f" Inverter off-line set online flag false for SN:{deviceSN}")

                if allData["online"] == False:
                    _LOGGER.warning(f"{name} has Cloud timeout or the Inverter is off-line, connection will be retried in 1 minute")
            else:
                _LOGGER.warning(f"{name} has Cloud timeout fetching Device Detail, will retry in 1 minute.")

            if getError != False:
                allData["online"] = False
                if TSlice != 0:
                    TSlice=TSlice-1 # failed to get specific detail so retry slot in 1 minute
                else:
                    TSlice=RETRY_NEXT_SLOT # failed to get full data, try again in 1 minute

        # actions here are every minute
        if TSlice>=59:
            TSlice=RETRY_NEXT_SLOT # reset timeslot, ready for full data fetch at 0
        _LOGGER.debug(f"Auxilliary TimeSlice {deviceSN}, {TSlice}")

        if LastHour != hournow:
            LastHour = hournow # update the hour the last poll was run

        TimeSlice[deviceSN] = TSlice

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
            "FoxESS Cloud initialisation failed, Fatal Error - correct error and restart Home Assistant")
        return False


    async_add_entities([
        FoxESSCurrent(coordinator, name, deviceID, "PV1 Current", "pv1-current", "pv1Current"),
        FoxESSPower(coordinator, name, deviceID, "PV1 Power", "pv1-power", "pv1Power"),
        FoxESSVolt(coordinator, name, deviceID, "PV1 Volt", "pv1-volt", "pv1Volt"),
        FoxESSCurrent(coordinator, name, deviceID, "PV2 Current", "pv2-current", "pv2Current"),
        FoxESSPower(coordinator, name, deviceID, "PV2 Power", "pv2-power", "pv2Power"),
        FoxESSVolt(coordinator, name, deviceID, "PV2 Volt", "pv2-volt", "pv2Volt"),
        FoxESSCurrent(coordinator, name, deviceID, "PV3 Current", "pv3-current", "pv3Current"),
        FoxESSPower(coordinator, name, deviceID, "PV3 Power", "pv3-power", "pv3Power"),
        FoxESSVolt(coordinator, name, deviceID, "PV3 Volt", "pv3-volt", "pv3Volt"),
        FoxESSCurrent(coordinator, name, deviceID, "PV4 Current", "pv4-current", "pv4Current"),
        FoxESSPower(coordinator, name, deviceID, "PV4 Power", "pv4-power", "pv4Power"),
        FoxESSVolt(coordinator, name, deviceID, "PV4 Volt", "pv4-volt", "pv4Volt"),
        FoxESSCurrent(coordinator, name, deviceID, "PV5 Current", "pv5-current", "pv5Current"),
        FoxESSPower(coordinator, name, deviceID, "PV5 Power", "pv5-power", "pv5Power"),
        FoxESSVolt(coordinator, name, deviceID, "PV5 Volt", "pv5-volt", "pv5Volt"),
        FoxESSCurrent(coordinator, name, deviceID, "PV6 Current", "pv6-current", "pv6Current"),
        FoxESSPower(coordinator, name, deviceID, "PV6 Power", "pv6-power", "pv6Power"),
        FoxESSVolt(coordinator, name, deviceID, "PV6 Volt", "pv6-volt", "pv6Volt"),
        FoxESSPower(coordinator, name, deviceID, "PV Power", "pv-power", "pvPower"),
        FoxESSCurrent(coordinator, name, deviceID, "R Current", "r-current", "RCurrent"),
        FoxESSFreq(coordinator, name, deviceID, "R Freq", "r-freq", "RFreq"),
        FoxESSPower(coordinator, name, deviceID, "R Power", "r-power", "RPower"),
        FoxESSPowerString(coordinator, name, deviceID, "Meter2 Power", "meter2-power", "meterPower2"),
        FoxESSVolt(coordinator, name, deviceID, "R Volt", "r-volt", "RVolt"),
        FoxESSCurrent(coordinator, name, deviceID, "S Current", "s-current", "SCurrent"),
        FoxESSFreq(coordinator, name, deviceID, "S Freq", "s-freq", "SFreq"),
        FoxESSPower(coordinator, name, deviceID, "S Power", "s-power", "SPower"),
        FoxESSVolt(coordinator, name, deviceID, "S Volt", "s-volt", "SVolt"),
        FoxESSCurrent(coordinator, name, deviceID, "T Current", "t-current", "TCurrent"),
        FoxESSFreq(coordinator, name, deviceID, "T Freq", "t-freq", "TFreq"),
        FoxESSPower(coordinator, name, deviceID, "T Power", "t-power", "TPower"),
        FoxESSVolt(coordinator, name, deviceID, "T Volt", "t-volt", "TVolt"),
        FoxESSReactivePower(coordinator, name, deviceID),
        FoxESSPowerFactor(coordinator, name, deviceID),
        FoxESSTemp(coordinator, name, deviceID, "Bat Temperature", "bat-temperature", "batTemperature"),
        FoxESSTemp(coordinator, name, deviceID, "Bat Temperature2", "bat-temperature2", "batTemperature_2"),
        FoxESSTemp(coordinator, name, deviceID, "Ambient Temperature", "ambient-temperature", "ambientTemperation"),
        FoxESSTemp(coordinator, name, deviceID, "Boost Temperature", "boost-temperature", "boostTemperation"),
        FoxESSTemp(coordinator, name, deviceID, "Inv Temperature", "inv-temperature", "invTemperation"),
        FoxESSBatSoC(coordinator, name, deviceID, "Bat SoC", "bat-soc", "SoC"),
        FoxESSBatSoC(coordinator, name, deviceID, "Bat SoC1", "bat-soc1", "SoC_1"),
        FoxESSBatSoC(coordinator, name, deviceID, "Bat SoC2", "bat-soc2", "SoC_2"),
        FoxESSPower(coordinator, name, deviceID, "Inverter Bat Power", "inv-Bat-Power", "invBatPower"),
        FoxESSPower(coordinator, name, deviceID, "Inverter Bat Power2", "inv-Bat-Power2", "invBatPower_2"),
        FoxESSBatMinSoC(coordinator, name, deviceID),
        FoxESSBatMinSoConGrid(coordinator, name, deviceID),
        FoxESSSolarPower(coordinator, name, deviceID),
        FoxESSEnergyThroughput(coordinator, name, deviceID),
        FoxESSEnergySolar(coordinator, name, deviceID),
        FoxESSInverter(coordinator, name, deviceID),
        FoxESSPowerString(coordinator, name, deviceID, "Generation Power", "-generation-power", "generationPower"),
        FoxESSPowerString(coordinator, name, deviceID, "Grid Consumption Power", "grid-consumption-power", "gridConsumptionPower"),
        FoxESSPowerString(coordinator, name, deviceID, "FeedIn Power", "feedIn-power", "feedinPower"),
        FoxESSPowerString(coordinator, name, deviceID, "Bat Discharge Power", "bat-discharge-power", "batDischargePower"),
        FoxESSPowerString(coordinator, name, deviceID, "Bat Charge Power", "bat-charge-power", "batChargePower"),
        FoxESSPowerString(coordinator, name, deviceID, "Load Power", "load-power", "loadsPower"),
        FoxESSEnergyGenerated(coordinator, name, deviceID, "Energy Generated", "energy-generated", "value"),
        FoxESSEnergyGenerated(coordinator, name, deviceID, "Energy Generated Month", "energy-generated-month", "month"),
        FoxESSEnergyGenerated(coordinator, name, deviceID, "Energy Generated Cumulative", "energy-generated-cumulative", "cumulative"),
        FoxESSEnergyGridConsumption(coordinator, name, deviceID),
        FoxESSEnergyFeedin(coordinator, name, deviceID),
        FoxESSEnergyBatCharge(coordinator, name, deviceID),
        FoxESSEnergyBatDischarge(coordinator, name, deviceID),
        FoxESSEnergyLoad(coordinator, name, deviceID),
        FoxESSResidualEnergy(coordinator, name, deviceID),
        FoxESSResponseTime(coordinator, name, deviceID),
        FoxESSRunningState(coordinator, name, deviceID, "Running State", "running-state", "runningState")
    ])

    if ExtPV:
        async_add_entities([
            FoxESSCurrent(coordinator, name, deviceID, "PV7 Current", "pv7-current", "pv7Current"),
            FoxESSPower(coordinator, name, deviceID, "PV7 Power", "pv7-power", "pv7Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV7 Volt", "pv7-volt", "pv7Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV8 Current", "pv8-current", "pv8Current"),
            FoxESSPower(coordinator, name, deviceID, "PV8 Power", "pv8-power", "pv8Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV8 Volt", "pv8-volt", "pv8Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV9 Current", "pv9-current", "pv9Current"),
            FoxESSPower(coordinator, name, deviceID, "PV9 Power", "pv9-power", "pv9Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV9 Volt", "pv9-volt", "pv9Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV10 Current", "pv10-current", "pv10Current"),
            FoxESSPower(coordinator, name, deviceID, "PV10 Power", "pv10-power", "pv10Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV10 Volt", "pv10-volt", "pv10Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV11 Current", "pv11-current", "pv11Current"),
            FoxESSPower(coordinator, name, deviceID, "PV11 Power", "pv11-power", "pv11Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV11 Volt", "pv11-volt", "pv11Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV12 Current", "pv12-current", "pv12Current"),
            FoxESSPower(coordinator, name, deviceID, "PV12 Power", "pv12-power", "pv12Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV12 Volt", "pv12-volt", "pv12Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV13 Current", "pv13-current", "pv13Current"),
            FoxESSPower(coordinator, name, deviceID, "PV13 Power", "pv13-power", "pv13Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV13 Volt", "pv13-volt", "pv13Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV14 Current", "pv14-current", "pv14Current"),
            FoxESSPower(coordinator, name, deviceID, "PV14 Power", "pv14-power", "pv14Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV14 Volt", "pv14-volt", "pv14Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV15 Current", "pv15-current", "pv15Current"),
            FoxESSPower(coordinator, name, deviceID, "PV15 Power", "pv15-power", "pv15Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV15 Volt", "pv15-volt", "pv15Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV16 Current", "pv16-current", "pv16Current"),
            FoxESSPower(coordinator, name, deviceID, "PV16 Power", "pv16-power", "pv16Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV16 Volt", "pv16-volt", "pv16Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV17 Current", "pv17-current", "pv17Current"),
            FoxESSPower(coordinator, name, deviceID, "PV17 Power", "pv17-power", "pv17Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV17 Volt", "pv17-volt", "pv17Volt"),
            FoxESSCurrent(coordinator, name, deviceID, "PV18 Current", "pv18-current", "pv18Current"),
            FoxESSPower(coordinator, name, deviceID, "PV18 Power", "pv18-power", "pv18Power"),
            FoxESSVolt(coordinator, name, deviceID, "PV18 Volt", "pv18-volt", "pv18Volt")
        ])


class GetAuth:

    def get_signature(self, token, path, lang='en'):
        """
        This function is used to generate a signature consisting of URL, token, and timestamp, and return a dictionary containing the signature and other information.
            :param token: your key
            :param path:  your request path
            :param lang: language, default is English.
            :return: with authentication header
        """
        timestamp = round(time.time() * 1000)
        signature = fr'{path}\r\n{token}\r\n{timestamp}'
        # or use user_agent_rotator.get_random_user_agent() for user-agent
        result = {
            'token': token,
            'lang': lang,
            'timestamp': str(timestamp),
            'Content-Type': 'application/json',
            'signature': self.md5c(text=signature),
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/117.0.0.0 Safari/537.36',
            'Connection': 'close'
        }

        return result

    @staticmethod
    def md5c(text="", _type="lower"):
        res = hashlib.md5(text.encode(encoding='UTF-8')).hexdigest()
        if _type.__eq__("lower"):
            return res
        else:
            return res.upper()


async def waitforAPI():
    global last_api
    # wait for openAPI, there is a minimum of 1 second allowed between OpenAPI query calls
    # check if last_api call was less than a second ago and if so delay the balance of 1 second
    now = time.time()
    last = last_api
    diff = now - last if last != 0 else 1
    diff = round( (diff+0.2) ,2)
    if diff < 1:
        await asyncio.sleep(diff)
        _LOGGER.debug(f"API enforced delay, wait: {diff}")
    now = time.time()
    last_api = now
    return False

async def getOADeviceDetail(hass, allData, deviceSN, apiKey):

    await waitforAPI()

    path = "/op/v0/device/detail"
    headerData = GetAuth().get_signature(token=apiKey, path=path)

    path = _ENDPOINT_OA_DOMAIN + _ENDPOINT_OA_DEVICE_DETAIL
    _LOGGER.debug("OADevice Detail fetch " + path + deviceSN)
    timestamp = round(time.time() * 1000)

    restOADeviceDetail = RestData(hass, METHOD_GET, path + deviceSN, DEFAULT_ENCODING,  None, headerData, None, None, DEFAULT_VERIFY_SSL, SSLCipherList.PYTHON_DEFAULT, DEFAULT_TIMEOUT)
    await restOADeviceDetail.async_update()

    if restOADeviceDetail.data is None or restOADeviceDetail.data == '':
        _LOGGER.debug("Unable to get OA Device Detail from FoxESS Cloud")
        return True
    else:
        response = json.loads(restOADeviceDetail.data)
        if response["errno"] == 0 and response["msg"] == 'success' :
            ResponseTime = round(time.time() * 1000) - timestamp
            if ResponseTime > 0:
                allData['raw']['ResponseTime'] = ResponseTime
            else:
                allData['raw']['ResponseTime'] = 0
            _LOGGER.debug(f"OA Device Detail Good Response: {response['result']}")
            result = response['result']
            allData['addressbook'] = result
            # manually poke this in as on the old cloud it was called plantname, need to keep in line with old entity name
            plantName = result['stationName']
            allData['addressbook']['plantName'] = plantName
            testBattery = result['hasBattery']
            if testBattery:
                _LOGGER.debug(f"OA Device Detail System has Battery: {testBattery}")
            else:
                _LOGGER.debug(f"OA Device Detail System has No Battery: {testBattery}")
            return False
        else:
            _LOGGER.error(f"OA Device Detail Bad Response: {response}")
            return True

async def getOABatterySettings(hass, allData, deviceSN, apiKey):

    await waitforAPI() # check for api delay

    path = "/op/v0/device/battery/soc/get"
    headerData = GetAuth().get_signature(token=apiKey, path=path)

    path = _ENDPOINT_OA_DOMAIN + _ENDPOINT_OA_BATTERY_SETTINGS
    if "hasBattery" not in allData["addressbook"]:
        hasBattery = False
    else:
        hasBattery = allData['addressbook']['hasBattery']

    if hasBattery:
        # only make this call if device detail reports battery fitted
        _LOGGER.debug("OABattery Settings fetch " + path + deviceSN)
        restOABatterySettings = RestData(hass, METHOD_GET, path + deviceSN, DEFAULT_ENCODING,  None, headerData, None, None, DEFAULT_VERIFY_SSL, SSLCipherList.PYTHON_DEFAULT, DEFAULT_TIMEOUT)
        await restOABatterySettings.async_update()

        if restOABatterySettings.data is None:
            _LOGGER.debug("Unable to get OA Battery Settings from FoxESS Cloud")
            return True
        else:
            response = json.loads(restOABatterySettings.data)
            if response["errno"] == 0 and response["msg"] == 'success' :
                _LOGGER.debug(f"OA Battery Settings Good Response: {response['result']}")
                result = response['result']
                minSoc = result['minSoc']
                minSocOnGrid = result['minSocOnGrid']
                allData["battery"]["minSoc"] = minSoc
                allData["battery"]["minSocOnGrid"] = minSocOnGrid
                _LOGGER.debug(f"OA Battery Settings read MinSoc: {minSoc}, MinSocOnGrid: {minSocOnGrid}")
                return False
            else:
                _LOGGER.error(f"OA Battery Settings Bad Response: {response}")
                return True
    else:
        # device detail reports no battery fitted so reset these variables to show unknown
        allData["battery"]["minSoc"] = None
        allData["battery"]["minSocOnGrid"] = None
        return False


async def getReport(hass, allData, apiKey, deviceSN, deviceID):

    await waitforAPI() # check for api delay

    path = _ENDPOINT_OA_REPORT
    headerData = GetAuth().get_signature(token=apiKey, path=path)

    path = _ENDPOINT_OA_DOMAIN + _ENDPOINT_OA_REPORT
    _LOGGER.debug("OA Report fetch " + path )

    now = datetime.now()
    month = str(datetime.now().month)     # now.strftime("%-m")

    reportData = '{"sn":"'+deviceSN+'","year":'+now.strftime("%Y")+',"month":'+month+',"dimension":"month","variables":["feedin","generation","gridConsumption","chargeEnergyToTal","dischargeEnergyToTal","loads"]}'

    _LOGGER.debug("getReport OA request:" + reportData)

    restOAReport = RestData(
        hass,
        METHOD_POST,
        path,
        DEFAULT_ENCODING,
        None,
        headerData,
        None,
        reportData,
        DEFAULT_VERIFY_SSL,
        SSLCipherList.PYTHON_DEFAULT,
        DEFAULT_TIMEOUT
    )

    await restOAReport.async_update()

    if restOAReport.data is None or restOAReport.data == '':
        _LOGGER.debug("Unable to get OA Report from FoxESS Cloud")
        return True
    else:
        # Openapi responded so process data
        response = json.loads(restOAReport.data)
        if response["errno"] == 0 and response["msg"] == 'success' :
            _LOGGER.debug(f"OA Report Data fetched OK: {response} "+ restOAReport.data[:350])
            result = json.loads(restOAReport.data)['result']
            today = int(now.strftime("%d")) # need today as an integer to locate in the monthly report index
            for item in result:
                variableName = item['variable']
                # Daily reports break down the data hour by month for each day
                # so locate the current days index and use that as the sum
                index = 1
                cumulative_total = 0
                for dataItem in item['values']:
                    if today==index: # we're only interested in the total for today
                        if dataItem != None:
                            cumulative_total = dataItem
                        else:
                            _LOGGER.warn(f"Report month fetch, None received")
                        break
                    index+=1
                    #cumulative_total += dataItem
                allData['report'][variableName] = round(cumulative_total,3)
                _LOGGER.debug(f"OA Report Variable: {variableName}, Total: {cumulative_total}")
            return False
        else:
            _LOGGER.debug(f"OA Report Bad Response: {response} "+ restOAReport.data)
            return True


async def getReportDailyGeneration(hass, allData, apiKey, deviceSN, deviceID):

    await waitforAPI() # check for api delay

    now = datetime.now()
    path = "/op/v0/device/generation"
    headerData = GetAuth().get_signature(token=apiKey, path=path)

    path = _ENDPOINT_OA_DOMAIN + _ENDPOINT_OA_DAILY_GENERATION
    _LOGGER.debug("getReportDailyGeneration fetch " + path )

    generationData = '{"sn":"'+deviceSN+'","dimension":"day"}'

    _LOGGER.debug("getReportDailyGeneration OA request:" + generationData)

    restOAgen = RestData(
        hass,
        METHOD_GET,
        path + deviceSN,
        DEFAULT_ENCODING,
        None,
        headerData,
        None,
        generationData,
        DEFAULT_VERIFY_SSL,
        SSLCipherList.PYTHON_DEFAULT,
        DEFAULT_TIMEOUT
    )

    await restOAgen.async_update()

    if restOAgen.data is None or restOAgen.data == '':
        _LOGGER.debug("Unable to get OA Daily Generation Report from FoxESS Cloud")
        return True
    else:
        response = json.loads(restOAgen.data)
        if response["errno"] == 0 and response["msg"] == 'success' :
            _LOGGER.debug("OA Daily Generation Report Data fetched OK Response:"+ restOAgen.data[:500])

            parsed = json.loads(restOAgen.data)["result"]
            if "today" not in parsed:
                allData["reportDailyGeneration"]["value"] = 0
                _LOGGER.debug(f"OA Daily Generation Report data, today has no value: {parsed} set to 0")
            else:
                allData["reportDailyGeneration"]["value"] = parsed['today']
                _LOGGER.debug(f"OA Daily Generation Report data: todays value {parsed['today']} ")
            if "month" not in parsed:
                allData["reportDailyGeneration"]["month"] = 0
                _LOGGER.debug(f"OA Daily Generation Report data, month has no value: {parsed} set to 0")
            else:
                allData["reportDailyGeneration"]["month"] = parsed['month']
                _LOGGER.debug(f"OA Daily Generation Report data: month value {parsed['month']} ")
            if "cumulative" not in parsed:
                allData["reportDailyGeneration"]["cumulative"] = 0
                _LOGGER.debug(f"OA Daily Generation Report data, cumulative has no value: {parsed} set to 0")
            else:
                allData["reportDailyGeneration"]["cumulative"] = parsed['cumulative']
                _LOGGER.debug(f"OA Daily Generation Report data: cumulative value {parsed['cumulative']} ")
            return False
        else:
            _LOGGER.debug(f"OA Daily Generation Report Bad Response: {response} "+ restOAgen.data)
            return True


async def getRaw(hass, allData, apiKey, deviceSN, deviceID):

    await waitforAPI() # check for api delay

    # "deviceSN" used for OpenAPI and it only fetches the real time data

    rawData =  '{"sn":"'+deviceSN+'" }'

    _LOGGER.debug("getRaw OA request:" +rawData)

    timestamp = round(time.time() * 1000)

    path = _ENDPOINT_OA_DEVICE_VARIABLES
    headerData = GetAuth().get_signature(token=apiKey, path=path)

    path = _ENDPOINT_OA_DOMAIN + _ENDPOINT_OA_DEVICE_VARIABLES

    restOADeviceVariables = RestData(
        hass,
        METHOD_POST,
        path,
        DEFAULT_ENCODING,
        None,
        headerData,
        None,
        rawData,
        DEFAULT_VERIFY_SSL,
        SSLCipherList.PYTHON_DEFAULT,
        DEFAULT_TIMEOUT
    )

    await restOADeviceVariables.async_update()

    if restOADeviceVariables.data is None or restOADeviceVariables.data == '':
        _LOGGER.debug("Unable to get OA Variables from FoxESS Cloud")
        return True
    else:
        # Openapi responded correctly
        response = json.loads(restOADeviceVariables.data)
        if response["errno"] == 0 and response["msg"] == 'success' :
            ResponseTime = round(time.time() * 1000) - timestamp
            if ResponseTime > 0:
                allData['raw']['ResponseTime'] = ResponseTime
            else:
                allData['raw']['ResponseTime'] = 0

            test = json.loads(restOADeviceVariables.data)['result']
            result = test[0].get('datas')
            _LOGGER.debug(f"OA Variables Good Response: {result}")
            # allData['raw'] = {}
            for item in result: # json.loads(result): # restOADeviceVariables.data)['result']:
                variableName = item['variable']
                # If value exists
                if item.get('value') is not None:
                    variableValue = item['value']
                else:
                    variableValue = 0
                    _LOGGER.debug( f"Variable {variableName} no value, set to zero" )
                # fix for second battery items
                if variableName == 'SoC_1':
                    variableName = 'SoC_1' # do nothing for the moment, future release might align this correctly to use SoC
                elif variableName == 'batTemperature_1':
                    variableName = 'batTemperature' # use same entity as for single battery systems
                elif variableName == 'invBatPower_1':
                    variableName = 'invBatPower' # use same entity as for single battery systems

                allData['raw'][variableName] = variableValue
                _LOGGER.debug( f"Var: {variableName}, SN: {deviceSN} set to {allData['raw'][variableName]}" )
            return False
        else:
            _LOGGER.debug(f"OA Device Variables Bad Response: {response}")
            return True

class FoxESSPowerString(CoordinatorEntity, SensorEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug(f"Initiating Entity - {self._nameValue}")
        self._attr_name = f"{name} - {self._nameValue}"
        self._attr_unique_id = f"{deviceID}{self._uniqueValue}"
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
            if self._keyValue not in self.coordinator.data["raw"]:
                _LOGGER.debug(f"{self._keyValue} None")
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None

class FoxESSCurrent(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug(f"Initiating Entity - {self._nameValue}")
        self._attr_name = f"{name} - {self._nameValue}"
        self._attr_unique_id = f"{deviceID}{self._uniqueValue}"
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
            if self._keyValue not in self.coordinator.data["raw"]:
                _LOGGER.debug(f"{self._keyValue} None")
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSFreq(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.FREQUENCY
    _attr_native_unit_of_measurement = UnitOfFrequency.HERTZ

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug(f"Initiating Entity - {self._nameValue}")
        self._attr_name = f"{name} - {self._nameValue}"
        self._attr_unique_id = f"{deviceID}{self._uniqueValue}"
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
            if self._keyValue not in self.coordinator.data["raw"]:
                _LOGGER.debug(f"{self._keyValue} None")
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSPower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug(f"Initiating Entity - {self._nameValue}")
        self._attr_name = f"{name} - {self._nameValue}"
        self._attr_unique_id = f"{deviceID}{self._uniqueValue}"
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
            if self._keyValue not in self.coordinator.data["raw"]:
                _LOGGER.debug(f"{self._keyValue} None")
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSVolt(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug(f"Initiating Entity - {self._nameValue}")
        self._attr_name = f"{name} - {self._nameValue}"
        self._attr_unique_id = f"{deviceID}{self._uniqueValue}"
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
            if self._keyValue not in self.coordinator.data["raw"]:
                _LOGGER.debug(f"{self._keyValue} None")
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSReactivePower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.REACTIVE_POWER
    _attr_native_unit_of_measurement = UnitOfReactivePower.VOLT_AMPERE_REACTIVE

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
            if "ReactivePower" not in self.coordinator.data["raw"]:
                _LOGGER.debug("ReactivePower None")
            else:
                return self.coordinator.data["raw"]["ReactivePower"] * 1000
        return None


class FoxESSPowerFactor(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER_FACTOR
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Power Factor")
        self._attr_name = name+" - Power Factor"
        self._attr_unique_id = deviceID+"power-factor"
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
            if "PowerFactor" not in self.coordinator.data["raw"]:
                _LOGGER.debug("PowerFactor None")
            else:
                return self.coordinator.data["raw"]["PowerFactor"]
        return None

class FoxESSEnergyGenerated(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug(f"Initiating Entity - {self._nameValue}")
        self._attr_name = f"{name} - {self._nameValue}"
        self._attr_unique_id = f"{deviceID}{self._uniqueValue}"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self._keyValue not in self.coordinator.data["reportDailyGeneration"]:
            _LOGGER.debug(f"{self._keyValue} None")
        else:
            if self.coordinator.data["reportDailyGeneration"][self._keyValue] == 0:
                energygenerated = 0
            else:
                energygenerated = self.coordinator.data["reportDailyGeneration"][self._keyValue]
                if energygenerated > 0:
                    energygenerated = round(energygenerated,3)
                else:
                    energygenerated = 0
            return energygenerated
        return None

class FoxESSEnergyThroughput(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Energy Throughput")
        self._attr_name = name+" - Energy Throughput"
        self._attr_unique_id = deviceID+"energy-throughput"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if "energyThroughput" not in self.coordinator.data["raw"]:
            _LOGGER.debug("raw Energy Throughput None")
        else:
            if self.coordinator.data["raw"]["energyThroughput"] == 0:
                energygenerated = 0
            else:
                energygenerated = self.coordinator.data["raw"]["energyThroughput"]
                if energygenerated > 0:
                    energygenerated = round(energygenerated,3)
                else:
                    energygenerated = 0
            return energygenerated
        return None


class FoxESSEnergyGridConsumption(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

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
        if "gridConsumption" not in self.coordinator.data["report"]:
            _LOGGER.debug("report gridConsumption None")
        else:
            if self.coordinator.data["report"]["gridConsumption"] == 0:
                energygrid = 0
            else:
                energygrid = self.coordinator.data["report"]["gridConsumption"]
            return energygrid
        return None


class FoxESSEnergyFeedin(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

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
        if "feedin" not in self.coordinator.data["report"]:
            _LOGGER.debug("report feedin None")
        else:
            if self.coordinator.data["report"]["feedin"] == 0:
                energyfeedin = 0
            else:
                energyfeedin = self.coordinator.data["report"]["feedin"]
            return energyfeedin
        return None


class FoxESSEnergyBatCharge(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

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
        if "chargeEnergyToTal" not in self.coordinator.data["report"]:
            _LOGGER.debug("report chargeEnergyToTal None")
        else:
            if self.coordinator.data["report"]["chargeEnergyToTal"] == 0:
                energycharge = 0
            else:
                energycharge = self.coordinator.data["report"]["chargeEnergyToTal"]
            return energycharge
        return None


class FoxESSEnergyBatDischarge(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

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
        if "dischargeEnergyToTal" not in self.coordinator.data["report"]:
            _LOGGER.debug("report dischargeEnergyToTal None")
        else:
            if self.coordinator.data["report"]["dischargeEnergyToTal"] == 0:
                energydischarge = 0
            else:
                energydischarge = self.coordinator.data["report"]["dischargeEnergyToTal"]
            return energydischarge
        return None


class FoxESSEnergyLoad(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

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
        if "loads" not in self.coordinator.data["report"]:
            _LOGGER.debug("report loads None")
        else:
            if self.coordinator.data["report"]["loads"] == 0:
                energyload = 0
            else:
                energyload = self.coordinator.data["report"]["loads"]
            #round
            return round(energyload,3)
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
        if self.coordinator.data["online"] or (self.coordinator.data["online"]==False and int(self.coordinator.data["addressbook"]["status"]) == 3 ):
            if "status" not in self.coordinator.data["addressbook"]:
                _LOGGER.debug("addressbook status None")
            else:
                if int(self.coordinator.data["addressbook"]["status"]) == 1:
                    return "on-line"
                else:
                    if int(self.coordinator.data["addressbook"]["status"]) == 2:
                        return "in-alarm"
                    else:
                        return "off-line"
        return None

    @property
    def extra_state_attributes(self):
        if self.coordinator.data["online"]:
            if "status" not in self.coordinator.data["addressbook"]:
                _LOGGER.debug("addressbook status attributes None")
            else:
                return {
                    ATTR_DEVICE_SN: self.coordinator.data["addressbook"][ATTR_DEVICE_SN],
                    ATTR_PLANTNAME: self.coordinator.data["addressbook"][ATTR_PLANTNAME],
                    ATTR_MODULESN: self.coordinator.data["addressbook"][ATTR_MODULESN],
                    ATTR_DEVICE_TYPE: self.coordinator.data["addressbook"][ATTR_DEVICE_TYPE],
                    #ATTR_COUNTRY: self.coordinator.data["addressbook"]["result"][ATTR_COUNTRY],
                    #ATTR_COUNTRYCODE: self.coordinator.data["addressbook"]["result"][ATTR_COUNTRYCODE],
                    #ATTR_CITY: self.coordinator.data["addressbook"]["result"][ATTR_CITY],
                    #ATTR_ADDRESS: self.coordinator.data["addressbook"]["result"][ATTR_ADDRESS],
                    #ATTR_FEEDINDATE: self.coordinator.data["addressbook"]["result"][ATTR_FEEDINDATE],
                    ATTR_LASTCLOUDSYNC: datetime.now()
                }
        return None


class FoxESSRunningState(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug(f"Initiating Entity - {self._nameValue}")
        self._attr_name = f"{name} - {self._nameValue}"
        self._attr_unique_id = f"{deviceID}{self._uniqueValue}"
        self._attr_icon = "mdi:state-machine"
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
            if self._keyValue not in self.coordinator.data["raw"]:
                _LOGGER.debug(f"{self._keyValue} None")
            else:
                res = self.coordinator.data["raw"][self._keyValue]
                if res == "160":
                    resText = f"{res}: self-test"
                elif res == "161":
                    resText = f"{res}: waiting"
                elif res == "162":
                    resText = f"{res}: checking"
                elif res == "163":
                    resText = f"{res}: on-grid"
                elif res == "164":
                    resText = f"{res}: off-grid"
                elif res == "165":
                    resText = f"{res}: fault"
                elif res == "166":
                    resText = f"{res}: permanent-fault"
                elif res == "167":
                    resText = f"{res}: standby"
                elif res == "168":
                    resText = f"{res}: upgrading"
                elif res == "169":
                    resText = f"{res}: fct"
                elif res == "170":
                    resText = f"{res}: illegal"
                else:
                    _LOGGER.debug(f"runcode {res}")
                    resText = f"{res}: unknown code"
                #return self.coordinator.data["raw"][self._keyValue]
                return resText
        return  None


class FoxESSEnergySolar(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

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
        if "loads" not in self.coordinator.data["report"]:
            loads = 0
        else:
            loads = float(self.coordinator.data["report"]["loads"])

        if "chargeEnergyToTal" not in self.coordinator.data["report"]:
            charge = 0
        else:
            charge = float(self.coordinator.data["report"]["chargeEnergyToTal"])

        if "feedin" not in self.coordinator.data["report"]:
            feedIn = 0
        else:
            feedIn = float(self.coordinator.data["report"]["feedin"])

        if "gridConsumption" not in self.coordinator.data["report"]:
            gridConsumption = 0
        else:
            gridConsumption = float(self.coordinator.data["report"]["gridConsumption"])

        if "dischargeEnergyToTal" not in self.coordinator.data["report"]:
            discharge = 0
        else:
            discharge = float(self.coordinator.data["report"]["dischargeEnergyToTal"])

        energysolar = round((loads + charge + feedIn - gridConsumption - discharge),3)
        if energysolar<0:
            energysolar=0
        return round(energysolar,3)


class FoxESSSolarPower(CoordinatorEntity, SensorEntity):

    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
        if "loadsPower" not in self.coordinator.data["raw"]:
            loads = 0
        else:
            loads = float(self.coordinator.data["raw"]["loadsPower"])

        if "batChargePower" not in self.coordinator.data["raw"]:
            charge = 0
        else:
            if self.coordinator.data["raw"]["batChargePower"] is None:
                charge = 0
            else:
                charge = float(self.coordinator.data["raw"]["batChargePower"])

        if "feedinPower" not in self.coordinator.data["raw"]:
            feedIn = 0
        else:
            feedIn = float(self.coordinator.data["raw"]["feedinPower"])

        if "gridConsumptionPower" not in self.coordinator.data["raw"]:
            gridConsumption = 0
        else:
            gridConsumption = float(self.coordinator.data["raw"]["gridConsumptionPower"])

        if "batDischargePower" not in self.coordinator.data["raw"]:
            discharge = 0
        else:
            if self.coordinator.data["raw"]["batDischargePower"] is None:
                discharge = 0
            else:
                discharge = float(self.coordinator.data["raw"]["batDischargePower"])

        #check if what was returned (that some time was negative) is <0, so fix it
        total = (loads + charge + feedIn - gridConsumption - discharge)
        if total<0:
            total=0
        return round(total,3)


class FoxESSBatSoC(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug(f"Initiating Entity - {self._nameValue}")
        self._attr_name = f"{name} - {self._nameValue}"
        self._attr_unique_id = f"{deviceID}{self._uniqueValue}"
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
            if self._keyValue not in self.coordinator.data["raw"]:
                _LOGGER.debug(f"{self._keyValue} None")
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return  None

    @property
    def icon(self):
        return icon_for_battery_level(battery_level=self.native_value, charging=None)

class FoxESSBatMinSoC(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat MinSoC")
        self._attr_name = name+" - Bat MinSoC"
        self._attr_unique_id = deviceID+"bat-minsoc"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["battery"]:
            if "minSoc" not in self.coordinator.data["battery"]:
                _LOGGER.debug("minSoc None")
            else:
                return self.coordinator.data["battery"]["minSoc"]
        return  None

    @property
    def icon(self):
        return icon_for_battery_level(battery_level=self.native_value, charging=None)

class FoxESSBatMinSoConGrid(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat minSocOnGrid")
        self._attr_name = name+" - Bat minSocOnGrid"
        self._attr_unique_id = deviceID+"bat-minSocOnGrid"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data["online"] and self.coordinator.data["battery"]:
            if "minSocOnGrid" not in self.coordinator.data["battery"]:
                _LOGGER.debug("minSocOnGrid None")
            else:
                return self.coordinator.data["battery"]["minSocOnGrid"]
        return  None

    @property
    def icon(self):
        return icon_for_battery_level(battery_level=self.native_value, charging=None)


class FoxESSTemp(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug(f"Initiating Entity - {self._nameValue}")
        self._attr_name = f"{name} - {self._nameValue}"
        self._attr_unique_id = f"{deviceID}{self._uniqueValue}"
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
            if self._keyValue not in self.coordinator.data["raw"]:
                _LOGGER.debug(f"{self._keyValue} None")
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSResidualEnergy(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Residual Energy")
        self._attr_name = name+" - Residual Energy"
        self._attr_unique_id = deviceID+"residual-energy"
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
            if "ResidualEnergy" not in self.coordinator.data["raw"]:
                _LOGGER.debug("ResidualEnergy None")
            else:
                re = self.coordinator.data["raw"]["ResidualEnergy"]
                if re > 0:
                    re = re / 100
                else:
                    re = 0
                return re
        return None

class FoxESSResponseTime(CoordinatorEntity, SensorEntity):

    _attr_native_unit_of_measurement = 'mS'

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Response Time")
        self._attr_name = name+" - Response Time"
        self._attr_unique_id = deviceID+"response-time"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        if "ResponseTime" not in self.coordinator.data["raw"]:
            _LOGGER.debug("ResponseTime None")
        else:
            return self.coordinator.data["raw"]["ResponseTime"]
        return None
