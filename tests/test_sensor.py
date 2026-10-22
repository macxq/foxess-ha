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


@pytest.mark.usefixtures("enable_custom_integrations")
def test_foxess_inverter_device_detail_timeout_no_key_error():
    """Verify FoxESSInverter does not raise KeyError: 'deviceSN' when device detail timed out."""
    coordinator = MagicMock()
    # State when device detail times out or on initial startup
    coordinator.data = {
        "addressbook": {"hasBattery": False, "status": "3"},
        "online": False,
    }

    inverter = sensor.FoxESSInverter(coordinator, "Fox Inverter", "DEV1")

    # native_value must safely return "off-line" without raising KeyError or ValueError
    assert inverter.native_value == "off-line"

    # extra_state_attributes must return None safely instead of KeyError: 'deviceSN' (#378)
    assert inverter.extra_state_attributes is None


@pytest.mark.usefixtures("enable_custom_integrations")
def test_foxess_inverter_empty_or_missing_status():
    """Verify FoxESSInverter handles empty or non-numeric addressbook status gracefully."""
    coordinator = MagicMock()
    inverter = sensor.FoxESSInverter(coordinator, "Fox Inverter", "DEV1")

    # Empty addressbook
    coordinator.data = {"addressbook": {}, "online": False}
    assert inverter.native_value is None
    assert inverter.extra_state_attributes is None

    # Invalid status
    coordinator.data = {"addressbook": {"status": "not_an_int"}, "online": False}
    assert inverter.native_value is None
    assert inverter.extra_state_attributes is None


@pytest.mark.usefixtures("enable_custom_integrations")
def test_foxess_inverter_extra_state_attributes_with_device_detail():
    """Verify FoxESSInverter extra_state_attributes populates safely when device detail is present."""
    coordinator = MagicMock()
    coordinator.data = {
        "addressbook": {
            sensor.ATTR_DEVICE_SN: "SN12345",
            sensor.ATTR_PLANTNAME: "Home Solar",
            sensor.ATTR_DEVICE_TYPE: "H1-3.7-E",
        },
        "online": True,
    }

    inverter = sensor.FoxESSInverter(coordinator, "Fox Inverter", "DEV1")
    attrs = inverter.extra_state_attributes

    assert attrs is not None
    assert attrs[sensor.ATTR_DEVICE_SN] == "SN12345"
    assert attrs[sensor.ATTR_PLANTNAME] == "Home Solar"
    assert attrs[sensor.ATTR_DEVICE_TYPE] == "H1-3.7-E"
    # Optional attributes missing from addressbook should be None, not KeyError
    assert attrs[sensor.ATTR_MASTER] is None
    assert attrs[sensor.ATTR_BATTERYLIST] is None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_residual_energy_scaling_in_get_raw(hass: HomeAssistant):
    """Verify ResidualEnergy handles all OpenAPI scaling cases (#297)."""
    import json
    import time
    import datetime

    cases = [
        # (raw_value, raw_unit, expected_raw)
        (1933.0, "0.01kWh", 19.33),  # Legacy OpenAPI reporting in hundredths of kWh
        (23.5, "0.01kWh", 23.5),     # BMS 2.004 / KH10 reporting directly in kWh with 0.01kWh unit
        (20.2, "kWh", 20.2),         # OpenAPI reporting directly in kWh
        (20.2, "1.0kWh", 20.2),      # OpenAPI reporting with 1.0kWh unit
        (235.0, "0.1kWh", 23.5),     # OpenAPI reporting with 0.1kWh unit
    ]

    for raw_val, raw_unit, expected_val in cases:
        now = time.time()
        zulu = datetime.datetime.now().astimezone().strftime("%z")
        sample_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)) + f" GMT{zulu}"
        payload = {
            "errno": 0,
            "msg": "success",
            "result": [
                {
                    "time": sample_time,
                    "datas": [
                        {"variable": "ResidualEnergy", "value": raw_val, "unit": raw_unit},
                    ],
                }
            ],
        }

        mock_rest = MagicMock()
        mock_rest.data = json.dumps(payload)
        mock_rest.last_exception = None
        mock_rest.async_update = AsyncMock()

        all_data = {"raw": {}, "addressbook": {"hasBattery": True}, "online": True}
        with patch("custom_components.foxess.sensor.RestData", return_value=mock_rest), \
             patch("custom_components.foxess.sensor.waitforAPI", new_callable=AsyncMock):
            res = await sensor.getRaw(hass, all_data, "api_key", "DEV_SN")
            assert res == sensor.FetchResult.OK
            assert all_data["raw"]["ResidualEnergy"] == pytest.approx(expected_val, 0.01), (
                f"Failed for input value={raw_val}, unit={raw_unit}: expected {expected_val}, got {all_data['raw'].get('ResidualEnergy')}"
            )


