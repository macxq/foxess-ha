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
TRY_OLD_CLOUD_API = False

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
RETRY_NEXT_SLOT = -1

DEFAULT_NAME = "FoxESS"
DEFAULT_VERIFY_SSL = False # True

SCAN_MINUTES = 1 # number of minutes betwen API requests 
SCAN_INTERVAL = timedelta(minutes=SCAN_MINUTES)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_APIKEY): cv.string,
        vol.Required(CONF_DEVICESN): cv.string,
        vol.Required(CONF_DEVICEID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)

token = None

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the FoxESS sensor."""
    global apiKey, deviceSN, deviceID, TimeSlice,allData,LastHour, hasBattery
    name = config.get(CONF_NAME)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    deviceID = config.get(CONF_DEVICEID)
    deviceSN = config.get(CONF_DEVICESN)
    apiKey = config.get(CONF_APIKEY)
    _LOGGER.debug("API Key:" + apiKey)
    _LOGGER.debug("Device SN:" + deviceSN)
    _LOGGER.debug("Device ID:" + deviceID)
    _LOGGER.debug( f"FoxESS Scan Interval: {SCAN_MINUTES} minutes" )
    TimeSlice = RETRY_NEXT_SLOT
    LastHour = 0
    hasBattery = True
    allData = {
        "report":{},
        "reportDailyGeneration": {},
        "raw":{},
        "battery":{},
        "online":False
    }



    async def async_update_data():
        _LOGGER.debug("Updating data from https://www.foxesscloud.com/")

        global token,TimeSlice,allData,LastHour
        hournow = datetime.now().strftime("%_H") # update hour now
        _LOGGER.debug(f"Time now: {hournow}, last {LastHour}")

        TimeSlice+=1
        if (TimeSlice % 5 == 0):
            _LOGGER.debug(f"TimeSlice 5 Interval: {TimeSlice}")

            # try old cloud interface - doesn't matter if this fails
            hashedPassword = hashlib.md5(password.encode()).hexdigest()
            if token is None:
                _LOGGER.debug("Token is empty, authenticating")
                token = await authAndgetToken(hass, username, hashedPassword)

            user_agent = USER_AGENT # or use- user_agent_rotator.get_random_user_agent()
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
                           "Connection": "close",
                           "X-Requested-With": "XMLHttpRequest"}

            if TRY_OLD_CLOUD_API:
                addfail = await getAddresbook(hass, headersData, allData, username, hashedPassword, deviceID)
                if addfail == 0:
                    _LOGGER.debug("FoxESS old cloud API no Addressbook data, token reset")
                else:
                    _LOGGER.debug("FoxESS old cloud API Addressbook data read ok")

            # try the openapi see if we get a response
            addfail = await getOADeviceDetail(hass, allData, deviceSN, apiKey)
            if addfail == 0:
                if allData["addressbook"]["status"] is not None:
                    statetest = int(allData["addressbook"]["status"])
                else:
                    statetest = 0
                _LOGGER.debug(f" Statetest {statetest}")
                
                if statetest in [1,2,3]:
                    allData["online"] = True
                    if TimeSlice==0:
                        # do this at startup and then every 15 minutes
                        addfail = await getOABatterySettings(hass, allData, deviceSN, apiKey) # read in battery settings, not sure what to do with these yet, poll every 5/15/30/60 mins ?
                        await asyncio.sleep(1)  # delay for OpenAPI between api calls
                    # main real time data fetch, followed by reports
                    getError = await getRaw(hass, headersData, allData, apiKey, deviceSN, deviceID)
                    if getError == False:
                        if TimeSlice==0 or LastHour != hournow: # do this at startup, every 15 minutes and on the hour change
                            LastHour = hournow # update the hour the last report was run
                            await asyncio.sleep(1)  # delay for OpenAPI between api calls
                            getError = await getReport(hass, headersData, allData, apiKey, deviceSN, deviceID)
                            if getError == False:
                                if TimeSlice==0:
                                    # do this at startup, then every 15 minutes
                                    await asyncio.sleep(1)  # delay for OpenAPI between api calls
                                    getError = await getReportDailyGeneration(hass, headersData, allData, apiKey, deviceSN, deviceID)
                                    if getError == True:
                                        allData["online"] = False
                                        TimeSlice=RETRY_NEXT_SLOT # failed to get data so try again in 1 minute
                                        _LOGGER.debug("getReportDailyGeneration False")
                            else:
                                allData["online"] = False
                                TimeSlice=RETRY_NEXT_SLOT # failed to get data so try again in 1 minute
                                _LOGGER.debug("getReport False")

                    else:
                        allData["online"] = False
                        TimeSlice=RETRY_NEXT_SLOT # failed to get data so try again in 1 minute
                        _LOGGER.debug("getRaw False")

                if allData["online"] == False:
                    _LOGGER.debug("Inverter off-line or cloud timeout, not fetching additional data")
            else:
                TimeSlice=RETRY_NEXT_SLOT # failed to get data so try again in a minute
                
        # actions here are every minute
        if TimeSlice==15:
            TimeSlice=RETRY_NEXT_SLOT # reset timeslice and start again from 0
        _LOGGER.debug(f"Auxilliary TimeSlice {TimeSlice}")

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
        FoxESSBatMinSoC(coordinator, name, deviceID),
        FoxESSBatMinSoConGrid(coordinator, name, deviceID),
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
        FoxESSEnergyLoad(coordinator, name, deviceID),
        FoxESSResidualEnergy(coordinator, name, deviceID)
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

        result = {
            'token': token,
            'lang': lang,
            'timestamp': str(timestamp),
            'Content-Type': 'application/json',
            'signature': self.md5c(text=signature),
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/117.0.0.0 Safari/537.36'
        }
        return result

    @staticmethod
    def md5c(text="", _type="lower"):
        res = hashlib.md5(text.encode(encoding='UTF-8')).hexdigest()
        if _type.__eq__("lower"):
            return res
        else:
            return res.upper()


async def authAndgetToken(hass, username, hashedPassword):

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
                   "Connection": "close",
                    "X-Requested-With": "XMLHttpRequest"}

    restAuth = RestData(hass, METHOD_POST, _ENDPOINT_AUTH, DEFAULT_ENCODING,  None,
                        headersAuth, None, payloadAuth, DEFAULT_VERIFY_SSL, SSLCipherList.PYTHON_DEFAULT)

    await restAuth.async_update()

    if restAuth.data is None:
        _LOGGER.error("Unable to login to FoxESS Cloud - No data received")
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


async def getAddresbook(hass, headersData, allData, username, hashedPassword, deviceID):
    restAddressBook = RestData(hass, METHOD_GET, _ENDPOINT_ADDRESSBOOK +
                               deviceID, DEFAULT_ENCODING,  None, headersData, None, None, DEFAULT_VERIFY_SSL, SSLCipherList.PYTHON_DEFAULT)
    await restAddressBook.async_update()

    if restAddressBook.data is None:
        _LOGGER.error("Unable to get Addressbook data from FoxESS Cloud")
        return 0
    else:
        response = json.loads(restAddressBook.data)
        if response["errno"] is not None and (response["errno"] == 41809 or response["errno"] == 41808):
                global token
                token = None
                _LOGGER.debug(f"Token has expired, re-authenticating {token}")
                return 0
        else:
            _LOGGER.debug(
                "FoxESS Addressbook data fetched correctly "+restAddressBook.data)
            #allData['addressbook'] = response
            return 1

async def getOADeviceDetail(hass, allData, deviceSN, apiKey):
    global hasBattery

    path = "/op/v0/device/detail"
    headerData = GetAuth().get_signature(token=apiKey, path=path)

    path = _ENDPOINT_OA_DOMAIN + _ENDPOINT_OA_DEVICE_DETAIL
    _LOGGER.debug("OADevice Detail fetch " + path + deviceSN)

    restOADeviceDetail = RestData(hass, METHOD_GET, path + deviceSN, DEFAULT_ENCODING,  None, headerData, None, None, DEFAULT_VERIFY_SSL, SSLCipherList.PYTHON_DEFAULT)
    await restOADeviceDetail.async_update()

    if restOADeviceDetail.data is None or restOADeviceDetail.data == '':
        _LOGGER.error("Unable to get OA Device Detail from FoxESS Cloud")
        return True
    else:
        response = json.loads(restOADeviceDetail.data)
        if response["errno"] == 0 and response["msg"] == 'success' :
            _LOGGER.debug(f"OA Device Detail Good Response: {response['result']}")
            result = response['result']
            allData['addressbook'] = result
            # manually poke this in as on the old cloud it was called plantname, need to keep in line with old entity name
            plantName = result['stationName']
            allData['addressbook']['plantName'] = plantName
            testBattery = result['hasBattery']
            if testBattery:
                _LOGGER.debug(f"OA Device Detail System has Battery: {hasBattery}")
                hasBattery = True
            else:
                _LOGGER.debug(f"OA Device Detail System has No Battery: {hasBattery}")
                hasBattery = False
            return False
        else:
            _LOGGER.error(f"OA Device Detail Bad Response: {response}")
            return True

async def getOABatterySettings(hass, allData, deviceSN, apiKey):

    path = "/op/v0/device/battery/soc/get"
    headerData = GetAuth().get_signature(token=apiKey, path=path)

    path = _ENDPOINT_OA_DOMAIN + _ENDPOINT_OA_BATTERY_SETTINGS

    if hasBattery:
        # only make this call if device detail reports battery fitted
        _LOGGER.debug("OABattery Settings fetch " + path + deviceSN)
        restOABatterySettings = RestData(hass, METHOD_GET, path + deviceSN, DEFAULT_ENCODING,  None, headerData, None, None, DEFAULT_VERIFY_SSL, SSLCipherList.PYTHON_DEFAULT)
        await restOABatterySettings.async_update()

        if restOABatterySettings.data is None:
            _LOGGER.error("Unable to get OA Battery Settings from FoxESS Cloud")
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


async def getReport(hass, headersData, allData, apiKey, deviceSN, deviceID):

    path = _ENDPOINT_OA_REPORT
    headerData = GetAuth().get_signature(token=apiKey, path=path)

    path = _ENDPOINT_OA_DOMAIN + _ENDPOINT_OA_REPORT
    _LOGGER.debug("OA Report fetch " + path )

    now = datetime.now()

    reportData = '{"sn":"'+deviceSN+'","year":'+now.strftime("%Y")+',"month":'+now.strftime("%_m")+',"dimension":"month","variables":["feedin","generation","gridConsumption","chargeEnergyToTal","dischargeEnergyToTal","loads"]}'
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
        SSLCipherList.PYTHON_DEFAULT
    )

    await restOAReport.async_update()

    if restOAReport.data is None or restOAReport.data == '':
        _LOGGER.error("Unable to get OA Report from FoxESS Cloud")
        # try the old cloud
        if TRY_OLD_CLOUD_API:
            now = datetime.now()
            reportData = '{"deviceID":"'+deviceID+'","reportType":"day","variables":["feedin","generation","gridConsumption","chargeEnergyToTal","dischargeEnergyToTal","loads"],"queryDate":{"year":'+now.strftime("%Y")+',"month":'+now.strftime("%_m")+',"day":'+now.strftime("%_d")+'}}'
            _LOGGER.debug("FoxESS Report data query: " +   reportData)

            restReport = RestData(
                hass, 
                METHOD_POST, 
                _ENDPOINT_REPORT,
                DEFAULT_ENCODING, 
                None, 
                headersData, 
                None, 
                reportData, 
                DEFAULT_VERIFY_SSL, 
                SSLCipherList.PYTHON_DEFAULT
            )

            await restReport.async_update()

            if restReport.data is None:
                _LOGGER.error("Unable to get Report data from FoxESS Cloud")
                return True
            else:
                _LOGGER.debug("FoxESS Report data fetched correctly " + restReport.data[:350] + " ... ")
                for item in json.loads(restReport.data)['result']:
                    variableName = item['variable']
                    allData['report'][variableName] = None
                    # Daily reports break down the data hour by hour for the whole day even if we're only
                    # partially through, so sum the values together to get our daily total so far...
                    cumulative_total = 0
                    for dataItem in item['data']:
                        cumulative_total += dataItem['value']
                    _LOGGER.debug(f"Old Report Variable: {variableName}, Total: {cumulative_total}")
                    allData['report'][variableName] = round(cumulative_total,3)
                return False
    else:
        # Openapi responded so process data
        response = json.loads(restOAReport.data)
        if response["errno"] == 0 and response["msg"] == 'success' :
            _LOGGER.debug(f"OA Report Data fetched OK: {response} "+ restOAReport.data[:350])
            result = json.loads(restOAReport.data)['result']
            today = int(now.strftime("%_d")) # need today as an integer to locate in the monthly report index
            for item in result: 
                variableName = item['variable']
                # Daily reports break down the data hour by month for each day
                # so locate the current days index and use that as the sum
                index = 1
                cumulative_total = 0
                for dataItem in item['values']:
                    if today==index: # we're only interested in the total for today
                        cumulative_total = dataItem
                        break
                    index+=1
                    #cumulative_total += dataItem
                allData['report'][variableName] = round(cumulative_total,3)
                _LOGGER.debug(f"OA Report Variable: {variableName}, Total: {cumulative_total}")
            return False
        else:
            _LOGGER.error(f"OA Report Bad Response: {response} "+ restOAReport.data)


async def getReportDailyGeneration(hass, headersData, allData, apiKey, deviceSN, deviceID):
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
        SSLCipherList.PYTHON_DEFAULT
    )

    await restOAgen.async_update()

    if restOAgen.data is None or restOAgen.data == '':
        _LOGGER.error("Unable to get OA Daily Generation Report from FoxESS Cloud")
        return True
    else:
        response = json.loads(restOAgen.data)
        if response["errno"] == 0 and response["msg"] == 'success' :
            _LOGGER.debug("OA Daily Generation Report Data fetched OK Response:"+ restOAgen.data[:500])

            parsed = json.loads(restOAgen.data)["result"]
            allData["reportDailyGeneration"]["value"] = parsed['today']
            _LOGGER.debug(f"OA Daily Generation Report data: {parsed} and todays value {parsed['today']} ")
            return False
        else:
            _LOGGER.error(f"OA Daily Generation Report Bad Response: {response} "+ restOAgen.data)

        # try the old cloud
        if TRY_OLD_CLOUD_API:

            generationData = ('{"deviceID":"' + deviceID + '","reportType": "month",' + '"variables": ["generation"],' + '"queryDate": {' + '"year":' + now.strftime("%Y") + ',"month":' + now.strftime("%_m") + ',"day":' + now.strftime("%_d") + ',"hour":' + now.strftime("%_H") + "}}")

            _LOGGER.debug("FoxESS Report Daily Generation query: " +   generationData)

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
                return True
            else:
                _LOGGER.debug("FoxESS daily generation data fetched correctly " + restGeneration.data)
                parsed = json.loads(restGeneration.data)["result"]
                _LOGGER.debug(f"Foxess DG Data fetched OK Response: { parsed[0]['data'][int(now.strftime('%d')) - 1] }")
                allData["reportDailyGeneration"] = parsed[0]["data"][int(now.strftime("%d")) - 1]
                return False


async def getRaw(hass, headersData, allData, apiKey, deviceSN, deviceID):

    path = _ENDPOINT_OA_DEVICE_VARIABLES
    headerData = GetAuth().get_signature(token=apiKey, path=path)

    # "deviceSN" used for OpenAPI and it only fetches the real time data
    rawData =  '{"sn":"'+deviceSN+'","variables":["ambientTemperation", \
                                    "batChargePower","batCurrent","batDischargePower","batTemperature","batVolt", \
                                    "boostTemperation", "chargeTemperature", "dspTemperature", \
                                    "epsCurrentR","epsCurrentS","epsCurrentT","epsPower","epsPowerR","epsPowerS","epsPowerT","epsVoltR","epsVoltS","epsVoltT", \
                                    "feedinPower", "generationPower","gridConsumptionPower", \
                                    "input","invBatCurrent","invBatPower","invBatVolt","invTemperation", \
                                    "loadsPower","loadsPowerR","loadsPowerS","loadsPowerT", \
                                    "meterPower","meterPower2","meterPowerR","meterPowerS","meterPowerT","PowerFactor", \
                                    "pv1Current","pv1Power","pv1Volt","pv2Current","pv2Power","pv2Volt", \
                                    "pv3Current","pv3Power","pv3Volt","pv4Current","pv4Power","pv4Volt","pvPower", \
                                    "RCurrent","ReactivePower","RFreq","RPower","RVolt", \
                                    "SCurrent","SFreq","SoC","SPower","SVolt", \
                                    "TCurrent","TFreq","TPower","TVolt", \
                                    "ResidualEnergy", "todayYield"] }'

    _LOGGER.debug("getRaw OA request:" +rawData) 

    path = _ENDPOINT_OA_DOMAIN + _ENDPOINT_OA_DEVICE_VARIABLES
    _LOGGER.debug("OADevice Variables fetch " + path )

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
        SSLCipherList.PYTHON_DEFAULT
    )

    await restOADeviceVariables.async_update()

    if restOADeviceVariables.data is None or restOADeviceVariables.data == '':
        _LOGGER.error("Unable to get OA Device Variables from FoxESS Cloud")
        # try the old cloud ?
        if TRY_OLD_CLOUD_API:
            now = datetime.now() - timedelta(minutes=6)
            _LOGGER.error("GetRaw Fallback to old cloud interface")

            rawData =  '{"deviceID":"'+deviceID+'","variables":["ambientTemperation", \
                                    "batChargePower","batCurrent","batDischargePower","batTemperature","batVolt", \
                                    "boostTemperation", "chargeTemperature","dspTemperature", \
                                    "epsCurrentR","epsCurrentS","epsCurrentT","epsPower","epsPowerR","epsPowerS","epsPowerT","epsVoltR","epsVoltS","epsVoltT", \
                                    "feedinPower","generationPower","gridConsumptionPower", \
                                    "input","invBatCurrent","invBatPower","invBatVolt","invTemperation", \
                                    "loadsPower","loadsPowerR","loadsPowerS","loadsPowerT", \
                                    "meterPower","meterPower2","meterPowerR","meterPowerS","meterPowerT","PowerFactor", \
                                    "pv1Current","pv1Power","pv1Volt","pv2Current","pv2Power","pv2Volt", \
                                    "pv3Current","pv3Power","pv3Volt","pv4Current","pv4Power","pv4Volt","pvPower", \
                                    "RCurrent","ReactivePower","RFreq","RPower","RVolt", \
                                    "SCurrent","SFreq","SoC","SPower","SVolt", \
                                    "TCurrent","TFreq","TPower","TVolt"], \
                                    "timespan":"hour","beginDate":{"year":'+now.strftime("%Y")+',"month":'+now.strftime("%_m")+',"day":'+now.strftime("%_d")+',"hour":'+now.strftime("%_H")+',"minute":0,"second":0}}'

            _LOGGER.debug("getRaw request:" +rawData) 

            restRaw = RestData(
                hass, 
                METHOD_POST, 
                _ENDPOINT_RAW,
                DEFAULT_ENCODING, 
                None, 
                headersData, 
                None, 
                rawData, 
                DEFAULT_VERIFY_SSL, 
                SSLCipherList.PYTHON_DEFAULT
            )

            await restRaw.async_update()

            if restRaw.data is None:
                _LOGGER.error("Unable to get Raw data from FoxESS Cloud")
                return True
            else:
                _LOGGER.debug("FoxESS Raw data fetched correctly " + restRaw.data[:1200] + " ... " ) 
                # allData['raw'] = {}
                for item in json.loads(restRaw.data)['result']:
                    variableName = item['variable']
                    # If data is a non-empty list, pop the last value off the list, otherwise return the previously found value
                    if item["data"]:
                        allData['raw'][variableName] = item["data"].pop().get("value",None)
                        _LOGGER.debug( f"Variable: {variableName} being set to {allData['raw'][variableName]}" )
                # These don't exist in old cloud api set them to 0
                allData['raw']['ResidualEnergy'] = 0
                allData['raw']['todayYield'] = 0
                allData["battery"]["minSoc"] = 0
                allData["battery"]["minSocOnGrid"] = 0
        return False
    else:
        # Openapi responded correctly
        response = json.loads(restOADeviceVariables.data)
        if response["errno"] == 0 and response["msg"] == 'success' :
            test = json.loads(restOADeviceVariables.data)['result']
            result = test[0].get('datas')
            _LOGGER.debug(f"OA Device Variables Good Response: {result}")
            # allData['raw'] = {}
            for item in result: # json.loads(result): # restOADeviceVariables.data)['result']:
                variableName = item['variable']
                # If value exists 
                if item.get('value') is not None:
                    variableValue = item['value']
                else:
                    variableValue = 0
                    _LOGGER.debug( f"Variable {variableName} no value, set to zero" )

                allData['raw'][variableName] = variableValue
                _LOGGER.debug( f"Variable: {variableName} being set to {allData['raw'][variableName]}" )
            return False
        else:
            _LOGGER.error(f"OA Device Variables Bad Response: {response}")
            return True
            
#        if response["errno"] is not None and (response["errno"] == 41809 or response["errno"] == 41808):
#                _LOGGER.debug("Error getting OA Device Variables " +restOADeviceVariables.data)

class FoxESSGenerationPower(CoordinatorEntity, SensorEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

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
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

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
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

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
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

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
    _attr_native_unit_of_measurement = UnitOfFrequency.HERTZ

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

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
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

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
    _attr_native_unit_of_measurement = UnitOfFrequency.HERTZ

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

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
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

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
    _attr_native_unit_of_measurement = UnitOfFrequency.HERTZ

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
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

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
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

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
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

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
                energygenerated = 0
            else:
                energygenerated = self.coordinator.data["reportDailyGeneration"]["value"]
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
        if self.coordinator.data["online"]:
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
        if self.coordinator.data["online"]:
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
        if self.coordinator.data["online"]:
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
        if self.coordinator.data["online"]:
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
        if self.coordinator.data["online"]:
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
        if self.coordinator.data["online"]:
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
            return self.coordinator.data["battery"]["minSocOnGrid"]
        return  None

    @property
    def icon(self):
        return icon_for_battery_level(battery_level=self.native_value, charging=None)


class FoxESSBatTemp(CoordinatorEntity, SensorEntity):

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

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
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

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
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

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
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

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
            re = self.coordinator.data["raw"]["ResidualEnergy"]
            if re > 0:
                re = re / 100
            else:
                re = 0
            return re
        return None
