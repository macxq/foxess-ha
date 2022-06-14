from __future__ import annotations

from collections import namedtuple
from datetime import datetime
from datetime import date
import logging

from homeassistant.components.rest.data import RestData
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.components.sensor import (
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_POWER,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_TEMPERATURE,
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
    ENERGY_KILO_WATT_HOUR,
    POWER_KILO_WATT,
    TEMP_CELSIUS,

)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity
)

from .const import (
    DOMAIN,
    ATT_COORDINATOR,
    ATT_NAME,
    ATT_DEVICEID
)


from homeassistant.helpers.icon import icon_for_battery_level
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

    
    for cofig in  hass.data[DOMAIN]:
        coordinator =cofig[ATT_COORDINATOR]
        name = cofig[ATT_NAME]
        deviceID = cofig[ATT_DEVICEID]

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

    def __init__(self, coordinator, name, deviceID, attribute,unique_id=None):
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("🆕 Initing Sensor -%s  %s", name, attribute)
        self._attr_name = "{} - {}".format(name, attribute)
        self._attr_unique_id = unique_id if unique_id!=None else "{}-{}".format(deviceID,to_lower_kebab_case(attribute))
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
    energy_data_date = None

    def __init__(self, coordinator, name, deviceID,attribute,unique_id=None) :
        super().__init__(coordinator=coordinator)
        _LOGGER.debug("🆕 Initing Sensor - %s", attribute)
        self._attr_name = "{} - {}".format(name, attribute)
        self._attr_unique_id = unique_id if unique_id!=None else "{}-{}".format(deviceID,to_lower_kebab_case(attribute))
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
            if (self.getEnergyData() > 0 and (self.energy_data is None or self.coordinator.data["report"]["generation"] >= self.energy_data)) or self.energy_data_date != date.today() :
                self.energy_data = self.getEnergyData()
                self.energy_data_date = date.today()
            return self.energy_data
        return None
  
        
class FoxESSPGenerationPower(FoxESSPGenericPowerEntity):
    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Generation Power")


    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["generationPower"]


class FoxESSGridConsumptionPower(FoxESSPGenericPowerEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Grid Consumption Power","{}grid-consumption-power".format(deviceID))

    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["gridConsumptionPower"]



class FoxESSFeedInPower(FoxESSPGenericPowerEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"FeedIn Power","{}feedIn-power".format(deviceID))

    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["feedinPower"]
       

class FoxESSBatDischargePower(FoxESSPGenericPowerEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Bat Discharge Power","{}bat-discharge-power".format(deviceID))

    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["batDischargePower"]


class FoxESSBatChargePower(FoxESSPGenericPowerEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Bat Charge Power","{}bat-charge-power".format(deviceID))

    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["batChargePower"]
        

class FoxESSLoadPower(FoxESSPGenericPowerEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Load Power","{}load-power".format(deviceID))

    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["loadsPower"]


class FoxESSPV1Power(FoxESSPGenericPowerEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"PV1 Power","{}pv1-power".format(deviceID))

    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["pv1Power"]

class FoxESSPV2Power(FoxESSPGenericPowerEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"PV2 Power","{}pv2-power".format(deviceID))

    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["pv2Power"]

class FoxESSPV3Power(FoxESSPGenericPowerEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"PV3 Power","{}pv3-power".format(deviceID))

    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["pv3Power"]

class FoxESSPV4Power(FoxESSPGenericPowerEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"PV4 Power","{}pv4-power".format(deviceID))

    def getPoweData(self) -> str | None:
        return self.coordinator.data["raw"]["pv4Power"]


class FoxESSEnergyGenerated(FoxESSEnergyGenericEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Energy Generated","{}energy-generated".format(deviceID))
        
    def getEnergyData(self) -> str | None:
        return self.coordinator.data["report"]["generation"]


class FoxESSEnergyGridConsumption(FoxESSEnergyGenericEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Grid Consumption","{}grid-consumption".format(deviceID))
        
    def getEnergyData(self) -> str | None:
        return self.coordinator.data["report"]["gridConsumption"]



class FoxESSEnergyFeedin(FoxESSEnergyGenericEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"FeedIn","{}feedIn".format(deviceID))
        
    def getEnergyData(self) -> str | None:
        return self.coordinator.data["report"]["feedin"]



class FoxESSEnergyBatCharge(FoxESSEnergyGenericEntity):
    

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Bat Charge","{}bat-charge".format(deviceID))
        
    def getEnergyData(self) -> str | None:
        return self.coordinator.data["report"]["chargeEnergyToTal"]

   

class FoxESSEnergyBatDischarge(FoxESSEnergyGenericEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Bat Discharge","{}bat-discharge".format(deviceID))
        
    def getEnergyData(self) -> str | None:
        return self.coordinator.data["report"]["dischargeEnergyToTal"]



class FoxESSEnergyLoad(FoxESSEnergyGenericEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Load","{}load".format(deviceID))
        
    def getEnergyData(self) -> str | None:
        return self.coordinator.data["report"]["loads"]


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


#### ????????? 

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


class FoxESSSolarPower(FoxESSPGenericPowerEntity):

    def __init__(self, coordinator, name, deviceID):
        super().__init__(coordinator, name, deviceID,"Solar Power","{}solar-power".format(deviceID))

    def getPoweData(self) -> str | None:
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