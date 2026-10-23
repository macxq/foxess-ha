from __future__ import annotations

from collections import namedtuple
from datetime import timedelta
from datetime import datetime
from dateutil import parser
import enum
import time
import logging
import json
import hashlib
import asyncio
import voluptuous as vol

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
    PLATFORM_SCHEMA,
    SensorEntity,
)

from homeassistant.const import (
    ATTR_DATE,
    ATTR_TIME,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_NAME,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfEnergy,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfFrequency,
    UnitOfReactivePower,
    PERCENTAGE,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util.ssl import SSLCipherList
from homeassistant.helpers.icon import icon_for_battery_level
from homeassistant.util import dt as dt_util
import homeassistant.helpers.config_validation as cv

from .api import FoxESSApiClient, GetAuth, waitforAPI
from .const import (
    ATTR_BATTERYLIST,
    ATTR_DEVICE_SN,
    ATTR_DEVICE_TYPE,
    ATTR_LASTCLOUDSYNC,
    ATTR_MANAGER,
    ATTR_MASTER,
    ATTR_MODULESN,
    ATTR_PLANTNAME,
    ATTR_SLAVE,
    BATTERY_LEVELS,
    CONF_APIKEY,
    CONF_DEVICEID,
    CONF_DEVICESN,
    CONF_ENERGY_GENERATED_SANITY,
    CONF_EVO,
    CONF_EXTPV,
    CONF_GET_VARIABLES,
    CONF_NAME,
    CONF_REDUCE_API_CALLS,
    CONF_SYSTEM_ID,
    CONF_V1_API,
    CONF_XTZONE,
    DEFAULT_ENERGY_GENERATED_SANITY,
    DEFAULT_NAME,
    DEFAULT_REDUCE_API_CALLS,
    DEFAULT_TIMEOUT,
    DOMAIN,
    FetchResult,
    RETRY_IN_5_MINS,
    RETRY_IN_10_MINS,
    RETRY_NEXT_SLOT,
    SCAN_INTERVAL,
    SCAN_MINUTES,
    YAML_CONFIGS_KEY,
    _AUTH_ERRNO,
    _ENDPOINT_OA_BATTERY_SETTINGS,
    _ENDPOINT_OA_DAILY_GENERATION,
    _ENDPOINT_OA_DEVICE_DETAIL,
    _ENDPOINT_OA_DEVICE_DETAIL_V1,
    _ENDPOINT_OA_DEVICE_LIST,
    _ENDPOINT_OA_DEVICE_VARIABLES,
    _ENDPOINT_OA_DEVICE_VARIABLES_V1,
    _ENDPOINT_OA_DOMAIN,
    _ENDPOINT_OA_REPORT,
)

_LOGGER = logging.getLogger(__name__)

METHOD_POST = "POST"
METHOD_GET = "GET"
DEFAULT_ENCODING = "UTF-8"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_VERIFY_SSL = False

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Required(CONF_APIKEY): cv.string,
        vol.Required(CONF_DEVICESN): cv.string,
        vol.Required(CONF_DEVICEID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_EXTPV): cv.boolean,
        vol.Optional(CONF_XTZONE): cv.boolean,
        vol.Optional(CONF_GET_VARIABLES): cv.boolean,
        vol.Optional(CONF_V1_API): cv.boolean,
        vol.Optional(CONF_EVO): cv.boolean,
        vol.Optional(
            CONF_ENERGY_GENERATED_SANITY, default=DEFAULT_ENERGY_GENERATED_SANITY
        ): cv.positive_float,
        vol.Optional(
            CONF_REDUCE_API_CALLS, default=DEFAULT_REDUCE_API_CALLS
        ): cv.boolean,
    }
)

token = None
timeslice = {}
last_api = 0


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up FoxESS sensors from a config entry."""
    config = {**config_entry.data, **config_entry.options}
    await _async_setup_foxess(
        hass,
        config,
        async_add_entities,
        config_entry,
    )


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the FoxESS sensor from YAML."""
    device_sn = config.get(CONF_DEVICESN)
    if not device_sn:
        return

    # Advertise YAML config so the config flow can detect conflicts and
    # preserve the original deviceID (which may differ from deviceSN).
    yaml_configs = hass.data.setdefault(YAML_CONFIGS_KEY, {})
    yaml_configs[device_sn] = {
        CONF_DEVICEID: config.get(CONF_DEVICEID),
        CONF_NAME: config.get(CONF_NAME, DEFAULT_NAME),
    }

    # Check if a ConfigEntry already exists for this deviceSN
    current_entries = hass.config_entries.async_entries(DOMAIN)
    if any(
        entry.unique_id == device_sn or entry.data.get(CONF_DEVICESN) == device_sn
        for entry in current_entries
    ):
        _LOGGER.debug(
            "FoxESS device %s is already configured in UI, skipping YAML setup",
            device_sn,
        )
        return

    # Trigger automatic import into UI
    _LOGGER.info(
        "Importing FoxESS device %s from configuration.yaml into UI", device_sn
    )
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=config,
        )
    )


