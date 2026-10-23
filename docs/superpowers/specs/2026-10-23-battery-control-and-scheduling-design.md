# Design Specification: FoxESS Battery Control and Mode Scheduling

**Date:** 2026-10-23  
**Status:** Approved by Reviewer & Ready for User Approval  
**Target Component:** `custom_components/foxess`  

---

## 1. Intent and The Why

Battery storage management is the most requested feature in the history of `macxq/foxess-ha` (tracking back to Issue #19 in early 2022). Users need the ability to control battery charging schedules, work modes, and minimum State of Charge (SoC) thresholds—primarily to charge their batteries from the grid during cheap electricity hours (e.g. night tariffs, G12/G12w, Nord Pool, Octopus Agile) and protect stored energy during peak periods.

Due to the absence of these controls in upstream `macxq/foxess-ha`, multiple community forks (`oliverclarke`, `sambtc94`) and standalone integrations (`nickw444/ha-foxess-cloud`, `nicois/foxess-control`) emerged. However, these forks either stripped out automated release pipelines and test suites, used fragile raw HTTP requests outside the modern async API client, or introduced clutter on solar-only (PV) inverters.

The intent of this project is to implement a robust, stable base for battery and work mode control directly in `macxq/foxess-ha`, maintaining full test coverage, async coordinator architecture, and clean auto-detection so solar-only users are unaffected. This base will also provide the foundational `foxess.set_schedule` service required for subsequent automated smart tariff charging.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Work Mode Selection (`select`):** Provide a `select` entity allowing users to switch the inverter between supported modes: `Self-Use`, `Feed-in`, `Backup`, and `Peak Shaving` (with `ForceCharge` and `ForceDischarge` supported as read/state options).
- **Battery SoC Limits (`number`):** Provide slider/box number entities for `Min SoC` (reserve discharge cut-off) and `Min SoC on Grid` (grid charge cut-off) with smart cross-value clamping.
- **Scheduler Toggle (`switch`):** Provide a `switch` entity to enable or disable the inverter's internal mode scheduler.
- **Schedule Management Service (`foxess.set_schedule`):** Implement a registered Home Assistant service accepting a target inverter, a list of time groups (start/end time, work mode, `fdPwr`, `fdSoc`, etc.), and an auto-enable flag for seamless automations.
- **Conditional Entity Creation & Persistence:** Automatically detect whether an inverter has a battery installed (`hasBattery`). Persist `has_battery` in the config entry so restarts during nighttime/offline states never drop entities. On PV-only (grid-tied) inverters, suppress battery and scheduler entities completely.
- **Architectural Integrity:** Migrate coordinator ownership to `__init__.py` so that all platforms (`sensor`, `select`, `number`, `switch`) share a single polling instance and unified `DeviceInfo`.
- **Quality & Testing:** 100% test coverage on newly introduced platforms, API client methods, and service handlers using `pytest` and Home Assistant test fixtures.

### Non-Goals
- **Local Modbus Control:** This integration communicates strictly via the official FoxESS Cloud OpenAPI. Local Modbus RS485 / TCP control is handled by separate local integrations (e.g. `foxess_modbus`).
- **Complex UI Dashboards:** Custom Lovelace cards or multi-period scheduler UI editors in frontend cards are out of scope for this foundation; users can manage basic entities via standard HA cards and automations via services.
- **Automated Price Optimization Engine (Phase 2):** Smart charge calculation based on Nord Pool or Amber tariffs will be built on top of this stable base in a subsequent feature branch.

### Anti-Goals
- **API Quota Exhaustion:** FoxESS Cloud limits accounts to ~1440 calls/day. We must never spam API endpoints on slider drag or poll settings excessively.
- **Regressions on PV-Only Systems:** Inverters without batteries must not show unavailable battery entities or produce error traces in HA logs.
- **Blocking the Event Loop:** No synchronous I/O or `rest.data` calls. All outbound network requests must go through `FoxESSApiClient` via `aiohttp`.

---

## 3. Constraints

1. **FoxESS Cloud OpenAPI Rules:**
   - 1-second delay between queries (guarded by `wait_for_api()` in `api.py`).
   - MD5 request signature header (`token`, `timestamp`, `signature`, `lang`).
   - Read & write endpoints expect HTTP `POST` with JSON bodies and return `{errno: 0, msg: "success"}` on success.
2. **Home Assistant Architecture Guidelines:**
   - Entities must link to the inverter device via `device_info` with identifier `(DOMAIN, deviceSN)` or `(DOMAIN, deviceID)`.
   - Settings changes must optimistically update local coordinator state and request an async refresh.
   - Platform setups must adhere to `async_setup_entry`.

---

## 4. Decisions & Rationale

| Decision | Decided By | Details / Rationale |
|---|---|---|
| **Stable base first** | User | Focus on clean entity controls, services, and tests before building dynamic tariff automation. |
| **No entities on PV-only systems** | User | Check `hasBattery`. If `False`, do not register `select`, `number`, or `switch` entities. |
| **Startup Offline Resilience** | Antigravity Call | Persist `has_battery` in `ConfigEntry.data`. If initial refresh fails due to cloud outage, raise `ConfigEntryNotReady`. |
| **HTTP POST for Read/Write** | Antigravity Call | Use HTTP `POST` for `/op/v0/device/setting/get`, `/op/v1/device/scheduler/get/flag`, and `/op/v2/device/scheduler/get` per FoxESS Cloud OpenAPI schema. |
| **Auto-Enable in `set_schedule`** | Antigravity Call | Service defaults to `enable: true`, calling `/op/v2/device/scheduler/enable` AND ensuring the scheduler flag is set via `/op/v1/device/scheduler/set/flag`. |
| **WorkMode / Schedule Guard** | Antigravity Call | Raising `HomeAssistantError` if a user attempts to change static Work Mode while Mode Scheduler switch is enabled. Include `ForceCharge`/`ForceDischarge` in available read modes. |
| **SoC Cross-Entity Clamping** | Antigravity Call | In `number.py`, enforce `minSoc <= minSocOnGrid` before sending to `/op/v0/device/battery/soc/set` to prevent cloud error 40xxx. |
| **Coordinator Migration** | Antigravity Call | Move coordinator lifecycle to `__init__.py` so `sensor`, `select`, `number`, and `switch` share a single instance stored in `hass.data[DOMAIN][entry.entry_id]`. |

---

## 5. Technical Specifications

### 5.1 API Client Extensions (`api.py`)

All endpoints use HTTP `POST` with standard signature headers:
- `async_set_battery_soc(sn: str, token: str, min_soc: int, min_soc_on_grid: int) -> tuple[FetchResult, dict, float]`
  - Endpoint: `POST /op/v0/device/battery/soc/set`
  - Payload: `{"sn": sn, "minSoc": min_soc, "minSocOnGrid": min_soc_on_grid}`
- `async_get_battery_soc(sn: str, token: str) -> tuple[FetchResult, dict, float]`
  - Endpoint: `GET /op/v0/device/battery/soc/get?sn={sn}`
- `async_set_work_mode(sn: str, token: str, mode: str) -> tuple[FetchResult, dict, float]`
  - Endpoint: `POST /op/v0/device/setting/set`
  - Payload: `{"sn": sn, "key": "WorkMode", "value": mode}`
- `async_get_work_mode(sn: str, token: str) -> tuple[FetchResult, dict, float]`
  - Endpoint: `POST /op/v0/device/setting/get`
  - Payload: `{"sn": sn, "key": "WorkMode"}`
- `async_set_scheduler_flag(sn: str, token: str, enabled: bool) -> tuple[FetchResult, dict, float]`
  - Endpoint: `POST /op/v1/device/scheduler/set/flag`
  - Payload: `{"deviceSN": sn, "enable": 1 if enabled else 0}`
- `async_get_scheduler_flag(sn: str, token: str) -> tuple[FetchResult, dict, float]`
  - Endpoint: `POST /op/v1/device/scheduler/get/flag`
  - Payload: `{"deviceSN": sn}`
- `async_set_scheduler_groups(sn: str, token: str, groups: list[dict], is_default: bool = False) -> tuple[FetchResult, dict, float]`
  - Endpoint: `POST /op/v2/device/scheduler/enable`
  - Payload: `{"deviceSN": sn, "isDefault": is_default, "groups": groups}`
- `async_get_scheduler_groups(sn: str, token: str) -> tuple[FetchResult, dict, float]`
  - Endpoint: `POST /op/v2/device/scheduler/get`
  - Payload: `{"deviceSN": sn}`

### 5.2 Coordinator Architecture (`__init__.py` & `sensor.py`)

- `__init__.py`:
  - `PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.NUMBER, Platform.SWITCH]`
  - In `async_setup_entry`:
    - Instantiate the shared `DataUpdateCoordinator` and store in `hass.data[DOMAIN][entry.entry_id]`.
    - Perform initial refresh. If it fails with communication error, raise `ConfigEntryNotReady`.
    - Detect `hasBattery` from device detail. Persist in `entry.data["has_battery"]` via `async_update_entry`.
    - Forward setup to `PLATFORMS`.
    - Register domain services (`foxess.set_schedule`).
  - In `async_unload_entry`:
    - Unload all platforms.
    - Remove services if this was the last active entry.

### 5.3 Entity Platforms

1. **`select.py` (Work Mode):**
   - Options: `["Self-Use", "Feed-in", "Backup", "Peak Shaving"]` (with `ForceCharge` and `ForceDischarge` accepted for read state).
   - Entity Name: `{Device Name} - Work Mode`
   - Icon: `mdi:battery-sync`
   - Guard: If `schedulerEnabled` is True, reject changes with a friendly `HomeAssistantError`.
   - Setup: Only registered if `has_battery` is True.

2. **`number.py` (Min SoC / Min SoC on Grid):**
   - `FoxESSBatMinSoCNumber`: Min SoC (10–100%, step 1). Icon `mdi:battery-low`.
   - `FoxESSBatMinSoCOnGridNumber`: Min SoC on Grid (10–100%, step 1). Icon `mdi:battery-arrow-up`.
   - Clamping: Automatically clamps companion value so `minSoc <= minSocOnGrid` before sending.
   - Setup: Only registered if `has_battery` is True.

3. **`switch.py` (Scheduler Enable):**
   - Entity Name: `{Device Name} - Mode Scheduler`
   - Icon: `mdi:calendar-clock`
   - Controls `/op/v1/device/scheduler/set/flag`.
   - Exposes attributes: current schedule groups.
   - Setup: Only registered if `has_battery` is True.

### 5.4 Service Definition (`services.yaml`)

```yaml
set_schedule:
  name: Set schedule
  description: Overwrite the FoxESS inverter mode schedule with configured time segments.
  fields:
    device_sn:
      name: Inverter serial number
      description: The FoxESS deviceSN to apply the schedule to.
      required: true
      example: "60BH1234567"
      selector:
        text:
    groups:
      name: Schedule groups
      description: List of time segment dictionaries matching FoxESS OpenAPI schema.
      required: true
      example:
        - enable: 1
          startHour: 1
          startMinute: 0
          endHour: 5
          endMinute: 0
          workMode: ForceCharge
          minSocOnGrid: 20
          fdSoc: 90
          fdPwr: 3000
      selector:
        object:
    enable:
      name: Enable scheduler
      description: Automatically ensure the inverter mode scheduler master switch is enabled.
      required: false
      default: true
      selector:
        boolean:
    is_default:
      name: Set as default
      description: Mark this schedule configuration as default.
      required: false
      default: false
      selector:
        boolean:
```

### 5.5 Testing Strategy

Create dedicated test modules under `tests/`:
- `tests/test_api_battery.py`: Tests for all new `FoxESSApiClient` methods with mock HTTP responses (success, auth failure, rate limit, error errno).
- `tests/test_select.py`: Test `FoxESSWorkModeSelect` reading state, setting options, handling active schedule errors.
- `tests/test_number.py`: Test `FoxESSBatMinSoCNumber` and `FoxESSBatMinSoCOnGridNumber` state reporting, clamping logic, and API calls.
- `tests/test_switch.py`: Test `FoxESSSchedulerSwitch` turning on/off and reporting schedule attributes.
- `tests/test_services.py`: Test `foxess.set_schedule` service registration, auto-enable flag, validation, and API invocation.
- `tests/test_battery_filtering.py`: Verify that when `hasBattery=False`, zero control entities are added to Home Assistant.

---

## 6. What's Left to the Builder

- Exact step precision and icon variations for number entities if custom models report different ranges.
- Translation keys for Polish (`pl.json`) and English (`en.json`) for entity names and options.
- Specific polling cadence adjustments for battery settings (default: 60 minutes or upon write refresh).
