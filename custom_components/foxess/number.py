from homeassistant.components.input_number import (InputNumber)
from homeassistant.helpers.entity import (EntityCategory)
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):

    _LOGGER.debug("Starting FoxESS Clound integration -  Number Platform")

    #coordinator: SensiboDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

#     async_add_entities(
#        [FoxESSEnergyBatMinSoC("aaa","bb")]
#     )


# class FoxESSEnergyBatMinSoC(InputNumber):
#     _attr_value = 4
#     _attr_entity_category = EntityCategory.CONFIG
#     _attr_available_with_device_off=True,

#     def __init__(self, name, deviceID):
#         _LOGGER.debug("Initing Entity - Bat Min SoC")
#         self._attr_name = name + " - Bat Min SoC"
#         self._attr_key = "BatMinSoC"
#         self._attr_unique_id = deviceID+"-bat_min_SoC"
#         self._attr_method = "async_set_value"


#     async def async_set_value(self, value):
#         """Update the current value."""
#         _LOGGER.debug("Updating value %d",value)
#         self._attr_value = value
#         self.async_write_ha_state()