@pytest.mark.usefixtures("enable_custom_integrations")
def test_foxess_residual_energy_native_value():
    """Verify FoxESSResidualEnergy entity native_value handles bounds correctly."""
    coordinator = MagicMock()
    entity = sensor.FoxESSResidualEnergy(coordinator, "Fox Inverter", "DEV1")

    # Normal battery capacity
    coordinator.data = {"online": True, "raw": {"ResidualEnergy": 23.5}}
    assert entity.native_value == 23.5

    # Large battery system (e.g. 55 kWh) - must not divide by 100
    coordinator.data = {"online": True, "raw": {"ResidualEnergy": 55.0}}
    assert entity.native_value == 55.0

    # Raw value in 0.01kWh legacy (> 100)
    coordinator.data = {"online": True, "raw": {"ResidualEnergy": 1933.0}}
    assert entity.native_value == 19.33

    # Zero or missing
    coordinator.data = {"online": True, "raw": {"ResidualEnergy": 0.0}}
    assert entity.native_value == 0.0

    coordinator.data = {"online": True, "raw": {}}
    assert entity.native_value is None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_get_report_daily_generation_preserves_previous_values_when_fields_missing(hass: HomeAssistant):
    """Verify missing today/month/cumulative fields do not overwrite with 0 (#324)."""
    import json

    # Pre-existing values
    all_data = {
        "reportDailyGeneration": {
            "value": 15.5,
            "month": 120.0,
            "cumulative": 3500.0,
        }
    }

    # API response missing "today"
    payload = {
        "errno": 0,
        "msg": "success",
        "result": {
            "month": 125.0,
            "cumulative": 3505.0,
        },
    }

    mock_rest = MagicMock()
    mock_rest.data = json.dumps(payload)
    mock_rest.async_update = AsyncMock()

    with patch("custom_components.foxess.sensor.RestData", return_value=mock_rest), \
         patch("custom_components.foxess.sensor.waitforAPI", new_callable=AsyncMock):
        res = await sensor.getReportDailyGeneration(hass, all_data, "key", "DEV_SN")
        assert res == sensor.FetchResult.OK
        # "value" must retain 15.5 instead of being reset to 0
        assert all_data["reportDailyGeneration"]["value"] == 15.5
        assert all_data["reportDailyGeneration"]["month"] == 125.0
        assert all_data["reportDailyGeneration"]["cumulative"] == 3505.0


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_get_report_daily_generation_auth_failed(hass: HomeAssistant):
    """Verify authentication errors return FetchResult.AUTH_FAILED."""
    import json

    payload = {
        "errno": 41808,
        "msg": "token invalid",
    }

    mock_rest = MagicMock()
    mock_rest.data = json.dumps(payload)
    mock_rest.async_update = AsyncMock()

    all_data = {"reportDailyGeneration": {}}
    with patch("custom_components.foxess.sensor.RestData", return_value=mock_rest), \
         patch("custom_components.foxess.sensor.waitforAPI", new_callable=AsyncMock):
        res = await sensor.getReportDailyGeneration(hass, all_data, "key", "DEV_SN")
        assert res == sensor.FetchResult.AUTH_FAILED


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_daily_generation_timer_and_resilience(hass: HomeAssistant):
    """Verify daily generation runs on independent 15-min timer and retries in 5 min on failure (#324)."""
    config = {
        sensor.CONF_NAME: "Test Inverter",
        sensor.CONF_DEVICEID: "DEV_TEST",
        sensor.CONF_DEVICESN: "SN_TEST_DAILY",
        sensor.CONF_APIKEY: "key_test",
    }
    mock_add = MagicMock()
    with patch("custom_components.foxess.sensor.DataUpdateCoordinator.async_refresh", new_callable=AsyncMock):
        await sensor._async_setup_foxess(hass, config, mock_add)

    coordinator = mock_add.call_args[0][0][0].coordinator
    update_data = coordinator.update_method

    with patch("custom_components.foxess.sensor.getOADeviceDetail", return_value=sensor.FetchResult.OK) as mock_detail, \
         patch("custom_components.foxess.sensor.getRaw", return_value=sensor.FetchResult.OK) as mock_raw, \
         patch("custom_components.foxess.sensor.getReport", return_value=sensor.FetchResult.OK) as mock_report, \
         patch("custom_components.foxess.sensor.getReportDailyGeneration", return_value=sensor.FetchResult.ERROR) as mock_gen, \
         patch("custom_components.foxess.sensor.waitforAPI", new_callable=AsyncMock):

        def side_effect_detail(h, allData, sn, key):
            allData["addressbook"]["status"] = "1"
            return sensor.FetchResult.OK
        mock_detail.side_effect = side_effect_detail

        # First run (startup, t=0): daily gen runs, fails with FetchResult.ERROR
        # But online must remain True (never pull down inverter online status)
        data = await update_data()
        assert mock_gen.call_count == 1
        assert data["online"] is True

        # Minutes 1, 2, 3, 4: daily gen should NOT run (retry after 5 min)
        for _ in range(4):
            await update_data()
        assert mock_gen.call_count == 1

        # Minute 5: retry should trigger
        mock_gen.return_value = sensor.FetchResult.OK
        await update_data()
        assert mock_gen.call_count == 2

        # After success, next run is in 15 minutes (so not called for next 14 ticks)
        for _ in range(14):
            await update_data()
        assert mock_gen.call_count == 2

        # 15th tick after success: triggers again!
        await update_data()
        assert mock_gen.call_count == 3


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_daily_generation_not_blocked_by_raw_or_report_failure(hass: HomeAssistant):
    """Verify daily generation is fetched even if getRaw or getReport fails (#324)."""
    config = {
        sensor.CONF_NAME: "Test Inverter",
        sensor.CONF_DEVICEID: "DEV_TEST2",
        sensor.CONF_DEVICESN: "SN_TEST_DAILY2",
        sensor.CONF_APIKEY: "key_test",
    }
    mock_add = MagicMock()
    with patch("custom_components.foxess.sensor.DataUpdateCoordinator.async_refresh", new_callable=AsyncMock):
        await sensor._async_setup_foxess(hass, config, mock_add)

    coordinator = mock_add.call_args[0][0][0].coordinator
    update_data = coordinator.update_method

    with patch("custom_components.foxess.sensor.getOADeviceDetail", return_value=sensor.FetchResult.OK) as mock_detail, \
         patch("custom_components.foxess.sensor.getRaw", return_value=sensor.FetchResult.ERROR) as mock_raw, \
         patch("custom_components.foxess.sensor.getReportDailyGeneration", return_value=sensor.FetchResult.OK) as mock_gen, \
         patch("custom_components.foxess.sensor.waitforAPI", new_callable=AsyncMock):

        def side_effect_detail(h, allData, sn, key):
            allData["addressbook"]["status"] = "1"
            return sensor.FetchResult.OK
        mock_detail.side_effect = side_effect_detail

        await update_data()
        # Even though getRaw failed, daily generation must have been called
        assert mock_gen.call_count == 1



