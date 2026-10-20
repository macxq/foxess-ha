"""Tests for FoxESS sensor setup and multi-inverter handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
