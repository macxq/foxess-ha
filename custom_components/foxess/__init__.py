from __future__ import annotations

import logging
import json
import hashlib

from datetime import timedelta
from datetime import datetime
import voluptuous as vol

from .const import (
    DOMAIN,
    ATT_COORDINATOR,
    ATT_NAME,
    ATT_DEVICEID
)



from homeassistant.core import  HomeAssistant
from homeassistant.config_entries import ConfigType

from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers import config_validation as cv, discovery


from homeassistant.components.rest.data import RestData

from random_user_agent.user_agent import UserAgent
from random_user_agent.params import SoftwareName, OperatingSystem
from homeassistant.components.sensor import (PLATFORM_SCHEMA)

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_NAME
)

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

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

CONF_DEVICEID = "devices"
DEFAULT_NAME = "FoxESS"
DEFAULT_VERIFY_SSL = True
tokens = {}

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)



CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        cv.string :{
            vol.Required(CONF_PASSWORD): cv.string,
            vol.Required(CONF_DEVICEID): vol.Schema({
                cv.string: cv.string
            }, extra=vol.ALLOW_EXTRA)
            
        }
    }
    , extra=vol.ALLOW_EXTRA),
}, extra=vol.ALLOW_EXTRA)

PLATFORMS: list[str] = ["sensor","number"]

async def async_setup(hass: HomeAssistant, hass_config: ConfigType) -> bool:
    """Set up a skeleton component."""
    # States are in the format DOMAIN.OBJECT_ID.
    _LOGGER.debug("Starting FoxESS Clound integration")

    config =  hass_config[DOMAIN]

    _LOGGER.debug(config)

    hass.data[DOMAIN]  = []

    # for entry in config:
    #     name = entry[CONF_NAME]
    #     username = entry[CONF_USERNAME]
    #     password = entry[CONF_PASSWORD]
    #     deviceID = entry[CONF_DEVICEID]

    #     hashedPassword = hashlib.md5(password.encode()).hexdigest()

    #     async def async_update_data(name=name,username=username,hashedPassword=hashedPassword,deviceID=deviceID):
    #         _LOGGER.debug(f"{name} - Updating data from https://www.foxesscloud.com/")

    #         allData = {
    #             "report":{},
    #             "raw":{},
    #             "online":False
    #         }

    #         global tokens
    #         if name not in tokens:
    #             _LOGGER.debug(f"Token for {name} is empty, authenticating for the firts time")
    #             tokens[name] = await authAndgetToken(hass, username, hashedPassword, name)

    #         user_agent = user_agent_rotator.get_random_user_agent()
    #         headersData = {"token": tokens[name], 
    #                     "User-Agent": user_agent,
    #                     "Accept": "application/json, text/plain, */*",
    #                     "lang": "en",
    #                     "sec-ch-ua-platform": "macOS",
    #                     "Sec-Fetch-Site": "same-origin",
    #                     "Sec-Fetch-Mode": "cors",
    #                     "Sec-Fetch-Dest": "empty",
    #                     "Referer": "https://www.foxesscloud.com/bus/device/inverterDetail?id=xyz&flowType=1&status=1&hasPV=true&hasBattery=false",
    #                     "Accept-Language":"en-US;q=0.9,en;q=0.8,de;q=0.7,nl;q=0.6",
    #                     "Connection": "keep-alive",
    #                     "X-Requested-With": "XMLHttpRequest"}

    #         await getAddresbook(hass, headersData, allData, deviceID, username, hashedPassword,name,0)

    #         status = int(allData["addressbook"]["result"]["status"]) 
    #         allData["inverterStatus"] = status
            
    #         if status!= 0:
    #             await getRaw(hass, headersData, allData, deviceID, name)
    #             await getReport(hass, headersData, allData, deviceID, name)
    #         else:
    #             _LOGGER.debug("Inverter is off-line, not fetching addictional data")

    #         _LOGGER.debug(f"🟢 All Data colected for {name} {allData}")

    #         return allData

    #     coordinator = DataUpdateCoordinator(
    #         hass,
    #         _LOGGER,
    #         # Name of the data. For logging purposes.
    #         name=name,
    #         update_method=async_update_data,
    #         # Polling interval. Will only be polled if there are subscribers.
    #         update_interval=SCAN_INTERVAL,
    #     )

    #     await coordinator.async_refresh()

    #     if not coordinator.last_update_success:
    #         _LOGGER.error(
    #             f"{name} Cloud initializaction failed, fix error and restar ha")
    #         return False


    #     hass.data[DOMAIN].append({ 
    #         ATT_COORDINATOR: coordinator,
    #         ATT_NAME: name,
    #         ATT_DEVICEID: deviceID
    #     })

    # for platform in PLATFORMS:
    #     await discovery.async_load_platform(hass, platform, DOMAIN, "", config)

    # Return boolean to indicate that initialization was successfully.
    return True


