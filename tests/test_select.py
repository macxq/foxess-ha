"""Tests for FoxESS Work Mode select entity."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.foxess.const import DOMAIN, FetchResult
from custom_components.foxess.select import (
    FoxESSWorkModeSelect,
    WORK_MODES,
    READ_ONLY_WORK_MODES,
    OPTIONS_TO_API,
    API_TO_OPTIONS,
    async_setup_entry,
)


@pytest.mark.asyncio
async def test_work_mode_select_options_and_change(hass):
    """Test options, current value, option selection and scheduler guard."""
    coordinator = AsyncMock()
    coordinator.data = {
        "addressbook": {"hasBattery": True},
        "workMode": "SelfUse",
        "schedulerEnabled": False,
    }
    select = FoxESSWorkModeSelect(coordinator, "FoxESS", "SN123", "SN123", "APIKEY")
    assert isinstance(select, CoordinatorEntity)
    assert isinstance(select, SelectEntity)
    assert select.name == "FoxESS - Work Mode"
    assert select.unique_id == "SN123_work_mode"
    assert select.current_option == "Self-Use"
    assert "Self-Use" in select.options
    assert "Feed-in" in select.options
    assert "Backup" in select.options
    assert "Peak Shaving" in select.options

    # Change option successfully
    with patch("custom_components.foxess.select.FoxESSApiClient.async_set_work_mode", new_callable=AsyncMock) as mock_set:
        mock_set.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 50.0)
        await select.async_select_option("Feed-in")
        mock_set.assert_called_once_with("SN123", "APIKEY", "Feedin")
        assert coordinator.data["workMode"] == "Feedin"
        coordinator.async_request_refresh.assert_called_once()

    # Rejection when scheduler is active
    coordinator.data["schedulerEnabled"] = True
    with pytest.raises(HomeAssistantError, match="Mode Scheduler is enabled"):
        await select.async_select_option("Backup")


@pytest.mark.asyncio
async def test_work_mode_select_read_only_modes(hass):
    """Test read-only work modes like ForceCharge and ForceDischarge."""
    coordinator = AsyncMock()
    coordinator.data = {
        "addressbook": {"hasBattery": True},
        "workMode": "ForceCharge",
        "schedulerEnabled": True,
    }
    select = FoxESSWorkModeSelect(coordinator, "FoxESS", "SN123", "SN123", "APIKEY")
    assert select.current_option == "ForceCharge"

    coordinator.data["workMode"] = "ForceDischarge"
    assert select.current_option == "ForceDischarge"


@pytest.mark.asyncio
async def test_work_mode_select_api_error_handling(hass):
    """Test error handling when API fails during select_option."""
    coordinator = AsyncMock()
    coordinator.data = {
        "addressbook": {"hasBattery": True},
        "workMode": "SelfUse",
        "schedulerEnabled": False,
    }
    select = FoxESSWorkModeSelect(coordinator, "FoxESS", "SN123", "SN123", "APIKEY")

    with patch("custom_components.foxess.select.FoxESSApiClient.async_set_work_mode", new_callable=AsyncMock) as mock_set:
        mock_set.return_value = (FetchResult.ERROR, {"errno": 40001, "msg": "failed"}, 50.0)
        with pytest.raises(HomeAssistantError, match="Failed to set FoxESS work mode"):
            await select.async_select_option("Backup")
        assert coordinator.data["workMode"] == "SelfUse"


@pytest.mark.asyncio
async def test_work_mode_select_not_created_for_pv_only(hass):
    """Test that select entities are not added for PV-only systems without battery."""
    coordinator = AsyncMock()
    coordinator.data = {"addressbook": {"hasBattery": False}}
    entry = MockConfigEntry(domain=DOMAIN, data={"deviceSN": "PV123", "has_battery": False})
    async_add_entities = MagicMock()
    with patch.dict(hass.data, {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}):
        await async_setup_entry(hass, entry, async_add_entities)
        async_add_entities.assert_called_once_with([])


@pytest.mark.asyncio
async def test_work_mode_select_created_when_battery_present(hass):
    """Test that select entity is added when battery is present."""
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
        assert len(entities) == 1
        assert isinstance(entities[0], FoxESSWorkModeSelect)
        assert entities[0].name == "FoxInverter - Work Mode"
