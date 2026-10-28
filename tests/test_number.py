"""Tests for FoxESS Battery SoC number platform."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.components.number import NumberEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.foxess.const import DOMAIN, FetchResult
from custom_components.foxess.number import (
    FoxESSBatMinSoCNumber,
    FoxESSBatMinSoCOnGridNumber,
    async_setup_entry,
)


@pytest.mark.asyncio
async def test_min_soc_numbers_clamping_and_write(hass):
    """Test Min SoC and Min SoC on Grid clamping and API calls."""
    coordinator = AsyncMock()
    coordinator.data = {
        "addressbook": {"hasBattery": True},
        "battery": {"minSoc": 15, "minSocOnGrid": 20},
    }
    min_soc = FoxESSBatMinSoCNumber(coordinator, "FoxESS", "SN123", "SN123", "APIKEY")
    min_soc_grid = FoxESSBatMinSoCOnGridNumber(coordinator, "FoxESS", "SN123", "SN123", "APIKEY")

    assert isinstance(min_soc, CoordinatorEntity)
    assert isinstance(min_soc, NumberEntity)
    assert min_soc.name == "FoxESS - Min SoC"
    assert min_soc.unique_id == "SN123_min_soc"
    assert min_soc.native_value == 15
    assert min_soc.native_min_value == 10
    assert min_soc.native_max_value == 100
    assert min_soc.native_step == 1

    assert min_soc_grid.name == "FoxESS - Min SoC on Grid"
    assert min_soc_grid.unique_id == "SN123_min_soc_on_grid"
    assert min_soc_grid.native_value == 20

    # Setting min_soc higher than minSocOnGrid clamps minSocOnGrid to 25
    with patch("custom_components.foxess.number.FoxESSApiClient.async_set_battery_soc", new_callable=AsyncMock) as mock_set:
        mock_set.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 50.0)
        await min_soc.async_set_native_value(25)
        mock_set.assert_called_once_with("SN123", "APIKEY", 25, 25)
        assert coordinator.data["battery"]["minSoc"] == 25
        assert coordinator.data["battery"]["minSocOnGrid"] == 25
        coordinator.async_request_refresh.assert_called_once()

    # Setting minSocOnGrid lower than minSoc clamps minSoc to 10
    coordinator.data["battery"] = {"minSoc": 25, "minSocOnGrid": 25}
    coordinator.async_request_refresh.reset_mock()
    with patch("custom_components.foxess.number.FoxESSApiClient.async_set_battery_soc", new_callable=AsyncMock) as mock_set:
        mock_set.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 50.0)
        await min_soc_grid.async_set_native_value(10)
        mock_set.assert_called_once_with("SN123", "APIKEY", 10, 10)
        assert coordinator.data["battery"]["minSoc"] == 10
        assert coordinator.data["battery"]["minSocOnGrid"] == 10
        coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_min_soc_numbers_api_failure(hass):
    """Test error handling when API fails to set SoC."""
    coordinator = AsyncMock()
    coordinator.data = {
        "addressbook": {"hasBattery": True},
        "battery": {"minSoc": 15, "minSocOnGrid": 20},
    }
    min_soc = FoxESSBatMinSoCNumber(coordinator, "FoxESS", "SN123", "SN123", "APIKEY")

    with patch("custom_components.foxess.number.FoxESSApiClient.async_set_battery_soc", new_callable=AsyncMock) as mock_set:
        mock_set.return_value = (FetchResult.ERROR, {"errno": 40001, "msg": "failed"}, 50.0)
        with pytest.raises(HomeAssistantError, match="Failed to set FoxESS battery SoC"):
            await min_soc.async_set_native_value(30)
        # Value must not be modified in coordinator
        assert coordinator.data["battery"]["minSoc"] == 15


@pytest.mark.asyncio
async def test_number_setup_entry_pv_only(hass):
    """Test that number entities are not added for PV-only systems without battery."""
    coordinator = AsyncMock()
    coordinator.data = {"addressbook": {"hasBattery": False}}
    entry = MockConfigEntry(domain=DOMAIN, data={"deviceSN": "PV123", "has_battery": False})
    async_add_entities = MagicMock()
    with patch.dict(hass.data, {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}):
        await async_setup_entry(hass, entry, async_add_entities)
        async_add_entities.assert_called_once_with([])


@pytest.mark.asyncio
async def test_number_setup_entry_with_battery(hass):
    """Test that number entities are added when battery is fitted."""
    coordinator = AsyncMock()
    coordinator.data = {"addressbook": {"hasBattery": True}}
    coordinator.inverter_name = "FoxInverter"
    coordinator.devicesn = "SN_BAT"
    coordinator.deviceID = "SN_BAT"
    coordinator.apiKey = "KEY_BAT"
    entry = MockConfigEntry(domain=DOMAIN, data={"deviceSN": "SN_BAT", "has_battery": True})
    async_add_entities = MagicMock()
    with patch.dict(hass.data, {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}):
        await async_setup_entry(hass, entry, async_add_entities)
        assert async_add_entities.call_count == 1
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 2
        assert any(isinstance(e, FoxESSBatMinSoCNumber) for e in entities)
        assert any(isinstance(e, FoxESSBatMinSoCOnGridNumber) for e in entities)
