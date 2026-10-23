"""Tests for FoxESS coordinator setup and entry lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.foxess.const import CONF_APIKEY, CONF_DEVICESN, DOMAIN


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.asyncio
async def test_async_setup_and_unload_entry(hass):
    """Test successful setup and unload of config entry storing coordinator and client."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICESN: "SN123456", CONF_APIKEY: "mock_key", "has_battery": True},
        entry_id="test_entry_id",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.foxess.PLATFORMS", [Platform.SENSOR]), \
         patch("custom_components.foxess.sensor.async_setup_entry", return_value=True), \
         patch("custom_components.foxess.FoxDataUpdateCoordinator.async_config_entry_first_refresh", new_callable=AsyncMock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.LOADED
        assert DOMAIN in hass.data
        assert "test_entry_id" in hass.data[DOMAIN]
        assert "coordinator" in hass.data[DOMAIN]["test_entry_id"]
        assert "client" in hass.data[DOMAIN]["test_entry_id"]

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.NOT_LOADED
        assert "test_entry_id" not in hass.data.get(DOMAIN, {})


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.asyncio
async def test_async_setup_entry_not_ready(hass):
    """Test ConfigEntryNotReady raised when initial coordinator refresh fails."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICESN: "SN123456", CONF_APIKEY: "mock_key"},
        entry_id="test_entry_not_ready",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.foxess.PLATFORMS", [Platform.SENSOR]), \
         patch("custom_components.foxess.FoxDataUpdateCoordinator.async_config_entry_first_refresh", side_effect=ConfigEntryNotReady):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.SETUP_RETRY


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.asyncio
async def test_async_setup_entry_persists_has_battery(hass):
    """Test discovered has_battery is saved to config entry data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICESN: "SN123456", CONF_APIKEY: "mock_key"},
        entry_id="test_entry_battery",
    )
    entry.add_to_hass(hass)

    async def mock_refresh(self):
        self.data = {"addressbook": {"hasBattery": True}}
        return None

    with patch("custom_components.foxess.PLATFORMS", [Platform.SENSOR]), \
         patch("custom_components.foxess.sensor.async_setup_entry", return_value=True), \
         patch("custom_components.foxess.FoxDataUpdateCoordinator.async_config_entry_first_refresh", new=mock_refresh):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.LOADED
        assert entry.data.get("has_battery") is True


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.asyncio
async def test_sensor_setup_entry_consumes_coordinator(hass):
    """Test sensor async_setup_entry consumes existing coordinator from hass.data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICESN: "SN123456", CONF_APIKEY: "mock_key"},
        entry_id="test_entry_sensor",
    )
    entry.add_to_hass(hass)
    mock_coordinator = MagicMock()
    mock_coordinator.devicesn = "SN123456"
    mock_coordinator.inverter_name = "FoxESS"
    mock_coordinator.deviceID = "SN123456"
    mock_coordinator.data = {
        "raw": {},
        "report": {},
        "reportDailyGeneration": {},
        "battery": {},
        "addressbook": {"hasBattery": False},
        "online": True,
    }
    mock_client = MagicMock()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": mock_coordinator,
        "client": mock_client,
    }

    mock_add_entities = MagicMock()
    from custom_components.foxess.sensor import async_setup_entry as sensor_async_setup_entry
    with patch("custom_components.foxess.sensor._async_setup_foxess") as mock_setup_foxess:
        await sensor_async_setup_entry(hass, entry, mock_add_entities)
        mock_setup_foxess.assert_called_once()
        assert mock_setup_foxess.call_args[1].get("coordinator") == mock_coordinator
