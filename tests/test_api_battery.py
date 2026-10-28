from unittest.mock import AsyncMock, patch
import pytest
from custom_components.foxess.api import FoxESSApiClient, FetchResult


@pytest.mark.asyncio
async def test_api_set_battery_soc():
    client = FoxESSApiClient()
    with patch.object(client, "async_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 120.0)
        res, data, _ = await client.async_set_battery_soc("SN123", "TOKEN", 15, 20)
        assert res == FetchResult.OK
        mock_req.assert_called_once_with(
            "POST",
            "/op/v0/device/battery/soc/set",
            "TOKEN",
            json_data={"sn": "SN123", "minSoc": 15, "minSocOnGrid": 20},
        )


@pytest.mark.asyncio
async def test_api_set_and_get_work_mode():
    client = FoxESSApiClient()
    with patch.object(client, "async_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 100.0)
        res, _, _ = await client.async_set_work_mode("SN123", "TOKEN", "SelfUse")
        assert res == FetchResult.OK
        mock_req.assert_called_with(
            "POST",
            "/op/v0/device/setting/set",
            "TOKEN",
            json_data={"sn": "SN123", "key": "WorkMode", "value": "SelfUse"},
        )

        res, _, _ = await client.async_get_work_mode("SN123", "TOKEN")
        assert res == FetchResult.OK
        mock_req.assert_called_with(
            "POST",
            "/op/v0/device/setting/get",
            "TOKEN",
            json_data={"sn": "SN123", "key": "WorkMode"},
        )


@pytest.mark.asyncio
async def test_api_scheduler_flag_and_groups():
    client = FoxESSApiClient()
    with patch.object(client, "async_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 100.0)
        res, _, _ = await client.async_set_scheduler_flag("SN123", "TOKEN", True)
        assert res == FetchResult.OK
        mock_req.assert_called_with(
            "POST",
            "/op/v1/device/scheduler/set/flag",
            "TOKEN",
            json_data={"deviceSN": "SN123", "enable": 1},
        )

        res, _, _ = await client.async_set_scheduler_flag("SN123", "TOKEN", False)
        assert res == FetchResult.OK
        mock_req.assert_called_with(
            "POST",
            "/op/v1/device/scheduler/set/flag",
            "TOKEN",
            json_data={"deviceSN": "SN123", "enable": 0},
        )

        res, _, _ = await client.async_get_scheduler_flag("SN123", "TOKEN")
        assert res == FetchResult.OK
        mock_req.assert_called_with(
            "POST",
            "/op/v1/device/scheduler/get/flag",
            "TOKEN",
            json_data={"deviceSN": "SN123"},
        )

        groups = [{"enable": 1, "startHour": 1, "workMode": "ForceCharge"}]
        res, _, _ = await client.async_set_scheduler_groups(
            "SN123", "TOKEN", groups, is_default=False
        )
        assert res == FetchResult.OK
        mock_req.assert_called_with(
            "POST",
            "/op/v2/device/scheduler/enable",
            "TOKEN",
            json_data={"deviceSN": "SN123", "isDefault": False, "groups": groups},
        )

        res, _, _ = await client.async_get_scheduler_groups("SN123", "TOKEN")
        assert res == FetchResult.OK
        mock_req.assert_called_with(
            "POST",
            "/op/v2/device/scheduler/get",
            "TOKEN",
            json_data={"deviceSN": "SN123"},
        )


@pytest.mark.asyncio
async def test_api_get_battery_soc():
    client = FoxESSApiClient()
    with patch.object(client, "async_get_battery_settings", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = (FetchResult.OK, {"errno": 0, "result": {"minSoc": 10}}, 100.0)
        res, data, _ = await client.async_get_battery_soc("SN123", "TOKEN")
        assert res == FetchResult.OK
        mock_get.assert_called_once_with("SN123", "TOKEN")


@pytest.mark.asyncio
async def test_api_force_charge_times():
    client = FoxESSApiClient()
    with patch.object(client, "async_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = (FetchResult.OK, {"errno": 0, "msg": "success"}, 100.0)
        res, _, _ = await client.async_get_force_charge_times("SN123", "TOKEN")
        assert res == FetchResult.OK
        mock_req.assert_called_with(
            "GET",
            "/op/v0/device/battery/forceChargeTime/get",
            "TOKEN",
            url_override="https://www.foxesscloud.com/op/v0/device/battery/forceChargeTime/get?sn=SN123",
        )

        res, _, _ = await client.async_set_force_charge_times(
            "SN123",
            "TOKEN",
            start_time_1={"hour": 2, "minute": 0},
            end_time_1={"hour": 5, "minute": 0},
            enable_1=True,
            start_time_2={"hour": 14, "minute": 30},
            end_time_2={"hour": 16, "minute": 0},
            enable_2=False,
        )
        assert res == FetchResult.OK
        mock_req.assert_called_with(
            "POST",
            "/op/v0/device/battery/forceChargeTime/set",
            "TOKEN",
            json_data={
                "sn": "SN123",
                "enable1": 1,
                "enable2": 0,
                "startTime1": {"hour": 2, "minute": 0},
                "endTime1": {"hour": 5, "minute": 0},
                "startTime2": {"hour": 14, "minute": 30},
                "endTime2": {"hour": 16, "minute": 0},
            },
        )
