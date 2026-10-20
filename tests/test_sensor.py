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
