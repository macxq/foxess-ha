# Options Flow and YAML Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GUI Options Flow (Configure button) allowing in-place edits of FoxESS settings, and implement seamless automatic migration from legacy `configuration.yaml` into UI `ConfigEntry` objects.

**Architecture:** 
1. Implement `FoxESSOptionsFlowHandler` in `config_flow.py` exposing `apiKey`, `extendPV`, `Evo`, `xtZone`, and `Restrict`. Register update listener in `__init__.py` to reload entry on change. Merge `entry.options` into `entry.data` in `sensor.py`.
2. Implement `async_step_import` in `FoxESSConfigFlow` and dispatch `SOURCE_IMPORT` from `sensor.py`'s `async_setup_platform` when legacy YAML config is present, creating a `ConfigEntry` and issuing a persistent notification.
3. Keep unique ID consistency (`unique_id = {deviceID}{suffix}`) so all historic statistics and energy dashboards remain intact.

**Tech Stack:** Home Assistant Core (2026.10+), pytest, pytest-homeassistant-custom-component.

---

## Global Constraints

- Never break backward compatibility for existing `unique_id`s.
- `_AUTH_ERRNO` must be verified if `apiKey` is changed in options flow or imported.
- All 28 existing tests must continue to pass, with new tests added for both features.
- Translations must be updated in `strings.json` and `translations/en.json`.

## Review Focus

1. **Options reload without restart:** Verify modifying `extendPV` or `apiKey` in options updates the running coordinator without requiring a full HA restart.
2. **YAML import idempotency:** Verify subsequent HA restarts do not attempt duplicate imports or create duplicate sensors when YAML is still present.
3. **Unique ID preservation on import:** Verify imported YAML configuration uses the original `deviceID` and `deviceSN` so existing entity IDs and history are preserved.
4. **Invalid API key in Options Flow:** Verify options flow validates the API key before saving, preventing broken coordinators.
5. **Multi-inverter YAML import:** Verify multiple YAML inverters are each imported as distinct config entries.

---

### Task 1: Options Flow Implementation (`FoxESSOptionsFlowHandler`)

**Files:**
- Modify: `custom_components/foxess/config_flow.py`
- Modify: `custom_components/foxess/__init__.py`
- Modify: `custom_components/foxess/sensor.py`
- Modify: `custom_components/foxess/strings.json`
- Modify: `custom_components/foxess/translations/en.json`
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing tests for Options Flow**
  Add unit tests in `tests/test_config_flow.py`:
  - `test_options_flow_form_shown`: Verify opening options flow shows form populated with current values (`apiKey`, `extendPV`, `Evo`, `xtZone`, `Restrict`).
  - `test_options_flow_success`: Verify submitting valid options creates entry with updated values.
  - `test_options_flow_invalid_api_key`: Verify entering an invalid API key triggers validation error and re-shows form.

- [ ] **Step 2: Run test suite to verify tests fail**
  Run `.venv/bin/pytest tests/test_config_flow.py -k "options_flow"` and confirm failure.

- [ ] **Step 3: Implement `FoxESSOptionsFlowHandler` and update listener**
  - In `config_flow.py`: Define `FoxESSOptionsFlowHandler(OptionsFlow)` with `async_step_init`. Add `async_get_options_flow` to `FoxESSConfigFlow`.
  - In `__init__.py`: Register `entry.async_on_unload(entry.add_update_listener(async_reload_entry))`.
  - In `sensor.py`: In `async_setup_entry`, merge `config = {**config_entry.data, **config_entry.options}` before passing to `_async_setup_foxess`.
  - In `strings.json` and `translations/en.json`: Add `options` step definitions and descriptions.

- [ ] **Step 4: Run test suite to verify tests pass**
  Run `.venv/bin/pytest tests/ -v` and confirm all tests pass.

- [ ] **Step 5: Commit changes**
  Commit with message: `Add Options Flow for configuring FoxESS integration settings`

---

### Task 2: Automatic YAML Migration (`async_step_import`)

**Files:**
- Modify: `custom_components/foxess/config_flow.py`
- Modify: `custom_components/foxess/sensor.py`
- Modify: `custom_components/foxess/strings.json`
- Modify: `custom_components/foxess/translations/en.json`
- Test: `tests/test_config_flow.py`
- Test: `tests/test_sensor.py`

- [ ] **Step 1: Write failing tests for YAML Migration**
  - In `tests/test_config_flow.py`:
    - `test_async_step_import_success`: Test importing YAML config creates `ConfigEntry` with matching fields and triggers persistent notification.
    - `test_async_step_import_already_configured`: Test importing an already-configured deviceSN aborts with `already_configured`.
  - In `tests/test_sensor.py`:
    - `test_async_setup_platform_triggers_import`: Test `async_setup_platform` calls `flow.async_init(SOURCE_IMPORT)` and skips direct entity creation when migrating.
    - `test_async_setup_platform_skips_if_entry_exists`: Test `async_setup_platform` does nothing when a `ConfigEntry` already exists for the deviceSN.

- [ ] **Step 2: Run test suite to verify tests fail**
  Run `.venv/bin/pytest tests/ -k "import"` and confirm failure.

- [ ] **Step 3: Implement `async_step_import` and update `async_setup_platform`**
  - In `config_flow.py`: Implement `async_step_import(self, import_data: dict) -> ConfigFlowResult`.
  - In `sensor.py`: Update `async_setup_platform` to check `hass.config_entries.async_entries(DOMAIN)`. If entry exists, return cleanly. If not, dispatch `hass.async_create_task(hass.config_entries.flow.async_init(...))` and return cleanly.
  - Update strings/translations if needed.

- [ ] **Step 4: Run test suite to verify tests pass**
  Run `.venv/bin/pytest tests/ -v` and confirm all tests pass.

- [ ] **Step 5: Commit changes**
  Commit with message: `Add automatic YAML configuration migration to UI ConfigEntry`

---

### Task 3: Manual Verification in Local Home Assistant

**Files:**
- Test config: `ha_test_config/configuration.yaml`

- [ ] **Step 1: Verify Options Flow in UI**
  - Open `http://localhost:8123/config/integrations`.
  - Click **Konfiguruj (Configure)** on the FoxESS integration card.
  - Toggle `extendPV` or change a diagnostic flag, save, and check `ha_test_config/home-assistant.log` to confirm reload and entity updates.

- [ ] **Step 2: Verify YAML Migration in UI**
  - Add a mock YAML entry in `ha_test_config/configuration.yaml`.
  - Restart Home Assistant or reload configuration.
  - Check that the persistent notification appears in HA and the inverters appear as UI entries without duplicate entities.