async def _async_setup_foxess(hass, config, async_add_entities, config_entry=None):
    """Shared setup logic for platform and config entry."""
    global LastHour, timeslice, last_api, RestrictGetVar, xtzone, V1_Api, Evo
    Evo = False
    name = config.get(CONF_NAME)
    deviceID = config.get(CONF_DEVICEID)
    devicesn = config.get(CONF_DEVICESN)
    apiKey = config.get(CONF_APIKEY)
    ExtPV = config.get(CONF_EXTPV)
    xtzone = config.get(CONF_XTZONE)
    RestrictGetVar = config.get(CONF_GET_VARIABLES)
    V1_Api = config.get(CONF_V1_API)
    Evo = config.get(CONF_EVO)
    energyGeneratedSanityCheck = float(
        config.get(CONF_ENERGY_GENERATED_SANITY, DEFAULT_ENERGY_GENERATED_SANITY)
        or DEFAULT_ENERGY_GENERATED_SANITY
    )
    reduce_api_calls = bool(
        config.get(CONF_REDUCE_API_CALLS, DEFAULT_REDUCE_API_CALLS)
    )
    _LOGGER.debug("API Key: %s", f"...{apiKey[-4:]}" if apiKey else "(unset)")
    _LOGGER.debug("Device SN: %s", devicesn)
    _LOGGER.debug("Device ID: %s", deviceID)
    _LOGGER.debug("FoxESS Scan Interval: %s minutes", SCAN_MINUTES)
    _LOGGER.debug("Cross Time Zone: %s", xtzone)
    _LOGGER.debug("Restrict Variables: %s", RestrictGetVar)
    _LOGGER.debug("Extended PV: %s", ExtPV)
    _LOGGER.debug("v1 Api Calls: %s", V1_Api)
    _LOGGER.debug("EVO: %s", Evo)
    _LOGGER.debug("Energy Sanity Check: %s kWh", energyGeneratedSanityCheck)
    _LOGGER.debug("Reduced API Calls Mode: %s", reduce_api_calls)
    if V1_Api is not False:
        V1_Api = True
        _LOGGER.debug("v1 Api Calls Enabled")
    else:
        _LOGGER.warning("v1 Api Calls Disabled, using v0")
    if ExtPV is not True:
        ExtPV = False
        _LOGGER.debug("Extended PV Disabled")
    else:
        _LOGGER.warning("Extended PV 1-18 strings enabled")
    if RestrictGetVar is not True:
        RestrictGetVar = False
        _LOGGER.debug("Get Variables is full variable mode")
    else:
        _LOGGER.warning("Get Variables is in restricted mode")
    timeslice[devicesn] = RETRY_NEXT_SLOT
    last_api = 0
    LastHour = 0
    daily_gen_interval = 60 if reduce_api_calls else 15
    daily_gen_retry_interval = 10 if reduce_api_calls else 5
    daily_gen_timer = 0
    allData = {
        "report": {},
        "reportDailyGeneration": {},
        "raw": {},
        "battery": {},
        "addressbook": {},
        "online": False,
    }
    allData["addressbook"]["hasBattery"] = False  # assume no battery is fitted for now
    allData["addressbook"]["status"] = "3"  # assume inverter is off-line for now

    async def async_update_data():
        _LOGGER.debug("Updating data from https://www.foxesscloud.com/")
        global token, timeslice, LastHour
        hournow = datetime.now().strftime("%H")  # update hour now
        _LOGGER.debug("Time now: %s, last %s", hournow, LastHour)
        tslice = timeslice[devicesn] + 1 # increment current device time slice
        timeslice[devicesn] = tslice

        main_poll_due = (tslice % 10 == 0) if reduce_api_calls else (tslice % 5 == 0)
        detail_due = (tslice % 30 == 0) if reduce_api_calls else (tslice % 15 == 0)
        report_due = (tslice == 0) if reduce_api_calls else (tslice % 15 == 0)
        retry_slot = RETRY_IN_10_MINS if reduce_api_calls else RETRY_IN_5_MINS

        # Independent timer for daily generation report (#324)
        nonlocal daily_gen_timer
        daily_gen_timer -= 1
        if daily_gen_timer <= 0:
            _LOGGER.debug(
                "Fetching OA Daily Generation Report on independent schedule for SN: %s",
                devicesn,
            )
            try:
                gen_error = await getReportDailyGeneration(
                    hass, allData, apiKey, devicesn
                )
                if gen_error is FetchResult.AUTH_FAILED:
                    if config_entry is not None:
                        raise ConfigEntryAuthFailed("FoxESS API key rejected")
                    _LOGGER.error(
                        "FoxESS API authentication failed in daily generation. "
                        "Update your apiKey in configuration.yaml and restart."
                    )
                elif gen_error:
                    _LOGGER.debug(
                        "getReportDailyGeneration failed for SN %s, retry in %s minutes",
                        devicesn,
                        daily_gen_retry_interval,
                    )
                    daily_gen_timer = daily_gen_retry_interval
                else:
                    daily_gen_timer = daily_gen_interval
            except ConfigEntryAuthFailed:
                raise
            except Exception as err:
                _LOGGER.warning(
                    "Unexpected error fetching daily generation for SN %s: %s, retry in %s minutes",
                    devicesn,
                    err,
                    daily_gen_retry_interval,
                )
                daily_gen_timer = daily_gen_retry_interval

        if main_poll_due:
            _LOGGER.debug("Main Poll, interval: %s, %s", devicesn, timeslice[devicesn])
            # try the openapi see if we get a response
            geterror = FetchResult.OK
            if detail_due:
                # get device detail at startup, then periodically to save api calls
                if Evo:
                    # Evo not currently in device detail, use list and fill partial blanks
                    geterror = await getOADeviceList(hass, allData, devicesn, apiKey)
                else:
                    geterror = await getOADeviceDetail(hass, allData, devicesn, apiKey)
                if geterror is FetchResult.AUTH_FAILED:
                    if config_entry is not None:
                        raise ConfigEntryAuthFailed("FoxESS API key rejected")
                    _LOGGER.error(
                        "FoxESS API authentication failed. "
                        "Update your apiKey in configuration.yaml and restart."
                    )
                    return allData
                await asyncio.sleep(1)  # OpenAPI demand
            if not geterror:
                if allData["addressbook"]["status"] is not None:
                    statetest = int(allData["addressbook"]["status"])
                    if statetest in [3]:
                        allData["raw"]["runningState"] = "164"  # off-grid
                else:
                    statetest = 0
                _LOGGER.debug(" Statetest %s", statetest)
                if statetest in [1, 2]:
                    allData["online"] = True
                    if tslice == 0:
                        # read in battery settings if fitted at startup, then every 60 mins
                        await getOABatterySettings(hass, allData, devicesn, apiKey)
                        await asyncio.sleep(1)  # OpenAPI demand
                    # main real time data fetch, followed by reports
                    geterror = await getRaw(
                        hass, allData, apiKey, devicesn, reduce_api_calls=reduce_api_calls
                    )
                    if geterror is FetchResult.AUTH_FAILED:
                        if config_entry is not None:
                            raise ConfigEntryAuthFailed("FoxESS API key rejected")
                        _LOGGER.error(
                            "FoxESS API authentication failed. "
                            "Update your apiKey in configuration.yaml and restart."
                        )
                        return allData
                    if not geterror:
                        if report_due:  # do at startup and periodically (every 15m or 60m)
                            await asyncio.sleep(1)  # OpenAPI demand limit
                            geterror = await getReport(hass, allData, apiKey, devicesn)
                            if geterror:
                                _LOGGER.debug("getReport False")
                                geterror = FetchResult.OK
                                allData["online"] = False
                                tslice = retry_slot  # retry in 5 or 10 minutes
                    else:
                        _LOGGER.debug("get variables failed")
                        if statetest == 2:
                            # The inverter is in alarm, don't check every minute
                            _LOGGER.debug(
                                "Inverter in alarm, slowing retry response for SN: %s",
                                devicesn,
                            )
                            allData["online"] = False
                            tslice = retry_slot  # retry in 5 or 10 minutes
                        else:
                            if geterror is FetchResult.DNS_TIMEOUT:
                                _LOGGER.warning("Fox Cloud - DNS fail, retry in 1 minute")
                                # retry in 1 minute
                                if tslice != 0:
                                    tslice = (tslice-1)
                                else:
                                    tslice = RETRY_NEXT_SLOT
                            else:
                                # The get variables api call failed, leave it 5 or 10 minutes
                                _LOGGER.debug("slowing retry response for SN: %s", devicesn)
                                allData["online"] = False
                                tslice = retry_slot  # retry in 5 or 10 minutes
                        geterror = FetchResult.OK
                else:
                    if statetest == 3:
                        # The inverter is off-line, no raw data polling, don't update entities
                        # retry device detail call periodically until it comes back on-line
                        allData["online"] = False
                        tslice = retry_slot  # retry in 5 or 10 minutes
                        _LOGGER.debug("Inverter off-line for SN: %s", devicesn)

                if not allData["online"]:
                    if not geterror:
                        _LOGGER.warning("%s Inverter is off-line, waiting to retry", name)
                    else:
                        _LOGGER.warning("%s Cloud timeout, retry in 1 minute", name)
            else:
                _LOGGER.warning("%s Cloud timeout on Device Detail, retry in 1 minute.", name)

            if geterror is not FetchResult.OK:
                allData["online"] = False
                if tslice != 0:
                    tslice = tslice-1
                    # failed to get specific detail so retry slot in 1 minute
                else:
                    tslice = RETRY_NEXT_SLOT  # failed to get full data, try again in 1 minute

        # actions here are every minute
        if tslice >= 59:
            tslice = RETRY_NEXT_SLOT  # reset timeslot, ready for full data fetch at 0
        _LOGGER.debug("Auxilliary timeslice %s, %s", devicesn, tslice)

        if LastHour != hournow:
            LastHour = hournow  # update the hour the last poll was run

        timeslice[devicesn] = tslice

        _LOGGER.debug(allData)

        return allData

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DEFAULT_NAME,
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
        config_entry=config_entry,
    )
    coordinator.devicesn = devicesn
    coordinator.inverter_name = name
    coordinator.deviceID = deviceID

    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        _LOGGER.error(
            "FoxESS Cloud initialisation failed, Fatal Error - correct error and restart Home Assistant"
        )
        return False

    async_add_entities(
        [
            FoxESSCurrent(
                coordinator, name, deviceID, "PV1 Current", "pv1-current", "pv1Current"
            ),
            FoxESSPower(
                coordinator, name, deviceID, "PV1 Power", "pv1-power", "pv1Power"
            ),
            FoxESSVolt(coordinator, name, deviceID, "PV1 Volt", "pv1-volt", "pv1Volt"),
            FoxESSCurrent(
                coordinator, name, deviceID, "PV2 Current", "pv2-current", "pv2Current"
            ),
            FoxESSPower(
                coordinator, name, deviceID, "PV2 Power", "pv2-power", "pv2Power"
            ),
            FoxESSVolt(coordinator, name, deviceID, "PV2 Volt", "pv2-volt", "pv2Volt"),
            FoxESSCurrent(
                coordinator, name, deviceID, "PV3 Current", "pv3-current", "pv3Current"
            ),
            FoxESSPower(
                coordinator, name, deviceID, "PV3 Power", "pv3-power", "pv3Power"
            ),
            FoxESSVolt(coordinator, name, deviceID, "PV3 Volt", "pv3-volt", "pv3Volt"),
            FoxESSCurrent(
                coordinator, name, deviceID, "PV4 Current", "pv4-current", "pv4Current"
            ),
            FoxESSPower(
                coordinator, name, deviceID, "PV4 Power", "pv4-power", "pv4Power"
            ),
            FoxESSVolt(coordinator, name, deviceID, "PV4 Volt", "pv4-volt", "pv4Volt"),
            FoxESSCurrent(
                coordinator, name, deviceID, "PV5 Current", "pv5-current", "pv5Current"
            ),
            FoxESSPower(
                coordinator, name, deviceID, "PV5 Power", "pv5-power", "pv5Power"
            ),
            FoxESSVolt(coordinator, name, deviceID, "PV5 Volt", "pv5-volt", "pv5Volt"),
            FoxESSCurrent(
                coordinator, name, deviceID, "PV6 Current", "pv6-current", "pv6Current"
            ),
            FoxESSPower(
                coordinator, name, deviceID, "PV6 Power", "pv6-power", "pv6Power"
            ),
            FoxESSVolt(coordinator, name, deviceID, "PV6 Volt", "pv6-volt", "pv6Volt"),
            FoxESSPower(coordinator, name, deviceID, "PV Power", "pv-power", "pvPower"),
            FoxESSCurrent(
                coordinator, name, deviceID, "R Current", "r-current", "RCurrent"
            ),
            FoxESSFreq(coordinator, name, deviceID, "R Freq", "r-freq", "RFreq"),
            FoxESSPower(coordinator, name, deviceID, "R Power", "r-power", "RPower"),
            FoxESSPowerString(
                coordinator,
                name,
                deviceID,
                "Meter2 Power",
                "meter2-power",
                "meterPower2",
            ),
            FoxESSVolt(coordinator, name, deviceID, "R Volt", "r-volt", "RVolt"),
            FoxESSCurrent(
                coordinator, name, deviceID, "S Current", "s-current", "SCurrent"
            ),
            FoxESSFreq(coordinator, name, deviceID, "S Freq", "s-freq", "SFreq"),
            FoxESSPower(coordinator, name, deviceID, "S Power", "s-power", "SPower"),
            FoxESSVolt(coordinator, name, deviceID, "S Volt", "s-volt", "SVolt"),
            FoxESSCurrent(
                coordinator, name, deviceID, "T Current", "t-current", "TCurrent"
            ),
            FoxESSFreq(coordinator, name, deviceID, "T Freq", "t-freq", "TFreq"),
            FoxESSPower(coordinator, name, deviceID, "T Power", "t-power", "TPower"),
            FoxESSVolt(coordinator, name, deviceID, "T Volt", "t-volt", "TVolt"),
            FoxESSReactivePower(coordinator, name, deviceID),
            FoxESSPowerFactor(coordinator, name, deviceID),
            FoxESSTemp(
                coordinator,
                name,
                deviceID,
                "Bat Temperature",
                "bat-temperature",
                "batTemperature",
            ),
            FoxESSTemp(
                coordinator,
                name,
                deviceID,
                "Bat Temperature2",
                "bat-temperature2",
                "batTemperature_2",
            ),
            FoxESSTemp(
                coordinator,
                name,
                deviceID,
                "Ambient Temperature",
                "ambient-temperature",
                "ambientTemperation",
            ),
            FoxESSTemp(
                coordinator,
                name,
                deviceID,
                "Boost Temperature",
                "boost-temperature",
                "boostTemperation",
            ),
            FoxESSTemp(
                coordinator,
                name,
                deviceID,
                "Inv Temperature",
                "inv-temperature",
                "invTemperation",
            ),
            FoxESSBatSoC(coordinator, name, deviceID, "Bat SoC", "bat-soc", "SoC"),
            FoxESSBatSoC(coordinator, name, deviceID, "Bat SoC1", "bat-soc1", "SoC_1"),
            FoxESSBatSoC(coordinator, name, deviceID, "Bat SoC2", "bat-soc2", "SoC_2"),
            FoxESSBatSoC(coordinator, name, deviceID, "Bat SoH", "bat-soh", "SOH"),
            FoxESSPower(
                coordinator,
                name,
                deviceID,
                "Inverter Bat Power",
                "inv-Bat-Power",
                "invBatPower",
            ),
            FoxESSPower(
                coordinator,
                name,
                deviceID,
                "Inverter Bat Power2",
                "inv-Bat-Power2",
                "invBatPower_2",
            ),
            FoxESSBatMinSoC(coordinator, name, deviceID),
            FoxESSBatMinSoConGrid(coordinator, name, deviceID),
            FoxESSSolarPower(coordinator, name, deviceID),
            FoxESSEnergyThroughput(coordinator, name, deviceID),
            FoxESSEnergySolar(
                coordinator,
                name,
                deviceID,
                max_value=energyGeneratedSanityCheck,
            ),
            FoxESSInverter(coordinator, name, deviceID),
            FoxESSPowerString(
                coordinator,
                name,
                deviceID,
                "Generation Power",
                "-generation-power",
                "generationPower",
            ),
            FoxESSPowerString(
                coordinator,
                name,
                deviceID,
                "Grid Consumption Power",
                "grid-consumption-power",
                "gridConsumptionPower",
            ),
            FoxESSPowerString(
                coordinator,
                name,
                deviceID,
                "FeedIn Power",
                "feedIn-power",
                "feedinPower",
            ),
            FoxESSPowerString(
                coordinator,
                name,
                deviceID,
                "Bat Discharge Power",
                "bat-discharge-power",
                "batDischargePower",
            ),
            FoxESSPowerString(
                coordinator,
                name,
                deviceID,
                "Bat Charge Power",
                "bat-charge-power",
                "batChargePower",
            ),
            FoxESSPowerString(
                coordinator, name, deviceID, "Load Power", "load-power", "loadsPower"
            ),
            FoxESSEnergyGenerated(
                coordinator,
                name,
                deviceID,
                "Energy Generated",
                "energy-generated",
                "value",
                max_value=energyGeneratedSanityCheck,
            ),
            FoxESSEnergyGenerated(
                coordinator,
                name,
                deviceID,
                "Energy Generated Month",
                "energy-generated-month",
                "month",
            ),
            FoxESSEnergyGenerated(
                coordinator,
                name,
                deviceID,
                "Energy Generated Cumulative",
                "energy-generated-cumulative",
                "cumulative",
            ),
            FoxESSEnergyGridConsumption(coordinator, name, deviceID),
            FoxESSEnergyFeedin(coordinator, name, deviceID),
            FoxESSEnergyBatCharge(coordinator, name, deviceID),
            FoxESSEnergyBatDischarge(coordinator, name, deviceID),
            FoxESSEnergyLoad(coordinator, name, deviceID),
            FoxESSPVEnergyTotal(coordinator, name, deviceID),
            FoxESSResidualEnergy(coordinator, name, deviceID),
            FoxESSResponseTime(coordinator, name, deviceID),
            FoxESSMaxBatChargeCurrent(coordinator, name, deviceID),
            FoxESSMaxBatDischargeCurrent(coordinator, name, deviceID),
            FoxESSRunningState(
                coordinator,
                name,
                deviceID,
                "Running State",
                "running-state",
                "runningState",
            ),
        ]
    )

    if ExtPV:
        async_add_entities(
            [
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV7 Current",
                    "pv7-current",
                    "pv7Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV7 Power", "pv7-power", "pv7Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV7 Volt", "pv7-volt", "pv7Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV8 Current",
                    "pv8-current",
                    "pv8Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV8 Power", "pv8-power", "pv8Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV8 Volt", "pv8-volt", "pv8Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV9 Current",
                    "pv9-current",
                    "pv9Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV9 Power", "pv9-power", "pv9Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV9 Volt", "pv9-volt", "pv9Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV10 Current",
                    "pv10-current",
                    "pv10Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV10 Power", "pv10-power", "pv10Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV10 Volt", "pv10-volt", "pv10Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV11 Current",
                    "pv11-current",
                    "pv11Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV11 Power", "pv11-power", "pv11Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV11 Volt", "pv11-volt", "pv11Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV12 Current",
                    "pv12-current",
                    "pv12Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV12 Power", "pv12-power", "pv12Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV12 Volt", "pv12-volt", "pv12Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV13 Current",
                    "pv13-current",
                    "pv13Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV13 Power", "pv13-power", "pv13Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV13 Volt", "pv13-volt", "pv13Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV14 Current",
                    "pv14-current",
                    "pv14Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV14 Power", "pv14-power", "pv14Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV14 Volt", "pv14-volt", "pv14Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV15 Current",
                    "pv15-current",
                    "pv15Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV15 Power", "pv15-power", "pv15Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV15 Volt", "pv15-volt", "pv15Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV16 Current",
                    "pv16-current",
                    "pv16Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV16 Power", "pv16-power", "pv16Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV16 Volt", "pv16-volt", "pv16Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV17 Current",
                    "pv17-current",
                    "pv17Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV17 Power", "pv17-power", "pv17Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV17 Volt", "pv17-volt", "pv17Volt"
                ),
                FoxESSCurrent(
                    coordinator,
                    name,
                    deviceID,
                    "PV18 Current",
                    "pv18-current",
                    "pv18Current",
                ),
                FoxESSPower(
                    coordinator, name, deviceID, "PV18 Power", "pv18-power", "pv18Power"
                ),
                FoxESSVolt(
                    coordinator, name, deviceID, "PV18 Volt", "pv18-volt", "pv18Volt"
                ),
            ]
        )





