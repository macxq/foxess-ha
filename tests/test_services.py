"""Tests for FoxESS domain services."""
import pytest
from unittest.mock import AsyncMock, patch
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.foxess.const import DOMAIN, FetchResult
from custom_components.foxess import async_setup_services


@pytest.mark.asyncio
async def test_set_schedule_service_call(hass):
    """Test calling foxess.set_schedule with auto-enable flag."""
    coordinator = AsyncMock()
    coordinator.data = {"addressbook": {"hasBattery": True}}
    coordinator.devicesn = "SN123"
    coordinator.apiKey = "TEST_KEY"

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"deviceSN": "SN123", "apiKey": "TEST_KEY", "has_battery": True},
        entry_id="mock_entry",
    )
    with patch.dict(
        hass.data,
        {
            DOMAIN: {
                entry.entry_id: {
                    "coordinator": coordinator,
                    "apiKey": "TEST_KEY",
                    "deviceSN": "SN123",
                }
            }
        },
    ):
        async_setup_services(hass)
        assert hass.services.has_service(DOMAIN, "set_schedule")

        with patch("custom_components.foxess.FoxESSApiClient.async_set_scheduler_groups", new_callable=AsyncMock) as mock_groups, \
             patch("custom_components.foxess.FoxESSApiClient.async_set_scheduler_flag", new_callable=AsyncMock) as mock_flag:
            mock_groups.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 40.0)
            mock_flag.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 40.0)

            groups = [{"enable": 1, "startHour": 1, "workMode": "ForceCharge"}]
            await hass.services.async_call(
                DOMAIN,
                "set_schedule",
                {
                    "device_sn": "SN123",
                    "groups": groups,
                    "enable": True,
                },
                blocking=True,
            )

            mock_groups.assert_called_once_with("SN123", "TEST_KEY", groups, False)
            mock_flag.assert_called_once_with("SN123", "TEST_KEY", True)
            assert coordinator.data["schedulerGroups"] == groups
            assert coordinator.data["schedulerEnabled"] is True
            coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_set_schedule_service_unknown_device(hass):
    """Test calling foxess.set_schedule with unknown device SN raises error."""
    with patch.dict(hass.data, {DOMAIN: {}}):
        async_setup_services(hass)
        with pytest.raises(HomeAssistantError, match="FoxESS device with SN 'UNKNOWN' not found"):
            await hass.services.async_call(
                DOMAIN,
                "set_schedule",
                {
                    "device_sn": "UNKNOWN",
                    "groups": [],
                },
                blocking=True,
            )


@pytest.mark.asyncio
async def test_set_schedule_service_api_error(hass):
    """Test calling foxess.set_schedule when API returns an error."""
    coordinator = AsyncMock()
    coordinator.data = {}
    coordinator.devicesn = "SN123"
    coordinator.apiKey = "TEST_KEY"

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"deviceSN": "SN123", "apiKey": "TEST_KEY"},
        entry_id="mock_entry",
    )
    with patch.dict(
        hass.data,
        {
            DOMAIN: {
                entry.entry_id: {
                    "coordinator": coordinator,
                    "apiKey": "TEST_KEY",
                }
            }
        },
    ):
        async_setup_services(hass)
        with patch("custom_components.foxess.FoxESSApiClient.async_set_scheduler_groups", new_callable=AsyncMock) as mock_groups:
            mock_groups.return_value = (FetchResult.ERROR, {"errno": 40256, "msg": "illegal timestamp"}, 40.0)
            with pytest.raises(HomeAssistantError, match="Failed to set scheduler groups"):
                await hass.services.async_call(
                    DOMAIN,
                    "set_schedule",
                    {
                        "device_sn": "SN123",
                        "groups": [{"workMode": "SelfUse"}],
                    },
                    blocking=True,
                )