async def authAndgetToken(hass, username, hashedPassword, name):

    payloadAuth = {"user": username, "password": hashedPassword}
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

    restAuth = RestData(hass, METHOD_POST, _ENDPOINT_AUTH, None,
                        headersAuth, None, payloadAuth, DEFAULT_VERIFY_SSL)

    await restAuth.async_update()

    if restAuth.data is None:
        _LOGGER.error(f"{name} - Unable to login to FoxESS Cloud - No data recived")
        return False

    response = json.loads(restAuth.data)

    if response["result"] is None:
        if response["errno"] is not None and response["errno"] == 41807:
            raise UpdateFailed(
                f"{name} - Unable to login to FoxESS Cloud - bad username or password! {restAuth.data}")
        else:
            raise UpdateFailed(
                f"{name} - Error communicating with API: {restAuth.data}")
    else:
        _LOGGER.debug(f"{name} - Login succesfull" + restAuth.data)

    token = response["result"]["token"]
    return token


async def getAddresbook(hass, headersData, allData, deviceID,username, hashedPassword,name,tokenRefreshRetrys):
    restAddressBook = RestData(hass, METHOD_GET, _ENDPOINT_ADDRESSBOOK +
                               deviceID, None, headersData, None, None, DEFAULT_VERIFY_SSL)
    await restAddressBook.async_update()

    if restAddressBook.data is None:
        _LOGGER.error(f"{name} - Unable to get Addressbook data from FoxESS Cloud")
        return False
    else:
        response = json.loads(restAddressBook.data)
        if response["errno"] is not None and response["errno"] == 41809:
                if tokenRefreshRetrys > 2:
                    raise UpdateFailed(f"{name} - Unable to refresh token in {tokenRefreshRetrys} retries")
                global tokens
                _LOGGER.debug(f"{name} - Token has expierd, re-authenticating {tokenRefreshRetrys}")
                tokens[name] = await authAndgetToken(hass, username, hashedPassword)
                getErnings(hass, headersData, allData, deviceID, username, hashedPassword,tokenRefreshRetrys+1)
        else:
            _LOGGER.debug(
                f"{name} - FoxESS Addressbook data fetched correcly "+restAddressBook.data)
            allData['addressbook'] = response


async def getReport(hass, headersData, allData, deviceID, name):
    now = datetime.now()


    reportData = '{"deviceID":"'+deviceID+'","reportType":"month","variables":["feedin","generation","gridConsumption","chargeEnergyToTal","dischargeEnergyToTal","loads"],"queryDate":{"year":'+now.strftime(
        "%Y")+',"month":'+now.strftime("%_m")+'}}'

    restReport = RestData(hass, METHOD_POST, _ENDPOINT_REPORT,
                          None, headersData, None, reportData, DEFAULT_VERIFY_SSL)

    await restReport.async_update()

    if restReport.data is None:
        _LOGGER.error(f"{name} - Unable to get Report data from FoxESS Cloud")
        return False
    else:
        _LOGGER.debug(f"{name} - FoxESS Report data fetched correcly " +
                      restReport.data[:150] + " ... ")

        for item in json.loads(restReport.data)['result']:
            variableName = item['variable']
            allData['report'][variableName] = None
            # Daily reports break down the data hour by hour for the whole day
            # even if we're only partially through, so sum the values together
            # to get our daily total so far...
            # EDIT 👆 this aproche dose not work, sum returns the underestimated values, there is some inconsistency on foxesscloud suite
            for dataItem in item['data']:
                if dataItem['index'] == int(now.strftime("%d")):
                    allData['report'][variableName] = dataItem['value']
            


async def getRaw(hass, headersData, allData, deviceID, name):
    now = datetime.now()

    rawData = '{"deviceID":"'+deviceID+'","variables":["generationPower","feedinPower","batChargePower","batDischargePower","gridConsumptionPower","loadsPower","SoC","batTemperature","pv1Power","pv2Power","pv3Power","pv4Power"],"timespan":"day","beginDate":{"year":'+now.strftime(
        "%Y")+',"month":'+now.strftime("%_m")+',"day":'+now.strftime("%_d")+',"hour":'+now.strftime("%_H")+'}}'

    restRaw = RestData(hass, METHOD_POST, _ENDPOINT_RAW,
                       None, headersData, None, rawData, DEFAULT_VERIFY_SSL)
    await restRaw.async_update()

    if restRaw.data is None:
        _LOGGER.error(f"{name} - Unable to get Raw data from FoxESS Cloud")
        return False
    else:
        _LOGGER.debug(f"{name} - FoxESS Raw data fetched correcly " +
                      restRaw.data[:150] + " ... ")
        allData['raw'] = {}

        for item in json.loads(restRaw.data)['result']:
            variableName = item['variable']
            # If data is a non-empty list, pop the last value off the list, otherwise return the previously found value
            if item["data"]:
                allData['raw'][variableName] = item["data"].pop().get("value",None)