async def getOADeviceDetail(hass, allData, devicesn, apiKey):
    client = FoxESSApiClient(hass)
    res, response, elapsed_ms = await client.async_get_device_detail(
        devicesn, apiKey, v1_api=V1_Api
    )
    if res is not FetchResult.OK or not response:
        _LOGGER.debug("Unable to get OA Device Detail from FoxESS Cloud")
        return res

    if response.get("errno") == 0 and (
        response.get("msg") in ("success", "Operation successful")
    ):
        allData["raw"]["ResponseTime"] = max(0, elapsed_ms)
        _LOGGER.debug("OA Device Detail Good Response: %s", response.get("result"))
        result = response["result"]
        allData["addressbook"] = result
        # manually poke this in as on the old cloud it was called plantname, need to keep in line with old entity name
        plantName = result.get("stationName")
        allData["addressbook"]["plantName"] = plantName
        testBattery = result.get("hasBattery")
        if testBattery:
            _LOGGER.debug("OA Device Detail System has Battery: %s", testBattery)
        else:
            _LOGGER.debug("OA Device Detail System has No Battery: %s", testBattery)
            allData["addressbook"][ATTR_BATTERYLIST] = "No Battery"
        return FetchResult.OK
    else:
        _LOGGER.error("OA Device Detail Bad Response: %s", response)
        return (
            FetchResult.AUTH_FAILED
            if response.get("errno") in _AUTH_ERRNO
            else FetchResult.ERROR
        )


