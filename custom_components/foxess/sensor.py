from __future__ import annotations

from collections import namedtuple
from datetime import datetime
import logging

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
    SensorEntity
)

from homeassistant.components.number import (NumberEntity)
from homeassistant.helpers.entity import (EntityCategory)

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

from .const import (
    DOMAIN,
    ATT_COORDINATOR,
    ATT_NAME,
    ATT_DEVICEID
)


from homeassistant.helpers.icon import icon_for_battery_level
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)




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



async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    _LOGGER.debug("Starting FoxESS Clound integration -  Sensor Platform")

    coordinator = hass.data[DOMAIN][ATT_COORDINATOR]
    name = hass.data[DOMAIN][ATT_NAME]
    deviceID = hass.data[DOMAIN][ATT_DEVICEID]

    async_add_entities(
        [FoxESSPV1Power(coordinator, name, deviceID),
        FoxESSPV2Power(coordinator, name, deviceID),
        FoxESSPV3Power(coordinator, name, deviceID), 
        FoxESSPV4Power(coordinator, name, deviceID), 
        FoxESSBatTemp(coordinator, name, deviceID),
        FoxESSBatSoC(coordinator, name, deviceID),
        FoxESSSolarPower(coordinator, name, deviceID),
        FoxESSEnergySolar(coordinator, name, deviceID),
        FoxESSInverter(coordinator, name, deviceID),
        FoxESSPGenerationPower(coordinator, name, deviceID), 
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
        FoxESSEnergyLoad(coordinator, name, deviceID)])

class FoxESSPGenericPowerEntity(CoordinatorEntity, SensorEntity):
    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_device_class = DEVICE_CLASS_POWER
    _attr_native_unit_of_measurement = POWER_KILO_WATT

    def __init__(self, coordinator, name, deviceID, attribute):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Sensor - %s", attribute)
        self._attr_name = "{} - {}".format(name, attribute)
        self._attr_unique_id = "{}-{}".format(deviceID,to_lower_kebab_case(attribute))
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ],
        )

    def getPoweData(self) -> str | None:
        return None 
    
    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["inverterStatus"] != 0:
            return self.getPoweData()
        return None 

class FoxESSEnergyGenericEntity(CoordinatorEntity, SensorEntity):

    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    energy_data = None

    def __init__(self, coordinator, name, deviceID,attribute,unique_id=None) :
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("Initing Sensor - %s", attribute)
        self._attr_name = "{} - {}".format(name, attribute)
        self._attr_unique_id = unique_id if unique_id!=None else "{}-{}".format(deviceID,to_lower_kebab_case(attribute))

        _LOGGER.debug("_attr_unique_id %s",  self._attr_unique_id)
        self.status = namedtuple(
            "status",
            [
                ATTR_DATE,
                ATTR_TIME,
            ]
        )

    def getEnergyData(self) -> str | None:
        return None 

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["inverterStatus"] != 0:
            if self.energy_data is None or self.coordinator.data["report"]["generation"] >= self.energy_data:
                self.energy_data = self.getEnergyData()
            return self.energy_data
        return None

    


class FoxESSEnergyGenerated(FoxESSEnergyGenericEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Energy Generated","{}energy-generated".format(deviceID))
        
    def getEnergyData(self) -> str | None:
        return self.coordinator.data["report"]["generation"]


        
class FoxESSPGenerationPower(FoxESSPGenericPowerEntity):
    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Generation Power")


    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["generationPower"]


#############

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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["gridConsumptionPower"]
        return None


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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["feedinPower"]
        return None 
        

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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["batDischargePower"]
        return None 


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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["batChargePower"]
        return None 
        

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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["loadsPower"]
        return None 


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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["pv1Power"]
        return None 


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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["pv2Power"]
        return None 
        

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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["pv3Power"]
        return None 


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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["pv4Power"]
        return None 





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
        if self.coordinator.data["inverterStatus"] != 0:
            if self.coordinator.data["report"]["gridConsumption"] == 0:
                energygrid = None
            else:
                energygrid = self.coordinator.data["report"]["gridConsumption"]
            return energygrid
        return None


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
        if self.coordinator.data["inverterStatus"] != 0:
            if self.coordinator.data["report"]["feedin"] == 0:
                energyfeedin = None
            else:
                energyfeedin = self.coordinator.data["report"]["feedin"]
            return energyfeedin
        return None


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
        if self.coordinator.data["inverterStatus"] != 0:
            if self.coordinator.data["report"]["chargeEnergyToTal"] == 0:
                energycharge = None
            else:
                energycharge = self.coordinator.data["report"]["chargeEnergyToTal"]
            return energycharge
        return None


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
        if self.coordinator.data["inverterStatus"] != 0:
            if self.coordinator.data["report"]["dischargeEnergyToTal"] == 0:
                energydischarge = None
            else:
                energydischarge = self.coordinator.data["report"]["dischargeEnergyToTal"]
            return energydischarge
        return None


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
        if self.coordinator.data["inverterStatus"] != 0:
            if self.coordinator.data["report"]["loads"] == 0:
                energyload = None
            else:
                energyload = self.coordinator.data["report"]["loads"]
            return energyload
        return None


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
                ATTR_FEEDINDATE,
                ATTR_LASTCLOUDSYNC
            ],
        )

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data["inverterStatus"] == 1:
            return "on-line"
        elif self.coordinator.data["inverterStatus"] == 2:
            return "alarm"
        else:
            return "off-line"

    @property
    def icon(self):
        if self.coordinator.data["inverterStatus"] == 2:
            return "mdi:alert-outline"
        else:
            return "mdi:solar-power"

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
        if self.coordinator.data["inverterStatus"] != 0:
            loads = float(self.coordinator.data["report"]["loads"])
            charge = float(self.coordinator.data["report"]["chargeEnergyToTal"])
            feedIn = float(self.coordinator.data["report"]["feedin"])
            gridConsumption = float(
                self.coordinator.data["report"]["gridConsumption"])
            discharge = float(
                self.coordinator.data["report"]["dischargeEnergyToTal"])

            return loads + charge + feedIn - gridConsumption - discharge
        return None


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
        if self.coordinator.data["inverterStatus"] != 0:
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
        return None


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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["SoC"]
        return  None

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
        if self.coordinator.data["inverterStatus"] != 0:
            return self.coordinator.data["raw"]["batTemperature"]
        return None

def to_lower_kebab_case(text):
    return text.lower().replace(" ","-")