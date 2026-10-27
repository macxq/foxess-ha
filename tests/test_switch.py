"""Tests for FoxESS Mode Scheduler switch platform."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.foxess.const import DOMAIN, FetchResult
from custom_components.foxess.switch import FoxESSSchedulerSwitch, async_setup_entry


@pytest.mark.asyncio
async def test_scheduler_switch_toggle_and_attributes(hass):
    """Test switch state, attributes, turn_on and turn_off."""
    coordinator = AsyncMock()
    coordinator.data = {
        "addressbook": {"hasBattery": True},
        "schedulerEnabled": True,
        "schedulerGroups": [{"workMode": "ForceCharge", "startHour": 1}],
    }
    switch = FoxESSSchedulerSwitch(coordinator, "FoxESS", "SN123", "SN123", "APIKEY")

    assert isinstance(switch, CoordinatorEntity)
    assert isinstance(switch, SwitchEntity)
    assert switch.name == "FoxESS - Mode Scheduler"
    assert switch.unique_id == "SN123_mode_scheduler"
    assert switch.is_on is True
    assert switch.extra_state_attributes["scheduler_groups"] == coordinator.data["schedulerGroups"]

    # Turn off
    with patch("custom_components.foxess.switch.FoxESSApiClient.async_set_scheduler_flag", new_callable=AsyncMock) as mock_flag:
        mock_flag.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 50.0)
        await switch.async_turn_off()
        mock_flag.assert_called_once_with("SN123", "APIKEY", False)
        assert coordinator.data["schedulerEnabled"] is False
        coordinator.async_request_refresh.assert_called_once()

    # Turn on
    coordinator.async_request_refresh.reset_mock()
    with patch("custom_components.foxess.switch.FoxESSApiClient.async_set_scheduler_flag", new_callable=AsyncMock) as mock_flag:
        mock_flag.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 50.0)
        await switch.async_turn_on()
        mock_flag.assert_called_once_with("SN123", "APIKEY", True)
        assert coordinator.data["schedulerEnabled"] is True
        coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_switch_api_failure(hass):
    """Test error handling when API fails to toggle scheduler."""
    coordinator = AsyncMock()
    coordinator.data = {
        "addressbook": {"hasBattery": True},
        "schedulerEnabled": False,
    }
    switch = FoxESSSchedulerSwitch(coordinator, "FoxESS", "SN123", "SN123", "APIKEY")

    with patch("custom_components.foxess.switch.FoxESSApiClient.async_set_scheduler_flag", new_callable=AsyncMock) as mock_flag:
        mock_flag.return_value = (FetchResult.ERROR, {"errno": 40001, "msg": "failed"}, 50.0)
        with pytest.raises(HomeAssistantError, match="Failed to enable FoxESS mode scheduler"):
            await switch.async_turn_on()
        assert coordinator.data["schedulerEnabled"] is False


@pytest.mark.asyncio
async def test_switch_setup_entry_pv_only(hass):
    """Test that switch entities are not added for PV-only systems without battery."""
    coordinator = AsyncMock()
    coordinator.data = {"addressbook": {"hasBattery": False}}
    entry = MockConfigEntry(domain=DOMAIN, data={"deviceSN": "PV123", "has_battery": False})
    async_add_entities = MagicMock()
    with patch.dict(hass.data, {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}):
        await async_setup_entry(hass, entry, async_add_entities)
        async_add_entities.assert_called_once_with([])


@pytest.mark.asyncio
async def test_switch_setup_entry_with_battery(hass):
    """Test that switch entity is added when battery is fitted."""
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
        assert isinstance(entities[0], FoxESSSchedulerSwitch)
        assert entities[0].name == "FoxInverter - Mode Scheduler"