async def getOADeviceList(hass, allData, devicesn, apiKey):
    client = FoxESSApiClient(hass)
    res, response, elapsed_ms = await client.async_get_device_list(
        apiKey, page=1, page_size=10
    )
    if res is not FetchResult.OK or not response:
        _LOGGER.debug("Unable to get OA Device List from FoxESS Cloud")
        return res

    if response.get("errno") == 0 and (
        response.get("msg") in ("success", "Operation successful")
    ):
        allData["raw"]["ResponseTime"] = max(0, elapsed_ms)
        _LOGGER.debug("OA Device List Good Response: %s", response.get("result"))
        result_data = response.get("result", {}).get("data", [])
        item = {}
        for d in result_data:
            if d.get("deviceSN") == devicesn:
                item = d
                break
        if not item and result_data:
            item = result_data[0]
        allData["addressbook"] = item
        plantName = item.get("stationName")
        allData["addressbook"]["plantName"] = plantName
        allData["addressbook"]["masterVersion"] = "not provided"
        allData["addressbook"]["managerVersion"] = "not provided"
        allData["addressbook"]["slaveVersion"] = "not provided"
        allData["addressbook"]["batteryList"] = "not provided"
        testBattery = item.get("hasBattery")
        if testBattery:
            _LOGGER.debug("OA Device List System has Battery: %s", testBattery)
        else:
            _LOGGER.debug("OA Device List System has No Battery: %s", testBattery)
            allData["addressbook"][ATTR_BATTERYLIST] = "No Battery"
        return FetchResult.OK
    else:
        _LOGGER.error("OA Device List Bad Response: %s", response)
        return (
            FetchResult.AUTH_FAILED
            if response.get("errno") in _AUTH_ERRNO
            else FetchResult.ERROR
        )


