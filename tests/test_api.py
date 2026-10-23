"""Tests for FoxESS native aiohttp API client."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientError

from custom_components.foxess.api import FoxESSApiClient, GetAuth
from custom_components.foxess.const import (
    _AUTH_ERRNO,
    FetchResult,
)


def test_get_auth_headers_and_md5():
    """Verify GetAuth builds valid signature headers and MD5 hashes."""
    auth = GetAuth()
    headers = auth.get_signature("test_token", "/op/v0/device/detail")

    assert headers["token"] == "test_token"
    assert "timestamp" in headers
    assert "signature" in headers
    assert headers["Content-Type"] == "application/json"
    assert len(headers["signature"]) == 32

    # MD5 lower and upper
    assert auth.md5c("hello", "lower") == "5d41402abc4b2a76b9719d911017c592"
    assert auth.md5c("hello", "upper") == "5D41402ABC4B2A76B9719D911017C592"


@pytest.mark.asyncio
async def test_api_client_success():
    """Verify successful API request returns FetchResult.OK and payload."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"errno": 0, "msg": "success", "result": {"foo": "bar"}})

    mock_session = MagicMock()
    mock_session.request.return_value.__aenter__.return_value = mock_resp

    client = FoxESSApiClient(session=mock_session)
    res, data, elapsed = await client.async_request("POST", "/op/v0/test", "token123", json_data={"test": 1})

    assert res == FetchResult.OK
    assert data == {"errno": 0, "msg": "success", "result": {"foo": "bar"}}
    assert elapsed >= 0


@pytest.mark.asyncio
async def test_api_client_http_401():
    """Verify HTTP 401 returns FetchResult.AUTH_FAILED."""
    mock_resp = AsyncMock()
    mock_resp.status = 401

    mock_session = MagicMock()
    mock_session.request.return_value.__aenter__.return_value = mock_resp

    client = FoxESSApiClient(session=mock_session)
    res, data, _ = await client.async_request("GET", "/op/v0/test", "invalid_key")

    assert res == FetchResult.AUTH_FAILED
    assert data is None


@pytest.mark.asyncio
async def test_api_client_auth_errno():
    """Verify auth errno in response body returns FetchResult.AUTH_FAILED."""
    for errno in _AUTH_ERRNO:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"errno": errno, "msg": "invalid key"})

        mock_session = MagicMock()
        mock_session.request.return_value.__aenter__.return_value = mock_resp

        client = FoxESSApiClient(session=mock_session)
        res, data, _ = await client.async_request("POST", "/op/v0/test", "bad_token")

        assert res == FetchResult.AUTH_FAILED
        assert data["errno"] == errno


@pytest.mark.asyncio
async def test_api_client_timestamp_error_not_auth_failed():
    """Verify errno 40256 (illegal timestamp) returns FetchResult.ERROR, not AUTH_FAILED."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={"errno": 40256, "msg": "Parameter could not be parsed correctly illegal timestamp"}
    )

    mock_session = MagicMock()
    mock_session.request.return_value.__aenter__.return_value = mock_resp

    client = FoxESSApiClient(session=mock_session)
    res, data, _ = await client.async_request("POST", "/op/v0/test", "token")

    assert res == FetchResult.ERROR
    assert data["errno"] == 40256


def test_default_timeout_within_timestamp_window():
    """DEFAULT_TIMEOUT must be shorter than the ~60s OpenAPI timestamp validation window."""
    from custom_components.foxess.const import DEFAULT_TIMEOUT

    assert DEFAULT_TIMEOUT <= 55


@pytest.mark.asyncio
async def test_api_client_network_error():
    """Verify network ClientError or Timeout returns FetchResult.ERROR."""
    mock_session = MagicMock()
    mock_session.request.return_value.__aenter__.side_effect = ClientError("Connection failed")

    client = FoxESSApiClient(session=mock_session)
    res, data, _ = await client.async_request("GET", "/op/v0/test", "token")

    assert res == FetchResult.ERROR
    assert data is None


@pytest.mark.asyncio
async def test_api_client_high_level_methods():
    """Verify high-level helper methods route to proper paths and payloads."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"errno": 0, "msg": "success", "result": {}})

    mock_session = MagicMock()
    mock_session.request.return_value.__aenter__.return_value = mock_resp

    client = FoxESSApiClient(session=mock_session)

    # get_device_detail
    res, _, _ = await client.async_get_device_detail("SN123", "key", v1_api=True)
    assert res == FetchResult.OK
    call_args = mock_session.request.call_args
    assert call_args[0][0] == "GET"
    assert "sn=SN123" in call_args[0][1]

    # get_device_list
    res, _, _ = await client.async_get_device_list("key", page=1, page_size=10)
    assert res == FetchResult.OK
    call_args = mock_session.request.call_args
    assert call_args[0][0] == "POST"
    assert call_args[1]["json"] == {"currentPage": 1, "pageSize": 10}

    # get_daily_generation
    res, _, _ = await client.async_get_daily_generation("SN123", "key")
    assert res == FetchResult.OK
    call_args = mock_session.request.call_args
    assert call_args[0][0] == "GET"
    assert "sn=SN123" in call_args[0][1]

    # get_real_data (v1)
    res, _, _ = await client.async_get_real_data("SN123", "key", ["pvPower", "SoC"], v1_api=True)
    assert res == FetchResult.OK
    call_args = mock_session.request.call_args
    assert call_args[0][0] == "POST"
    assert call_args[1]["json"] == {"sns": ["SN123"], "variables": ["pvPower", "SoC"]}

    # get_real_data (v0)
    res, _, _ = await client.async_get_real_data("SN123", "key", ["pvPower", "SoC"], v1_api=False)
    assert res == FetchResult.OK
    call_args = mock_session.request.call_args
    assert call_args[0][0] == "POST"
    assert call_args[1]["json"] == {"sn": "SN123", "variables": ["pvPower", "SoC"]}
