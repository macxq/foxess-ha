# Releases

## [v0.60.0b1]
```yaml
title: "Battery Storage Control & Mode Scheduling Automation (Beta 1) (#19, #201, #323, #381, #401)"
date: "2026-10-27"
```

### 🔋 Battery Storage Control & Mode Scheduling Automation (Beta 1) (#19, #201, #323, #352, #360, #365, #381, #401)

- **Battery State-of-Charge (SoC) Controls (`number`)**: Added configurable number entities for `Min SoC` (reserve cut-off) and `Min SoC on Grid` (grid charge cut-off) with automatic cross-entity clamping (`Min SoC <= Min SoC on Grid`) (#19, #381).
- **Inverter Work Mode Selection (`select`)**: Added `Work Mode` select entity to switch between `Self-Use`, `Feed-in`, `Backup`, and `Peak Shaving` modes, protected with conflict prevention when schedule mode is active (#323).
- **Mode Scheduler Toggle (`switch`)**: Added `Mode Scheduler` switch to enable or disable the inverter's cloud schedule, exposing configured schedule groups and force charge times in state attributes (#201).
- **Automated Scheduling Service (`foxess.set_schedule`)**: Registered service allowing automations (e.g. night-time cheap tariff charging or dynamic price schedules) to configure schedule time segments with auto-activation.
- **Legacy & AIO Force Charge Scheduling (`foxess.set_force_charge_times`)**: Added service and endpoints (`/op/v0/device/battery/forceChargeTime/...`) for inverters like AIO-H3 and legacy models that do not use the Mode Scheduler (#352).
- **Offline Zeroing for Micro-Inverters (`show_unknown_zero`)**: Added configuration option to report `0.0` for power, current, and voltage instead of falling into `unavailable` when the micro-inverter is offline after sunset, while preserving daily energy totals (#360, #365).
- **Centralized Multi-Platform Coordinator**: Migrated update coordinator lifecycle to `__init__.py` to share a single polling instance across sensor, select, number, and switch platforms without duplicate API calls.
- **PV-Only Protection**: Inverters without batteries (`hasBattery == False`) cleanly skip creating battery and scheduling controls, leaving solar-only installations clutter-free.

## [v0.59]
```yaml
title: "Fix Solar Sensor Stale Report After Midnight (#400, #402)"
date: "2026-10-27"
```

### 🐛 Fix Solar Sensor Stale Report After Midnight (#400, #402)

- **Ignore Stale Cached Report**: In `FoxESSEnergySolar`, ignore cached daily report from previous day until a fresh report is fetched after midnight. Prevents the monotonic ratchet from locking the solar energy sensor to yesterday's cumulative total for the entire day (@atihauber).

## [v0.58]
```yaml
title: "Fix Transient Illegal Timestamp (errno 40256) & Auth Stalls (#394, #397, #398)"
date: "2026-10-26"
```

### 🐛 Fix Transient Illegal Timestamp (errno 40256) & Polling Stalls (#394, #397, #398)

- **Treat 40256 as Transient Error**: Removed errno `40256` (*illegal timestamp*) from `_AUTH_ERRNO`. Transient clock skew or FoxESS Cloud response delays during peak hours no longer trigger `ConfigEntryAuthFailed` or permanently stall polling with "Authentication expired" (#394, #397, #398).
- **Automatic Polling Recovery**: When FoxESS Cloud delays requests or returns `40256`, the integration logs a warning and automatically retries on the next poll cycle without requiring manual integration reload or Home Assistant restart.
- **Reduced Client Timeout**: Decreased `DEFAULT_TIMEOUT` from 75 s to 50 s to ensure slow requests time out locally before exceeding the FoxESS OpenAPI ~60 s server timestamp signature tolerance window.
- **Config Flow Clarification**: OpenAPI errno `40256` during device setup now maps to `cannot_connect` instead of misleading `invalid_auth`.
- **Eco Mode Report Interval**: Corrected report polling schedule in reduced API calls mode (`reduceAPICalls`) to periodically poll every 60 minutes (`tslice % 60 == 0`) as documented.

## [v0.57]
```yaml
title: "Battery Residual Energy Device Class Fix (#390)"
date: "2026-10-23"
```

### 🔋 Battery Residual Energy Device Class Fix (#390)

- **Updated Device Class to `ENERGY_STORAGE`**: Resolved Home Assistant Core startup warning (`state class 'measurement' which is impossible considering device class ('energy')`) on `sensor.foxess_residual_energy`.
- **Home Assistant Compliance**: `FoxESSResidualEnergy` now uses `SensorDeviceClass.ENERGY_STORAGE` (with graceful fallback for older HA installations), which properly represents stored battery energy in kWh with `SensorStateClass.MEASUREMENT`.
- **Entity Rule Audit**: Added comprehensive test coverage auditing all 27 entity classes across the integration to guarantee strict adherence to Home Assistant Core `DEVICE_CLASS_STATE_CLASSES` and `DEVICE_CLASS_UNITS`.

## [v0.56]
```yaml
title: "Native aiohttp Client & cloud_polling Refactor (#389)"
date: "2026-10-23"
```

### 🚀 Native aiohttp Client & Modernized Cloud Architecture (#389)

- **Native aiohttp Session**: Replaced legacy synchronous `RestData` objects across all 6 FoxESS OpenAPI endpoints (`getOADeviceDetail`, `getOADeviceList`, `getOABatterySettings`, `getReport`, `getReportDailyGeneration`, and `getRaw`) with Home Assistant's native `async_get_clientsession(hass)` in a centralized `FoxESSApiClient`.
- **Metadata Classification**: Updated `iot_class` to `cloud_polling` and removed unnecessary `rest` core dependency in `manifest.json`.
- **Centralized Architecture (`api.py` & `const.py`)**: Extracted all API endpoints, configuration constants, HTTP headers, MD5 signature generation (`GetAuth`), token handling, rate limiting (`wait_for_api`), and error/errno code mapping into reusable modules.
- **Preserved Reliability**: Retains all existing entity unique IDs, device grouping, age and offset checks, energy decay prevention, and daily generation resilience features (#324).
- **Full Backward Compatibility**: Fully backwards compatible with existing YAML and UI config entries.
- **Test Suite**: Added comprehensive unit test coverage for `FoxESSApiClient` (`tests/test_api.py`) and updated test suite to verify 65/65 passing tests.