async def getOABatterySettings(hass, allData, devicesn, apiKey):
    if "hasBattery" not in allData.get("addressbook", {}):
        hasBattery = False
    else:
        hasBattery = allData["addressbook"]["hasBattery"]

    if hasBattery:
        # only make this call if device detail reports battery fitted
        _LOGGER.debug("OABattery Settings fetch for SN: %s", devicesn)
        client = FoxESSApiClient(hass)
        res, response, elapsed_ms = await client.async_get_battery_settings(devicesn, apiKey)
        if res is not FetchResult.OK or not response:
            _LOGGER.debug("Unable to get OA Battery Settings from FoxESS Cloud")
            return res

        if response.get("errno") == 0 and (
            response.get("msg") in ("success", "Operation successful")
        ):
            _LOGGER.debug(
                "OA Battery Settings Good Response: %s", response.get("result")
            )
            result = response.get("result", {})
            minSoc = result.get("minSoc")
            minSocOnGrid = result.get("minSocOnGrid")
            allData["battery"]["minSoc"] = minSoc
            allData["battery"]["minSocOnGrid"] = minSocOnGrid
            _LOGGER.debug(
                "OA Battery Settings read MinSoc: %s, MinSocOnGrid: %s",
                minSoc,
                minSocOnGrid,
            )
            return FetchResult.OK
        else:
            _LOGGER.error("OA Battery Settings Bad Response: %s", response)
            return (
                FetchResult.AUTH_FAILED
                if response.get("errno") in _AUTH_ERRNO
                else FetchResult.ERROR
            )
    else:
        # device detail reports no battery fitted so reset these variables to show unknown
        allData["battery"]["minSoc"] = None
        allData["battery"]["minSocOnGrid"] = None
        return FetchResult.OK


async def getReport(hass, allData, apiKey, devicesn):
    client = FoxESSApiClient(hass)
    _LOGGER.debug("OA Report fetch for SN %s", devicesn)

    now = datetime.now()
    variables = [
        "feedin",
        "generation",
        "gridConsumption",
        "chargeEnergyToTal",
        "dischargeEnergyToTal",
        "loads",
        "PVEnergyTotal",
    ]

    res, response, elapsed_ms = await client.async_get_report(
        devicesn=devicesn,
        token=apiKey,
        year=now.year,
        month=now.month,
        variables=variables,
    )

    if res is not FetchResult.OK or not response:
        _LOGGER.debug("Unable to get OA Report from FoxESS Cloud")
        return res

    if response.get("errno") == 0 and (
        response.get("msg") in ("success", "Operation successful")
    ):
        _LOGGER.debug("OA Report Data fetched OK: %s", response)
        result = response.get("result", [])
        today = now.day
        for item in result:
            variableName = item.get("variable")
            if not variableName:
                continue
            index = 1
            cumulative_total = 0
            for dataItem in item.get("values", []):
                if today == index:
                    if dataItem is not None:
                        cumulative_total = dataItem
                    else:
                        _LOGGER.debug("Report month fetch, None received")
                    break
                index += 1
            allData["report"][variableName] = round(cumulative_total, 3)
            _LOGGER.debug(
                "OA Report Variable: %s, Total: %s", variableName, cumulative_total
            )
        return FetchResult.OK
    else:
        _LOGGER.debug("OA Report Bad Response: %s", response)
        return (
            FetchResult.AUTH_FAILED
            if response.get("errno") in _AUTH_ERRNO
            else FetchResult.ERROR
        )


async def getReportDailyGeneration(hass, allData, apiKey, devicesn):
    client = FoxESSApiClient(hass)
    _LOGGER.debug("getReportDailyGeneration fetch for SN %s", devicesn)

    res, response, elapsed_ms = await client.async_get_daily_generation(devicesn, apiKey)
    if res is not FetchResult.OK or not response:
        _LOGGER.debug("Unable to get OA Daily Generation Report from FoxESS Cloud")
        return res

    if response.get("errno") == 0 and (
        response.get("msg") in ("success", "Operation successful")
    ):
        _LOGGER.debug("OA Daily Generation Report Data fetched OK Response: %s", response)

        result_data = response.get("result")
        if not isinstance(result_data, dict):
            _LOGGER.debug(
                "OA Daily Generation Report result is not a dict: %s", result_data
            )
            return FetchResult.ERROR

        parsed = result_data
        if "today" in parsed and parsed["today"] is not None:
            allData["reportDailyGeneration"]["value"] = parsed["today"]
            _LOGGER.debug(
                "OA Daily Generation Report data: todays value %s ", parsed["today"]
            )
        else:
            _LOGGER.debug(
                "OA Daily Generation Report data, today has no value in %s, retaining previous: %s",
                parsed,
                allData["reportDailyGeneration"].get("value"),
            )

        if "month" in parsed and parsed["month"] is not None:
            allData["reportDailyGeneration"]["month"] = parsed["month"]
            _LOGGER.debug(
                "OA Daily Generation Report data: month value %s ", parsed["month"]
            )
        else:
            _LOGGER.debug(
                "OA Daily Generation Report data, month has no value in %s, retaining previous: %s",
                parsed,
                allData["reportDailyGeneration"].get("month"),
            )

        if "cumulative" in parsed and parsed["cumulative"] is not None:
            allData["reportDailyGeneration"]["cumulative"] = parsed["cumulative"]
            _LOGGER.debug(
                "OA Daily Generation Report data: cumulative value %s ",
                parsed["cumulative"],
            )
        else:
            _LOGGER.debug(
                "OA Daily Generation Report data, cumulative has no value in %s, retaining previous: %s",
                parsed,
                allData["reportDailyGeneration"].get("cumulative"),
            )

        return FetchResult.OK
    else:
        _LOGGER.debug("OA Daily Generation Report Bad Response: %s", response)
        return (
            FetchResult.AUTH_FAILED
            if response.get("errno") in _AUTH_ERRNO
            else FetchResult.ERROR
        )


