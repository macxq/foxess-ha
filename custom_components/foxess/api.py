"""FoxESS Cloud OpenAPI client using native aiohttp."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

import aiohttp
from aiohttp import ClientError, ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    _AUTH_ERRNO,
    _ENDPOINT_OA_BATTERY_SETTINGS,
    _ENDPOINT_OA_BATTERY_SOC_SET,
    _ENDPOINT_OA_DAILY_GENERATION,
    _ENDPOINT_OA_DEVICE_DETAIL,
    _ENDPOINT_OA_DEVICE_DETAIL_V1,
    _ENDPOINT_OA_DEVICE_LIST,
    _ENDPOINT_OA_DEVICE_VARIABLES,
    _ENDPOINT_OA_DEVICE_VARIABLES_V1,
    _ENDPOINT_OA_DOMAIN,
    _ENDPOINT_OA_REPORT,
    _ENDPOINT_OA_SCHEDULER_ENABLE,
    _ENDPOINT_OA_SCHEDULER_FLAG_GET,
    _ENDPOINT_OA_SCHEDULER_FLAG_SET,
    _ENDPOINT_OA_SCHEDULER_GET,
    _ENDPOINT_OA_SETTING_GET,
    _ENDPOINT_OA_SETTING_SET,
    DEFAULT_TIMEOUT,
    FetchResult,
)

_LOGGER = logging.getLogger(__name__)
_DEFAULT_CLIENT: FoxESSApiClient | None = None


async def waitforAPI() -> None:
    """Rate limit guard: FoxESS OpenAPI enforces a 1-second delay between queries."""
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = FoxESSApiClient()
    await _DEFAULT_CLIENT.wait_for_api()


class GetAuth:
    """FoxESS OpenAPI authentication header builder."""

    def get_signature(self, token: str, path: str, lang: str = "en") -> dict[str, str]:
        """Generate authentication headers consisting of path, token, and timestamp."""
        timestamp = round(time.time() * 1000)
        signature = rf"{path}\r\n{token}\r\n{timestamp}"
        return {
            "token": token,
            "lang": lang,
            "timestamp": str(timestamp),
            "Content-Type": "application/json",
            "signature": self.md5c(text=signature),
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Connection": "close",
        }

    @staticmethod
    def md5c(text: str = "", _type: str = "lower") -> str:
        """MD5 hash helper."""
        res = hashlib.md5(text.encode(encoding="UTF-8")).hexdigest()
        return res if _type == "lower" else res.upper()


class FoxESSApiClient:
    """Client for FoxESS OpenAPI communicating via aiohttp."""

    def __init__(
        self,
        hass: HomeAssistant | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialise the FoxESS API client."""
        self._hass = hass
        self._session = session
        self._last_api_time: float = 0.0
        self._lock = asyncio.Lock()
        self._auth = GetAuth()

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get or obtain the aiohttp ClientSession."""
        if self._session is not None:
            if getattr(self._session, "closed", False) is not True:
                return self._session
        if self._hass is not None:
            self._session = async_get_clientsession(self._hass)
            return self._session
        raise RuntimeError("No aiohttp ClientSession or HomeAssistant instance available.")

    async def wait_for_api(self) -> None:
        """Rate limit guard: FoxESS OpenAPI enforces a 1-second delay between queries."""
        async with self._lock:
            now = time.time()
            last = self._last_api_time
            diff = now - last if last != 0 else 1.0
            diff = round(diff + 0.2, 2)
            if diff < 1.0:
                await asyncio.sleep(diff)
                _LOGGER.debug("FoxESS API enforced delay, waited: %s s", diff)
            self._last_api_time = time.time()

    async def async_request(
        self,
        method: str,
        path: str,
        token: str,
        url_override: str | None = None,
        json_data: dict[str, Any] | str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT,
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Execute a single FoxESS OpenAPI request with signature, timing, and rate limiting."""
        await self.wait_for_api()

        headers = self._auth.get_signature(token=token, path=path)
        url = url_override or f"{_ENDPOINT_OA_DOMAIN}{path}"

        kwargs: dict[str, Any] = {
            "headers": headers,
            "timeout": ClientTimeout(total=timeout_seconds),
        }

        if json_data is not None:
            if isinstance(json_data, str):
                kwargs["data"] = json_data
            else:
                kwargs["json"] = json_data

        t0 = time.time()
        try:
            async with self.session.request(method, url, **kwargs) as resp:
                elapsed_ms = round((time.time() - t0) * 1000)

                if resp.status == 401:
                    _LOGGER.warning("FoxESS API rejected credentials (HTTP 401)")
                    return FetchResult.AUTH_FAILED, None, elapsed_ms

                try:
                    data = await resp.json(content_type=None)
                except (json.JSONDecodeError, ClientError) as err:
                    _LOGGER.debug("FoxESS API response was not valid JSON: %s", err)
                    return FetchResult.ERROR, None, elapsed_ms

                if not isinstance(data, dict):
                    _LOGGER.debug("FoxESS API returned non-dict JSON: %r", data)
                    return FetchResult.ERROR, None, elapsed_ms

                errno = data.get("errno", -1)
                if errno != 0:
                    if errno in _AUTH_ERRNO:
                        _LOGGER.warning("FoxESS API authentication failed with errno: %s", errno)
                        return FetchResult.AUTH_FAILED, data, elapsed_ms
                    _LOGGER.debug("FoxESS API returned error response: %s", data)
                    return FetchResult.ERROR, data, elapsed_ms

                return FetchResult.OK, data, elapsed_ms

        except (TimeoutError, asyncio.TimeoutError):
            elapsed_ms = round((time.time() - t0) * 1000)
            _LOGGER.debug("Timeout connecting to FoxESS API: %s", url)
            return FetchResult.ERROR, None, elapsed_ms
        except ClientError as err:
            elapsed_ms = round((time.time() - t0) * 1000)
            err_str = str(err)
            dns_error_cls = getattr(aiohttp, "ClientConnectorDNSError", ())
            if (
                isinstance(err, dns_error_cls)
                or "DNS" in err_str
                or "getaddrinfo" in err_str
                or "Name or service not known" in err_str
                or "Timeout while contacting DNS servers" in err_str
            ):
                _LOGGER.debug("DNS error connecting to FoxESS API (%s): %s", url, err)
                return FetchResult.DNS_TIMEOUT, None, elapsed_ms
            _LOGGER.debug("Network error connecting to FoxESS API (%s): %s", url, err)
            return FetchResult.ERROR, None, elapsed_ms
        except Exception as err:
            elapsed_ms = round((time.time() - t0) * 1000)
            _LOGGER.warning("Unexpected error during FoxESS API request (%s): %s", url, err)
            return FetchResult.ERROR, None, elapsed_ms

    async def async_get_device_detail(
        self, devicesn: str, token: str, v1_api: bool = True
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Fetch device detail."""
        path = _ENDPOINT_OA_DEVICE_DETAIL_V1 if v1_api else _ENDPOINT_OA_DEVICE_DETAIL
        url = f"{_ENDPOINT_OA_DOMAIN}{path}?sn={devicesn}"
        return await self.async_request("GET", path, token, url_override=url)

    async def async_get_device_list(
        self, token: str, page: int = 1, page_size: int = 25
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Fetch device list."""
        path = _ENDPOINT_OA_DEVICE_LIST
        return await self.async_request(
            "POST", path, token, json_data={"currentPage": page, "pageSize": page_size}
        )

    async def async_get_battery_settings(
        self, devicesn: str, token: str
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Fetch battery SoC and minSoc settings."""
        path = "/op/v0/device/battery/soc/get"
        url = f"{_ENDPOINT_OA_DOMAIN}{_ENDPOINT_OA_BATTERY_SETTINGS}{devicesn}"
        return await self.async_request("GET", path, token, url_override=url)

    async def async_get_report(
        self, devicesn: str, token: str, year: int, month: int, variables: list[str]
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Fetch monthly generation report."""
        path = _ENDPOINT_OA_REPORT
        json_data = {
            "sn": devicesn,
            "year": year,
            "month": month,
            "dimension": "month",
            "variables": variables,
        }
        return await self.async_request("POST", path, token, json_data=json_data)

    async def async_get_daily_generation(
        self, devicesn: str, token: str
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Fetch daily generation statistics."""
        path = "/op/v0/device/generation"
        url = f"{_ENDPOINT_OA_DOMAIN}{_ENDPOINT_OA_DAILY_GENERATION}{devicesn}"
        return await self.async_request(
            "GET", path, token, url_override=url, json_data={"sn": devicesn, "dimension": "day"}
        )

    async def async_get_real_data(
        self,
        devicesn: str,
        token: str,
        variables: list[str] | None = None,
        v1_api: bool = True,
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Fetch real-time device variables."""
        path = _ENDPOINT_OA_DEVICE_VARIABLES_V1 if v1_api else _ENDPOINT_OA_DEVICE_VARIABLES
        json_data: dict[str, Any] = {"sns": [devicesn]} if v1_api else {"sn": devicesn}
        if variables:
            json_data["variables"] = variables
        return await self.async_request("POST", path, token, json_data=json_data)

    async def async_set_battery_soc(
        self, sn: str, token: str, min_soc: int, min_soc_on_grid: int
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Set battery Min SoC and Min SoC on Grid."""
        return await self.async_request(
            "POST",
            _ENDPOINT_OA_BATTERY_SOC_SET,
            token,
            json_data={"sn": sn, "minSoc": min_soc, "minSocOnGrid": min_soc_on_grid},
        )

    async def async_get_battery_soc(
        self, sn: str, token: str
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Fetch battery SoC and minSoc settings."""
        return await self.async_get_battery_settings(sn, token)

    async def async_set_work_mode(
        self, sn: str, token: str, mode: str
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Set inverter work mode."""
        return await self.async_request(
            "POST",
            _ENDPOINT_OA_SETTING_SET,
            token,
            json_data={"sn": sn, "key": "WorkMode", "value": mode},
        )

    async def async_get_work_mode(
        self, sn: str, token: str
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Get inverter work mode."""
        return await self.async_request(
            "POST",
            _ENDPOINT_OA_SETTING_GET,
            token,
            json_data={"sn": sn, "key": "WorkMode"},
        )

    async def async_set_scheduler_flag(
        self, sn: str, token: str, enabled: bool
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Enable or disable the mode scheduler."""
        return await self.async_request(
            "POST",
            _ENDPOINT_OA_SCHEDULER_FLAG_SET,
            token,
            json_data={"deviceSN": sn, "enable": 1 if enabled else 0},
        )

    async def async_get_scheduler_flag(
        self, sn: str, token: str
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Get the mode scheduler flag status."""
        return await self.async_request(
            "POST",
            _ENDPOINT_OA_SCHEDULER_FLAG_GET,
            token,
            json_data={"deviceSN": sn},
        )

    async def async_set_scheduler_groups(
        self, sn: str, token: str, groups: list[dict[str, Any]], is_default: bool = False
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Set mode scheduler time groups."""
        return await self.async_request(
            "POST",
            _ENDPOINT_OA_SCHEDULER_ENABLE,
            token,
            json_data={"deviceSN": sn, "isDefault": is_default, "groups": groups},
        )

    async def async_get_scheduler_groups(
        self, sn: str, token: str
    ) -> tuple[FetchResult, dict[str, Any] | None, float]:
        """Get configured mode scheduler groups."""
        return await self.async_request(
            "POST",
            _ENDPOINT_OA_SCHEDULER_GET,
            token,
            json_data={"deviceSN": sn},
        )
