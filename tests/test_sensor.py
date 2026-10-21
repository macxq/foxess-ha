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


@pytest.mark.usefixtures("enable_custom_integrations")
def test_measurement_sensors_have_state_class():
    """Verify sensors requiring statistics/Energy Dashboard have SensorStateClass.MEASUREMENT."""
    from homeassistant.components.sensor import SensorStateClass

    coordinator = MagicMock()
    for cls in [
        sensor.FoxESSBatSoC,
        sensor.FoxESSTemp,
        sensor.FoxESSBatMinSoC,
        sensor.FoxESSBatMinSoConGrid,
        sensor.FoxESSResidualEnergy,
        sensor.FoxESSResponseTime,
    ]:
        try:
            entity = cls(coordinator, "Inverter", "DEV1", "NameVal", "uniq", "key")
        except TypeError:
            entity = cls(coordinator, "Inverter", "DEV1")

        assert entity.state_class == SensorStateClass.MEASUREMENT, f"{cls.__name__} missing MEASUREMENT state_class"


@pytest.mark.usefixtures("enable_custom_integrations")
def test_energy_generated_sanity_check():
    """Verify daily Energy Generated entity ignores spikes exceeding threshold."""
    coordinator = MagicMock()
    daily_entity = sensor.FoxESSEnergyGenerated(
        coordinator, "Inverter", "DEV1", "Energy Generated", "energy-generated", "value", max_value=100.0
    )
    cumul_entity = sensor.FoxESSEnergyGenerated(
        coordinator, "Inverter", "DEV1", "Energy Generated Cumulative", "energy-generated-cumulative", "cumulative"
    )

    # Normal daily reading
    coordinator.data = {"reportDailyGeneration": {"value": 25.4, "cumulative": 1500.0}}
    assert daily_entity.native_value == 25.4
    assert cumul_entity.native_value == 1500.0

    # Spurious spike (e.g. 33 MWh sent by cloud instead of daily value)
    coordinator.data = {"reportDailyGeneration": {"value": 33000.0, "cumulative": 33000.0}}
    assert daily_entity.native_value is None  # Daily entity ignores spike
    assert cumul_entity.native_value == 33000.0  # Cumulative entity is not capped


@pytest.mark.usefixtures("enable_custom_integrations")
def test_energy_solar_monotonic_ratchet_and_sanity():
    """Verify FoxESSEnergySolar ratchets within a day and ignores spikes."""
    import datetime
    coordinator = MagicMock()
    solar_entity = sensor.FoxESSEnergySolar(
        coordinator, "Inverter", "DEV1", max_value=100.0
    )

    day1 = datetime.date(2026, 6, 1)
    day2 = datetime.date(2026, 6, 2)

    with patch("homeassistant.util.dt.now") as mock_now:
        mock_now.return_value.date.return_value = day1

        # Midday reading: 10 + 5 + 1 - 2 - 4 = 10 kWh
        coordinator.data = {
            "report": {
                "loads": 10.0,
                "chargeEnergyToTal": 5.0,
                "feedin": 1.0,
                "gridConsumption": 2.0,
                "dischargeEnergyToTal": 4.0,
            }
        }
        assert solar_entity.native_value == 10.0

        # Further increase in afternoon: loads increases to 15 -> formula = 15 kWh
        coordinator.data["report"]["loads"] = 15.0
        assert solar_entity.native_value == 15.0

        # Evening drop / calculation drift: loads drops to 14.5 -> formula = 14.5 kWh
        # Ratchet must preserve 15.0 to prevent negative stats in Energy Dashboard
        coordinator.data["report"]["loads"] = 14.5
        assert solar_entity.native_value == 15.0

        # Erroneous spike: formula yields 500 kWh (> 100.0 max_value)
        coordinator.data["report"]["loads"] = 500.0
        assert solar_entity.native_value == 15.0  # spike ignored, returns holding value

        # Next day rollover: formula resets to 0.5 kWh
        mock_now.return_value.date.return_value = day2
        coordinator.data["report"]["loads"] = 0.5
        coordinator.data["report"]["chargeEnergyToTal"] = 0.0
        coordinator.data["report"]["feedin"] = 0.0
        coordinator.data["report"]["gridConsumption"] = 0.0
        coordinator.data["report"]["dischargeEnergyToTal"] = 0.0
        assert solar_entity.native_value == 0.5


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_get_raw_age_check_respects_reduce_api_calls(hass: HomeAssistant):
    """Verify getRaw tolerates older samples (up to 661s) when reduce_api_calls is True."""
    import time
    import datetime
    import json

    now = time.time()
    zulu = datetime.datetime.now().astimezone().strftime("%z")
    sample_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 450)) + f" GMT{zulu}"

    payload = {
        "errno": 0,
        "msg": "success",
        "result": [
            {
                "time": sample_time,
                "datas": [
                    {"variable": "runningState", "value": "161"},
                    {"variable": "generationPower", "value": 1.5},
                ],
            }
        ],
    }

    mock_rest = MagicMock()
    mock_rest.data = json.dumps(payload)
    mock_rest.last_exception = None
    mock_rest.async_update = AsyncMock()

    all_data_standard = {"raw": {}, "addressbook": {"hasBattery": False}, "online": True}
    with patch("custom_components.foxess.sensor.RestData", return_value=mock_rest), \
         patch("custom_components.foxess.sensor.waitforAPI", new_callable=AsyncMock):
        # In standard mode (max_age=361), age=450 exceeds threshold -> online becomes False
        res = await sensor.getRaw(hass, all_data_standard, "api_key", "DEV_SN", reduce_api_calls=False)
        assert res == sensor.FetchResult.OK
        assert all_data_standard["online"] is False

    all_data_reduced = {"raw": {}, "addressbook": {"hasBattery": False}, "online": True}
    with patch("custom_components.foxess.sensor.RestData", return_value=mock_rest), \
         patch("custom_components.foxess.sensor.waitforAPI", new_callable=AsyncMock):
        # In reduced mode (max_age=661), age=450 is within threshold -> online remains True
        res = await sensor.getRaw(hass, all_data_reduced, "api_key", "DEV_SN", reduce_api_calls=True)
        assert res == sensor.FetchResult.OK
        assert all_data_reduced["online"] is True


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_get_raw_missing_or_invalid_timestamp(hass: HomeAssistant):
    """Verify getRaw handles missing or unparseable timestamps gracefully."""
    import json

    payload = {
        "errno": 0,
        "msg": "success",
        "result": [
            {
                "time": "invalid_timestamp",
                "datas": [
                    {"variable": "runningState", "value": "161"},
                ],
            }
        ],
    }

    mock_rest = MagicMock()
    mock_rest.data = json.dumps(payload)
    mock_rest.last_exception = None
    mock_rest.async_update = AsyncMock()

    all_data = {"raw": {}, "addressbook": {"hasBattery": False}, "online": True}
    with patch("custom_components.foxess.sensor.RestData", return_value=mock_rest), \
         patch("custom_components.foxess.sensor.waitforAPI", new_callable=AsyncMock):
        res = await sensor.getRaw(hass, all_data, "api_key", "DEV_SN", reduce_api_calls=True)
        assert res == sensor.FetchResult.OK
        assert all_data["online"] is True