async def getRaw(hass, allData, apiKey, devicesn, reduce_api_calls: bool = False):
    client = FoxESSApiClient(hass)
    raw_vars = None
    if RestrictGetVar:
        _LOGGER.debug("Getting Device Variable in restricted mode")
        raw_vars = [
            "ambientTemperation",
            "batChargePower",
            "batCurrent",
            "batCurrent_1",
            "batCurrent_2",
            "batDischargePower",
            "batTemperature",
            "batTemperature_1",
            "batTemperature_2",
            "batVolt",
            "batVolt_1",
            "batVolt_2",
            "boostTemperation",
            "chargeTemperature",
            "dspTemperature",
            "epsCurrentR",
            "epsCurrentS",
            "epsCurrentT",
            "epsPower",
            "epsPowerR",
            "epsPowerS",
            "epsPowerT",
            "epsVoltR",
            "epsVoltS",
            "epsVoltT",
            "feedinPower",
            "generationPower",
            "gridConsumptionPower",
            "input",
            "invBatCurrent",
            "invBatPower",
            "invBatVolt",
            "invTemperation",
            "loadsPower",
            "loadsPowerR",
            "loadsPowerS",
            "loadsPowerT",
            "meterPower",
            "meterPower2",
            "meterPowerR",
            "meterPowerS",
            "meterPowerT",
            "PowerFactor",
            "pv1Current",
            "pv1Power",
            "pv1Volt",
            "pv2Current",
            "pv2Power",
            "pv2Volt",
            "pv3Current",
            "pv3Power",
            "pv3Volt",
            "pv4Current",
            "pv4Power",
            "pv4Volt",
            "pvPower",
            "RCurrent",
            "ReactivePower",
            "RFreq",
            "RPower",
            "RVolt",
            "SCurrent",
            "SFreq",
            "SoC",
            "SPower",
            "SVolt",
            "TCurrent",
            "TFreq",
            "TPower",
            "TVolt",
            "SoC_1",
            "Soc_2",
            "ResidualEnergy",
            "energyThroughput",
            "runningState",
            "currentFaultCount",
        ]

    res, response, elapsed_ms = await client.async_get_real_data(
        devicesn=devicesn,
        token=apiKey,
        variables=raw_vars,
        v1_api=V1_Api,
    )

    if res is not FetchResult.OK or not response:
        _LOGGER.debug("Unable to get OA Variables from FoxESS Cloud")
        return res

    if response.get("errno") == 0 and (
        response.get("msg") in ("success", "Operation successful")
    ):
        allData["raw"]["ResponseTime"] = max(0, elapsed_ms)
        test = response.get("result")
        if not test or not isinstance(test, list):
            _LOGGER.debug("OA Variables empty result in response")
            return FetchResult.ERROR

        timercv = test[0].get("time")
        try:
            # format is "2025-02-21 16:38:29 GMT+0000" strptime is useless at international dates, so work out the offset
            _LOGGER.debug("OA Variables time: %s ", timercv)
            tzoffsetsign = timercv[23:24]
            tzoffsethr = int(timercv[24:26])
            tzoffsetmin = int(timercv[26:28])
            tzfull = str(timercv[23:28])
            _LOGGER.debug(
                "OA Variables tzoffsign: %s, hr: %s, min: %s, full: %s",
                tzoffsetsign,
                tzoffsethr,
                tzoffsetmin,
                tzfull,
            )
            if tzoffsetsign in ["+"]:
                tzoffset = (tzoffsethr * 3600 + tzoffsetmin * 60) * 1
            else:
                tzoffset = (tzoffsethr * 3600 + tzoffsetmin * 60) * -1
            tsrcv = (parser.parse(timercv, ignoretz=True)).timestamp()
            zulu = datetime.now().astimezone().strftime("%z")
            if zulu != tzfull:
                if xtzone:
                    _LOGGER.debug(
                        "OA Variables tsrcv applying offset: %s, offset: %s, zulu: %s",
                        tsrcv,
                        tzoffset,
                        zulu,
                    )
                    tsrcv = tsrcv - tzoffset
            else:
                _LOGGER.debug(
                    "OA Variables tsrcv is local: %s, zulu: %s, offset: %s ",
                    tsrcv,
                    zulu,
                    tzoffset,
                )
        except:
            tsrcv = 0
        age = 0
        max_age = 661 if reduce_api_calls else 361
        if tsrcv != 0:
            testd = datetime.now()
            tsnow = round(time.time())
            age = round(tsnow - tsrcv)
            _LOGGER.debug(
                "OA Variables time: %s vs %s timestamps r:%s now:%s, age: %s",
                timercv,
                testd,
                tsrcv,
                tsnow,
                age,
            )
            if age > max_age:
                _LOGGER.debug(
                    "OA Variables invalid age: %s vs %s timestamps r:%s now:%s, age: %s (max: %s)",
                    timercv,
                    testd,
                    tsrcv,
                    tsnow,
                    age,
                    max_age,
                )

        result = test[0].get("datas", [])
        _LOGGER.debug("OA Variables Good Response: %s", result)
        for item in result:
            variableName = item.get("variable")
            if not variableName:
                continue
            # If value exists
            if item.get("value") is not None:
                variableValue = item["value"]
            else:
                variableValue = 0
                _LOGGER.debug("Variable %s no value, set to zero", variableName)
            # fix for various battery and scale items
            if variableName == "SoC_1":
                variableName = "SoC_1"  # do nothing for the moment, future release might align this correctly to use SoC
            elif variableName == "batTemperature_1":
                variableName = "batTemperature"  # use entity for single battery systems
            elif variableName == "invBatPower_1":
                variableName = "invBatPower"  # use entity for single battery systems
            elif variableName == "ResidualEnergy":
                # OpenAPI may return:
                # - hundredths of kWh with unit '0.01kWh' (e.g. 1933.0 for 19.33 kWh) -> divide by 100
                # - tenths of kWh with unit '0.1kWh' (e.g. 235.0 for 23.5 kWh) -> divide by 10
                # - directly in kWh with unit '0.01kWh', 'kWh', '1.0kWh', or None (e.g. 20.2 or 23.5)
                if variableValue is not None:
                    scale = item.get("unit")
                    if scale == "0.1kWh":
                        if variableValue > 100.0:
                            variableValue = round(variableValue / 10.0, 2)
                            _LOGGER.debug("OA Variables ResidualEnergy Scale (0.1kWh): /10 to %s", variableValue)
                        else:
                            variableValue = round(float(variableValue), 2)
                    elif variableValue > 100.0:
                        variableValue = round(variableValue / 100.0, 2)
                        _LOGGER.debug("OA Variables ResidualEnergy Scale (>100): /100 to %s", variableValue)
                    else:
                        variableValue = round(float(variableValue), 2)
                        _LOGGER.debug("OA Variables ResidualEnergy: %s (scale: %s)", variableValue, scale)

            allData["raw"][variableName] = variableValue
            _LOGGER.debug(
                "Var: %s, SN: %s set to %s",
                variableName,
                devicesn,
                allData["raw"][variableName],
            )

            if variableName == "runningState" and (
                "hasBattery" in allData["addressbook"]
            ):
                hasBat = allData["addressbook"]["hasBattery"]
                if not hasBat:
                    # solar only inverter
                    _LOGGER.debug(
                        "TestState: %s, hasBat: %s online: %s",
                        variableValue,
                        hasBat,
                        allData["online"],
                    )
                    if variableValue is not None:
                        if variableValue == "161" or variableValue == "162":
                            # waiting and solar only so set off-line flag
                            if age < max_age:
                                _LOGGER.debug(
                                    "Waiting but data less than %s minutes old - allow sample, RunningState: %s, hasBat: %s online: %s",
                                    round(max_age / 60),
                                    variableValue,
                                    hasBat,
                                    allData["online"],
                                )
                            else:
                                allData["online"] = False
                                _LOGGER.debug(
                                    "Waiting so set off-line state, TestState: %s, hasBat: %s online: %s",
                                    variableValue,
                                    hasBat,
                                    allData["online"],
                                )
                        elif variableValue == "163" and not allData["online"]:
                            # on-grid but showing off-line wait for it to be set on-line by OADeviceDetail
                            # allData["online"] = False
                            _LOGGER.debug(
                                "Inverter on-grid but off-line wait for OADevice to confirm, TestState: %s, hasBat: %s",
                                variableValue,
                                hasBat,
                            )

        return FetchResult.OK
    else:
        _LOGGER.debug("OA Device Variables Bad Response: %s", response)
        return (
            FetchResult.AUTH_FAILED
            if response.get("errno") in _AUTH_ERRNO
            else FetchResult.ERROR
        )


