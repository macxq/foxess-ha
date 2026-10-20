"""Tests for FoxESS sensor setup and multi-inverter handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.core import HomeAssistant
from custom_components.foxess import sensor


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_auth_errno_constants():
    """Verify _AUTH_ERRNO contains all FoxESS OpenAPI authentication failure codes."""
    assert 40256 in sensor._AUTH_ERRNO
    assert 41808 in sensor._AUTH_ERRNO
    assert 41809 in sensor._AUTH_ERRNO


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_multiple_inverters_timeslice_preserved(hass: HomeAssistant):
    """Setting up a second inverter must not reset the timeslice dictionary."""
    config1 = {
        sensor.CONF_NAME: "Inverter 1",
        sensor.CONF_DEVICEID: "DEV1",
        sensor.CONF_DEVICESN: "SN1",
        sensor.CONF_APIKEY: "key1",
    }
    config2 = {
        sensor.CONF_NAME: "Inverter 2",
        sensor.CONF_DEVICEID: "DEV2",
        sensor.CONF_DEVICESN: "SN2",
        sensor.CONF_APIKEY: "key2",
    }
    mock_add_entities = MagicMock()
    with patch(
        "custom_components.foxess.sensor.DataUpdateCoordinator.async_refresh",
        new_callable=AsyncMock,
    ):
        await sensor._async_setup_foxess(hass, config1, mock_add_entities)
        assert "SN1" in sensor.timeslice
        assert sensor.timeslice["SN1"] == sensor.RETRY_NEXT_SLOT

        await sensor._async_setup_foxess(hass, config2, mock_add_entities)
        assert "SN1" in sensor.timeslice
        assert "SN2" in sensor.timeslice
        assert sensor.timeslice["SN1"] == sensor.RETRY_NEXT_SLOT
        assert sensor.timeslice["SN2"] == sensor.RETRY_NEXT_SLOT


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_async_setup_platform_triggers_import(hass: HomeAssistant):
    """When a device is not yet in ConfigEntries, async_setup_platform triggers import."""
    config = {
        sensor.CONF_NAME: "YAML Inverter",
        sensor.CONF_DEVICEID: "DEV1",
        sensor.CONF_DEVICESN: "SN1",
        sensor.CONF_APIKEY: "key1",
    }
    mock_add_entities = MagicMock()
    with patch.object(
        hass.config_entries.flow, "async_init", new_callable=AsyncMock
    ) as mock_flow_init:
        await sensor.async_setup_platform(hass, config, mock_add_entities)
        mock_flow_init.assert_called_once_with(
            "foxess",
            context={"source": SOURCE_IMPORT},
            data=config,
        )
    mock_add_entities.assert_not_called()


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_async_setup_platform_skips_if_entry_exists(hass: HomeAssistant):
    """When a device already has a ConfigEntry, async_setup_platform does nothing."""
    entry = MockConfigEntry(
        domain="foxess",
        unique_id="SN1",
        data={sensor.CONF_DEVICESN: "SN1", sensor.CONF_APIKEY: "key1"},
    )
    entry.add_to_hass(hass)

    config = {
        sensor.CONF_NAME: "YAML Inverter",
        sensor.CONF_DEVICEID: "DEV1",
        sensor.CONF_DEVICESN: "SN1",
        sensor.CONF_APIKEY: "key1",
    }
    mock_add_entities = MagicMock()
    with patch.object(
        hass.config_entries.flow, "async_init", new_callable=AsyncMock
    ) as mock_flow_init:
        await sensor.async_setup_platform(hass, config, mock_add_entities)
        mock_flow_init.assert_not_called()
    mock_add_entities.assert_not_called()


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_info_on_foxess_entity():
    """Verify FoxESSEntity correctly builds DeviceInfo from coordinator."""
    coordinator = MagicMock()
    coordinator.devicesn = "SN_TEST_123"
    coordinator.inverter_name = "My Solar Inverter"
    coordinator.data = {
        "addressbook": {
            sensor.ATTR_DEVICE_TYPE: "H1-3.7-E",
            sensor.ATTR_MASTER: "1.54",
        }
    }

    entity = sensor.FoxESSEntity(coordinator=coordinator)
    dev_info = entity.device_info

    assert dev_info is not None
    assert dev_info["identifiers"] == {(sensor.DOMAIN, "SN_TEST_123")}
    assert dev_info["name"] == "My Solar Inverter"
    assert dev_info["manufacturer"] == "FoxESS"
    assert dev_info["model"] == "H1-3.7-E"
    assert dev_info["sw_version"] == "1.54"
    assert dev_info["serial_number"] == "SN_TEST_123"
    assert dev_info["configuration_url"] == sensor._ENDPOINT_OA_DOMAIN


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_info_fallback_and_none():
    """Verify FoxESSEntity fallback to _deviceID and None when missing."""
    # Fallback to _deviceID if coordinator has no devicesn
    coordinator = MagicMock()
    coordinator.devicesn = None
    coordinator.inverter_name = None
    coordinator.data = {}

    entity = sensor.FoxESSEntity(coordinator=coordinator)
    entity._deviceID = "DEV_FALLBACK"
    assert entity.device_info["identifiers"] == {(sensor.DOMAIN, "DEV_FALLBACK")}

    # Return None if no devicesn or _deviceID
    entity._deviceID = None
    assert entity.device_info is None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_async_setup_foxess_populates_device_info_on_all_entities(hass: HomeAssistant):
    """Verify all entities registered during setup have valid DeviceInfo grouping."""
    config = {
        sensor.CONF_NAME: "Dom",
        sensor.CONF_DEVICEID: "DEV1",
        sensor.CONF_DEVICESN: "662T602014NC048",
        sensor.CONF_APIKEY: "testkey",
    }
    mock_add_entities = MagicMock()
    with patch(
        "custom_components.foxess.sensor.DataUpdateCoordinator.async_refresh",
        new_callable=AsyncMock,
    ):
        await sensor._async_setup_foxess(hass, config, mock_add_entities)

    assert mock_add_entities.call_count >= 1
    # Check all entities passed to async_add_entities
    for call in mock_add_entities.call_args_list:
        entities = call[0][0]
        assert len(entities) > 0
        for ent in entities:
            assert isinstance(ent, sensor.FoxESSEntity)
            assert ent.device_info is not None
            assert ent.device_info["identifiers"] == {(sensor.DOMAIN, "662T602014NC048")}
            assert ent.device_info["name"] == "Dom"
            assert ent.device_info["manufacturer"] == "FoxESS"
            assert ent.device_info["serial_number"] == "662T602014NC048"
