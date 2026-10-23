# Releases

## [v0.58]
```yaml
title: "v0.58 - Fix Transient Illegal Timestamp (errno 40256) Polling Stall (#394)"
date: "2026-10-23"
```

### 🐛 Fix Transient Illegal Timestamp (errno 40256) (#394)

• **Treat 40256 as Transient Error**: Removed errno `40256` (*illegal timestamp*) from `_AUTH_ERRNO`. Transient clock skew or FoxESS Cloud response delays during peak hours no longer trigger `ConfigEntryAuthFailed` or permanently stall polling with "Authentication expired".
• **Automatic Polling Recovery**: When FoxESS Cloud delays requests or returns `40256`, the integration logs a warning and automatically retries on the next poll cycle without requiring manual integration reload or Home Assistant restart.
• **Reduced Client Timeout**: Decreased `DEFAULT_TIMEOUT` from 75 s to 50 s to ensure slow requests time out locally before exceeding the FoxESS OpenAPI ~60 s server timestamp signature tolerance window.
• **Config Flow Clarification**: OpenAPI errno `40256` during device setup now maps to `cannot_connect` instead of misleading `invalid_auth`.

## [v0.57]
```yaml
title: "v0.57 - Battery Residual Energy Device Class Fix (#390)"
date: "2026-10-23"
```

### 🔋 Battery Residual Energy Device Class Fix (#390)

• **Updated Device Class to `ENERGY_STORAGE`**: Resolved Home Assistant Core startup warning (`state class 'measurement' which is impossible considering device class ('energy')`) on `sensor.foxess_residual_energy`.
• **Home Assistant Compliance**: `FoxESSResidualEnergy` now uses `SensorDeviceClass.ENERGY_STORAGE` (with graceful fallback for older HA installations), which properly represents stored battery energy in kWh with `SensorStateClass.MEASUREMENT`.
• **Entity Rule Audit**: Added comprehensive test coverage auditing all 27 entity classes across the integration to guarantee strict adherence to Home Assistant Core `DEVICE_CLASS_STATE_CLASSES` and `DEVICE_CLASS_UNITS`.

## [v0.56]
```yaml
title: "v0.56 - Native aiohttp Client & cloud_polling Refactor (#389)"
date: "2026-10-23"
```

### 🚀 Native aiohttp Client & Modernized Cloud Architecture (#389)

• **Native aiohttp Session**: Replaced legacy synchronous `RestData` objects across all 6 FoxESS OpenAPI endpoints (`getOADeviceDetail`, `getOADeviceList`, `getOABatterySettings`, `getReport`, `getReportDailyGeneration`, and `getRaw`) with Home Assistant's native `async_get_clientsession(hass)` in a centralized `FoxESSApiClient`.
• **Metadata Classification**: Updated `iot_class` to `cloud_polling` and removed unnecessary `rest` core dependency in `manifest.json`.
• **Centralized Architecture (`api.py` & `const.py`)**: Extracted all API endpoints, configuration constants, HTTP headers, MD5 signature generation (`GetAuth`), token handling, rate limiting (`wait_for_api`), and error/errno code mapping into reusable modules.
• **Preserved Reliability**: Retains all existing entity unique IDs, device grouping, age and offset checks, energy decay prevention, and daily generation resilience features (#324).
• **Full Backward Compatibility**: Fully backwards compatible with existing YAML and UI config entries.
• **Test Suite**: Added comprehensive unit test coverage for `FoxESSApiClient` (`tests/test_api.py`) and updated test suite to verify 65/65 passing tests.