class FoxESSEntity(CoordinatorEntity, SensorEntity):
    """Base class for FoxESS sensor entities with DeviceInfo."""

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information to group all entities under one device."""
        devicesn = getattr(self.coordinator, "devicesn", None) or getattr(
            self, "_deviceID", None
        )
        if not devicesn:
            return None
        inverter_name = getattr(self.coordinator, "inverter_name", None) or devicesn
        data = getattr(self.coordinator, "data", {}) or {}
        addressbook = data.get("addressbook", {}) if isinstance(data, dict) else {}
        return DeviceInfo(
            identifiers={(DOMAIN, devicesn)},
            name=inverter_name,
            manufacturer="FoxESS",
            model=addressbook.get(ATTR_DEVICE_TYPE),
            sw_version=addressbook.get(ATTR_MASTER),
            serial_number=devicesn,
            configuration_url=_ENDPOINT_OA_DOMAIN,
        )


class FoxESSPowerString(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug("Initiating Entity - %s", self._nameValue)
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
                _LOGGER.debug("%s None", self._keyValue)
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSCurrent(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug("Initiating Entity - %s", self._nameValue)
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
                _LOGGER.debug("%s None", self._keyValue)
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSFreq(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.FREQUENCY
    _attr_native_unit_of_measurement = UnitOfFrequency.HERTZ

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug("Initiating Entity - %s", self._nameValue)
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
                _LOGGER.debug("%s None", self._keyValue)
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSPower(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug("Initiating Entity - %s", self._nameValue)
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
                _LOGGER.debug("%s None", self._keyValue)
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSVolt(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug("Initiating Entity - %s", self._nameValue)
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
                _LOGGER.debug("%s None", self._keyValue)
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSReactivePower(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.REACTIVE_POWER
    _attr_native_unit_of_measurement = UnitOfReactivePower.VOLT_AMPERE_REACTIVE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Reactive Power")
        self._attr_name = name + " - Reactive Power"
        self._attr_unique_id = deviceID + "reactive-power"
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


class FoxESSPowerFactor(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER_FACTOR
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Power Factor")
        self._attr_name = name + " - Power Factor"
        self._attr_unique_id = deviceID + "power-factor"
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


class FoxESSEnergyGenerated(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        coordinator,
        name,
        deviceID,
        nameValue,
        uniqueValue,
        keyValue,
        max_value=None,
    ):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        self._max_value = max_value
        _LOGGER.debug("Initiating Entity - %s", self._nameValue)
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
        if self._keyValue not in self.coordinator.data.get("reportDailyGeneration", {}):
            _LOGGER.debug("%s None", self._keyValue)
            return None

        val = self.coordinator.data["reportDailyGeneration"][self._keyValue]
        if val is None:
            return None

        if val == 0:
            energygenerated = 0
        else:
            if val > 0:
                energygenerated = round(val, 3)
            else:
                energygenerated = 0

        if (
            self._max_value is not None
            and energygenerated is not None
            and energygenerated > self._max_value
        ):
            _LOGGER.warning(
                "%s value %s exceeds sanity check threshold %s kWh, ignoring",
                self._nameValue,
                energygenerated,
                self._max_value,
            )
            return None

        return energygenerated


class FoxESSEnergyThroughput(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Energy Throughput")
        self._attr_name = name + " - Energy Throughput"
        self._attr_unique_id = deviceID + "energy-throughput"
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
                    energygenerated = round(energygenerated, 3)
                else:
                    energygenerated = 0
            return energygenerated
        return None


class FoxESSEnergyGridConsumption(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Grid Consumption")
        self._attr_name = name + " - Grid Consumption"
        self._attr_unique_id = deviceID + "grid-consumption"
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


class FoxESSEnergyFeedin(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - FeedIn")
        self._attr_name = name + " - FeedIn"
        self._attr_unique_id = deviceID + "feedIn"
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


class FoxESSEnergyBatCharge(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat Charge")
        self._attr_name = name + " - Bat Charge"
        self._attr_unique_id = deviceID + "bat-charge"
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

class FoxESSMaxBatChargeCurrent(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Max Bat Charge Current")
        self._attr_name = name + " - Max Bat Charge Current"
        self._attr_unique_id = deviceID + "max-bat-charge-charge"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if "maxChargeCurrent" not in self.coordinator.data["raw"]:
            _LOGGER.debug("report maxChargeCurrent None")
        else:
            if self.coordinator.data["raw"]["maxChargeCurrent"] == 0:
                charge = 0
            else:
                charge = self.coordinator.data["raw"]["maxChargeCurrent"]
            return charge
        return None

class FoxESSMaxBatDischargeCurrent(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Max Bat Discharge Current")
        self._attr_name = name + " - Max Bat Discharge Current"
        self._attr_unique_id = deviceID + "max-bat-discharge-charge"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if "maxDischargeCurrent" not in self.coordinator.data["raw"]:
            _LOGGER.debug("report maxDischargeCurrent None")
        else:
            if self.coordinator.data["raw"]["maxDischargeCurrent"] == 0:
                charge = 0
            else:
                charge = self.coordinator.data["raw"]["maxDischargeCurrent"]
            return charge
        return None


class FoxESSEnergyBatDischarge(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat Discharge")
        self._attr_name = name + " - Bat Discharge"
        self._attr_unique_id = deviceID + "bat-discharge"
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
                energydischarge = self.coordinator.data["report"][
                    "dischargeEnergyToTal"
                ]
            return energydischarge
        return None


class FoxESSEnergyLoad(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Load")
        self._attr_name = name + " - Load"
        self._attr_unique_id = deviceID + "load"
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
            # round
            return round(energyload, 3)
        return None


class FoxESSPVEnergyTotal(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - PV Energy Total")
        self._attr_name = name + " - PVEnergyTotal"
        self._attr_unique_id = deviceID + "PVEnergyTotal"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> str | None:
        if "PVEnergyTotal" not in self.coordinator.data["report"]:
            _LOGGER.debug("report PVEnergyTotal None")
        else:
            if self.coordinator.data["report"]["PVEnergyTotal"] == 0:
                energyload = 0
            else:
                energyload = self.coordinator.data["report"]["PVEnergyTotal"]
            # round
            return round(energyload, 3)
        return None


class FoxESSInverter(FoxESSEntity):
    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Inverter")
        self._attr_name = name + " - Inverter"
        self._attr_unique_id = deviceID + "Inverter"
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
                ATTR_MASTER,
                ATTR_MANAGER,
                ATTR_SLAVE,
                ATTR_BATTERYLIST,
                ATTR_LASTCLOUDSYNC,
            ],
        )

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data or {}
        addressbook = data.get("addressbook", {}) if isinstance(data, dict) else {}
        status = addressbook.get("status")
        try:
            status_int = int(status) if status is not None else None
        except (ValueError, TypeError):
            status_int = None

        is_online = bool(data.get("online", False))

        if is_online or (not is_online and status_int in [1, 2, 3]):
            if status_int == 1:
                return "on-line"
            elif status_int == 2:
                return "in-alarm"
            elif status_int == 3:
                return "off-line"
            else:
                _LOGGER.debug("addressbook status None or unknown: %s", status)
        return None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        addressbook = data.get("addressbook", {}) if isinstance(data, dict) else {}
        if not addressbook or ATTR_DEVICE_SN not in addressbook:
            _LOGGER.debug("addressbook device detail not yet available")
            return None
        return {
            ATTR_DEVICE_SN: addressbook.get(ATTR_DEVICE_SN),
            ATTR_PLANTNAME: addressbook.get(ATTR_PLANTNAME),
            ATTR_MODULESN: addressbook.get(ATTR_MODULESN),
            ATTR_DEVICE_TYPE: addressbook.get(ATTR_DEVICE_TYPE),
            ATTR_MASTER: addressbook.get(ATTR_MASTER),
            ATTR_MANAGER: addressbook.get(ATTR_MANAGER),
            ATTR_SLAVE: addressbook.get(ATTR_SLAVE),
            ATTR_BATTERYLIST: addressbook.get(ATTR_BATTERYLIST),
            ATTR_LASTCLOUDSYNC: datetime.now(),
        }


class FoxESSRunningState(FoxESSEntity):
    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug("Initiating Entity - %s", self._nameValue)
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
        if self.coordinator.data["raw"]:
            if self._keyValue not in self.coordinator.data["raw"]:
                _LOGGER.debug("%s None", self._keyValue)
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
                    _LOGGER.debug("runcode %s", res)
                    resText = f"{res}: unknown code"
                return resText
        return None


class FoxESSEnergySolar(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID, max_value=None):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Solar")
        self._attr_name = name + " - Solar"
        self._attr_unique_id = deviceID + "solar"
        self._max_value = max_value
        self._last_day = None
        self._max_today = 0.0
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        today = dt_util.now().date()
        if self._last_day != today:
            self._last_day = today
            self._max_today = 0.0

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

        energysolar = round((loads + charge + feedIn - gridConsumption - discharge), 3)
        if energysolar < 0:
            energysolar = 0

        # Sanity check: ignore spikes exceeding max_value
        if self._max_value is not None and energysolar > self._max_value:
            _LOGGER.warning(
                "%s value %s exceeds sanity check threshold %s kWh, ignoring",
                self._attr_name,
                energysolar,
                self._max_value,
            )
            return round(self._max_today, 3) if self._max_today > 0 else None

        # Monotonic ratchet: prevent evening drops from creating negative stats deltas
        if energysolar > self._max_today:
            self._max_today = energysolar

        return round(self._max_today, 3)


class FoxESSSolarPower(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Solar Power")
        self._attr_name = name + " - Solar Power"
        self._attr_unique_id = deviceID + "solar-power"
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
            gridConsumption = float(
                self.coordinator.data["raw"]["gridConsumptionPower"]
            )

        if "batDischargePower" not in self.coordinator.data["raw"]:
            discharge = 0
        else:
            if self.coordinator.data["raw"]["batDischargePower"] is None:
                discharge = 0
            else:
                discharge = float(self.coordinator.data["raw"]["batDischargePower"])

        # check if what was returned (that some time was negative) is <0, so fix it
        total = loads + charge + feedIn - gridConsumption - discharge
        if total < 0:
            total = 0
        return round(total, 3)


class FoxESSBatSoC(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug("Initiating Entity - %s", self._nameValue)
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
                _LOGGER.debug("%s None", self._keyValue)
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None

    @property
    def icon(self):
        return icon_for_battery_level(battery_level=self.native_value, charging=None)


class FoxESSBatMinSoC(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat MinSoC")
        self._attr_name = name + " - Bat MinSoC"
        self._attr_unique_id = deviceID + "bat-minsoc"
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
        return None

    @property
    def icon(self):
        return icon_for_battery_level(battery_level=self.native_value, charging=None)


class FoxESSBatMinSoConGrid(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Bat minSocOnGrid")
        self._attr_name = name + " - Bat minSocOnGrid"
        self._attr_unique_id = deviceID + "bat-minSocOnGrid"
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
        return None

    @property
    def icon(self):
        return icon_for_battery_level(battery_level=self.native_value, charging=None)


class FoxESSTemp(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, name, deviceID, nameValue, uniqueValue, keyValue):
        super().__init__(coordinator=coordinator)
        self._nameValue = nameValue
        self._uniqueValue = uniqueValue
        self._keyValue = keyValue
        _LOGGER.debug("Initiating Entity - %s", self._nameValue)
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
                _LOGGER.debug("%s None", self._keyValue)
            else:
                return self.coordinator.data["raw"][self._keyValue]
        return None


class FoxESSResidualEnergy(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_device_class = getattr(SensorDeviceClass, "ENERGY_STORAGE", None)
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Residual Energy")
        self._attr_name = name + " - Residual Energy"
        self._attr_unique_id = deviceID + "residual-energy"
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        if data.get("online") and data.get("raw"):
            raw = data["raw"]
            if "ResidualEnergy" not in raw:
                _LOGGER.debug("ResidualEnergy None")
                return None
            re = raw["ResidualEnergy"]
            if re is None:
                return None
            try:
                re_float = float(re)
            except (ValueError, TypeError):
                return None
            if re_float > 100.0:
                re_float = re_float / 100.0
            elif re_float < 0:
                re_float = 0.0
            return round(re_float, 2)
        return None


class FoxESSResponseTime(FoxESSEntity):
    _attr_state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "mS"

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initiating Entity - Response Time")
        self._attr_name = name + " - Response Time"
        self._attr_unique_id = deviceID + "response-time"
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
