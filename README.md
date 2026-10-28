<h2 align="center">
   <a href="https://www.fox-ess.com">FoxESS</a> and<a href="https://www.home-assistant.io"> Home Assistant</a> integration  🏡 ☀
   </br></br>
   <img src="https://github.com/home-assistant/brands/raw/master/custom_integrations/foxess/logo.png" >
   </br>
   <a href="https://github.com/hacs/default"><img src="https://img.shields.io/badge/HACS-default-sucess"></a>
   <a href="https://github.com/macxq/foxess-ha/actions/workflows/HACS.yaml/badge.svg?branch=main"><img src="https://github.com/macxq/foxess-ha/actions/workflows/HACS.yaml/badge.svg?branch=main"/></a>
    <a href="https://github.com/macxq/foxess-ha/actions/workflows/hassfest.yaml/badge.svg"><img src="https://github.com/macxq/foxess-ha/actions/workflows/hassfest.yaml/badge.svg"/></a>
    </br>
</h2>

## ⚙️ Installation & ♻️ Update

Use hacs.io to manage the installation and update process. Right now this integration is part of HACS by default - no more neeed to add it by custom repositories 🥳

## ⌨️ Manual installation 

Create the folder called `foxess` in `/homeassistant/custom_components`

Copy the content of this integrations `custom_components/foxess` folder into your HA `/homeassistant/custom_components/foxess` folder



## 💾 Configuration

### 📱 UI Configuration (Recommended)

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=foxess)

1. In Home Assistant, navigate to **Settings** ➔ **Devices & services**.
2. Click **Add Integration** and search for **FoxESS**.
3. **Step 1 - API Key:** Enter your personal `apiKey` (masked password field with toggle 👁️).
4. **Step 2 - Select Inverter:** Select your inverter from the discovered devices list (pre-selected automatically if you have one inverter).
5. If you have multiple inverters in your FoxESS account, simply click **Add Integration** again to add each additional inverter.

#### How to get your API Key:
1. Log into the FoxESS OpenAPI Developer Portal at [developer-eu.foxesscloud.com/apiKeys](https://developer-eu.foxesscloud.com/apiKeys) (or [developer-us.foxesscloud.com](https://developer-us.foxesscloud.com) for US accounts) using your FoxESS Cloud account credentials.
2. Click **Generate API Key** (or copy your existing key).
3. Paste the API key into the Home Assistant setup form.

---

### ⚙️ Options Flow (Integration Settings)

You can adjust settings for each configured inverter at any time without restarting Home Assistant:
1. Go to **Settings** ➔ **Devices & services** ➔ **FoxESS**.
2. Click **Configure** on the inverter entry card:
   - **Assigned Inverter:** Displays the serial number (`deviceSN`) for this device (read-only).
   - **API Key:** Update or change your FoxESS API key.
   - **Daily energy sanity check threshold (kWh) (`energyGeneratedSanityCheck`):** Maximum expected daily energy generation in kWh (default: `100.0` kWh). Readings above this threshold are ignored to protect Energy Dashboard statistics from corrupted spikes (e.g. when FoxESS Cloud erroneously reports lifetime yield instead of daily yield).
   - **Reduced API calls mode (Eco mode) (`reduceAPICalls`):** Halves API polling frequency (10-minute intervals for real-time telemetry, 30-minute intervals for status details, 60-minute intervals for reports) to prevent hitting the FoxESS 1,440 daily call quota. Recommended for multi-inverter setups or systems connected to external Virtual Power Plant (VPP) providers (e.g. Amber Electric, Evergen).
   - **Show zero when inverter is offline (`show_unknown_zero`):** When enabled, power, current, and voltage sensors cleanly report `0.0` instead of falling into `unavailable`/`unknown` when the inverter or micro-inverter is offline after sunset, and cumulative energy totals are retained.
   - **Extended PV strings (`extendPV`):** Enable for Fox R series or inverters supporting more than 6 PV strings (reads PV strings 7–18).
   - **FoxESS EVO series mode (`Evo`):** Enable if using a FoxESS EVO series inverter where device details are incomplete.
   - **Cross Time Zone adjustment (`xtZone`):** Enable if inverter timestamps use a different time zone than Home Assistant.
   - **Restrict API variables (`Restrict`):** Restrict variable queries to essential telemetry if Fox Cloud returns errors for large variable lists.

---

### 📋 Configuration Parameters Reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `apiKey` | string | *Required* | FoxESS OpenAPI token generated in the FoxESS Developer Portal. |
| `deviceSN` | string | *Required* | Inverter serial number from Foxess Cloud. |
| `deviceID` | string | `deviceSN` | Inverter ID. Reuses `deviceSN` for all modern setups. Preserves legacy UUID on older setups. |
| `name` | string | `"FoxESS"` | Friendly name prefix for inverter entities and device title. |
| `energyGeneratedSanityCheck` | float | `100.0` | Daily generation ceiling (kWh). Spikes exceeding this value are rejected to safeguard Energy Dashboard statistics. |
| `reduceAPICalls` | boolean | `false` | Enable reduced API call frequency (10-minute polling) to conserve daily quota on accounts with multiple inverters or external VPP providers. |
| `show_unknown_zero` | boolean | `false` | When enabled, reports 0 for power, current, and voltage instead of unavailable when the inverter is offline (e.g. micro-inverters at night) and retains cumulative energy totals. |
| `extendPV` | boolean | `false` | Enable to read additional PV strings 7–18 for inverters with >6 strings. |
| `Evo` | boolean | `false` | Enable support for FoxESS EVO series inverters. |
| `xtZone` | boolean | `false` | Adjust time zone offset if inverter timestamps differ from HA local time. |
| `Restrict` | boolean | `false` | Limit API variable queries to prevent timeout/payload issues on certain inverters. |
| `Use_V1_Api` | boolean | `true` | Use OpenAPI v1 endpoints (`/op/v1/device/...`) for real-time telemetry. |

---

### 🔄 Automatic Migration from YAML

If you previously configured FoxESS using `configuration.yaml`:
- When Home Assistant starts with this version, your configuration will be **automatically imported** into a UI Config Entry.
- **Zero data loss:** All entity unique IDs (`{deviceID}{suffix}`) and historical sensor statistics are preserved.
- A persistent notification will appear in Home Assistant confirming successful migration.
- After migration, you can safely remove the `foxess` block from your `configuration.yaml`.

---

<details>
<summary><b>⌨️ Legacy YAML Configuration (Deprecated)</b></summary>

> [!NOTE]
> YAML configuration is deprecated and will be removed in a future release. Please use the UI configuration flow instead.

```yaml
sensor:
  - platform: foxess
    deviceID: enter_your_inverter_serial_number
    deviceSN: enter_your_inverter_serial_number
    apiKey: enter_your_personal_api_key
```

- `your_personal_api_key`: generated at [developer-eu.foxesscloud.com/apiKeys](https://developer-eu.foxesscloud.com/apiKeys) (or [developer-us.foxesscloud.com](https://developer-us.foxesscloud.com) for US accounts).
- `deviceSN`: inverter serial number from Foxesscloud.com under Device -> Inverter.
- `deviceID`: for all installations since March 2024, reuse `deviceSN` as `deviceID`. For older legacy installations, keep the original inverter UUID from the Foxess Cloud URL to preserve historical entity unique IDs.
- `extendPV`: set to `true` if your inverter has more than 6 PV strings.

Multi-inverter YAML example:
```yaml
sensor:
  - platform: foxess
    name: Fox1
    deviceID: enter_your_inverter_id_1
    deviceSN: enter_your_inverter_serial_number_1
    apiKey: enter_your_personal_api_key_1
  - platform: foxess
    name: Fox2
    deviceID: enter_your_inverter_id_2
    deviceSN: enter_your_inverter_serial_number_2
    apiKey: enter_your_personal_api_key_2
```

</details>


## 🔋 Battery Controls, Work Modes & Scheduling

For systems equipped with a battery, this integration exposes direct controls and automation services via FoxESS Cloud OpenAPI:

### 🎛️ Control Entities

| Entity | Platform | Domain | Description |
|---|---|---|---|
| **FoxESS - Work Mode** | `select` | `select` | Switch inverter operating mode: `Self-Use`, `Feed-in`, `Backup`, or `Peak Shaving`. Automatically rejects manual changes when Mode Scheduler is active to prevent cloud conflict error 44096. |
| **FoxESS - Min SoC** | `number` | `number` | Minimum battery State of Charge off-grid (10–100%, step 1). Clamped automatically so `Min SoC <= Min SoC on Grid`. |
| **FoxESS - Min SoC on Grid** | `number` | `number` | Minimum battery State of Charge while connected to grid (10–100%, step 1). Clamped automatically so `Min SoC on Grid >= Min SoC`. |
| **FoxESS - Mode Scheduler** | `switch` | `switch` | Toggle cloud scheduler on/off. Configured scheduler groups and force charge times are exposed in entity attributes. |

> [!NOTE]
> For PV-only installations without a battery (`hasBattery: false`), battery controls and scheduler platforms are automatically skipped.

---

### ⚡ Automation Services

#### 1. `foxess.set_schedule`
Overwrites the FoxESS Mode Scheduler with configured time slots and operating modes (ideal for dynamic tariff charging, e.g. Octopus Agile, Nord Pool, Tibber):

```yaml
action: foxess.set_schedule
data:
  device_sn: "60BH1234567"
  enable: true
  groups:
    - enable: 1
      startHour: 2
      startMinute: 0
      endHour: 5
      endMinute: 0
      workMode: "ForceCharge"
      minSocOnGrid: 100
      fdPwr: 0
```

#### 2. `foxess.set_force_charge_times`
Configures grid force-charging time windows for inverters supporting `forceChargeTime` (such as AIO-H3, AC1, and models that do not use the Mode Scheduler):

```yaml
action: foxess.set_force_charge_times
data:
  device_sn: "60BH1234567"
  enable_1: true
  start_time_1: "02:00"
  end_time_1: "05:00"
  enable_2: false
  start_time_2: "14:00"
  end_time_2: "16:00"
```

---

## 📊 Provided entities

HA Entity  | Measurement
|---|---|
Inverter |  string  `on-line/off-line/in-alarm` - attributes Master, Manager, Slave versions & Battery details where fitted
Generation Power  |  kW 
Grid Consumption Power  |  kW  
FeedIn Power  |  kW  
Bat Discharge Power  |  kW   
Bat Charge Power  |  kW  
Solar Power | kW
Load Power | kW
Meter2 Power | kW
PV1 Current | A
PV1 Power | kW
PV1 Volt | V
PV2 Current | A
PV2 Power | kW
PV2 Volt | V
PV3 Current | A
PV3 Power | kW
PV3 Volt | V
PV4 Current | A
PV4 Power | kW
PV4 Volt | V
PV Power | kW
R Current | A
R Freq | Hz
R Power | kW
R Volt | V
S Current | A
S Freq | Hz
S Power | kW
S Volt | V
T Current | A
T Freq | Hz
T Power | kW
T Volt | V
Reactive Power | kVar
PV Production Total | kWh
Energy Generated  |  kWh 
Energy Generated Month  |  kWh 
Energy Throughput | kWh
Grid Consumption  |  kWh 
FeedIn  |  kWh  
Solar  |  kWh 
Load |  kWh 
Bat Charge  |  kWh 
Bat Discharge  |  kWh  
Bat SoC | % (single battery systems)
Bat SoC1 | % (dual battery systems)
Bat SoC2 | % (dual battery systems)
Bat SoH | % (single battery systems where BMS supports it)
Max Bat Charge Current | A
Max Bat Discharge Current | A
Inverter Bat Power | kW (negative=charging, positive=discharging)
Inverter Bat Power2 | kW (dual battery systems
Bat Temperature | °C 
Bat Temperature2 | °C (dual battery systems)
Ambient Temp | °C
Boost Temp | °C
Inv Temp | °C
Residual Energy | kWh
minSoC | %
minSoC on Grid | %
Power Factor | %
API Response Time | mS
Running State | string `163: on-grid` (see **Table1**)

**Table1** Possible Running States
Running State
|---------|
160: self-test
161: waiting
162: checking
163: on-grid
164: off-grid
165: fault
166: permanent-fault
167: standby
168: upgrading
169: fct
170: illegal


💡 If you want to understand energy generation per string check out this wiki [article](https://github.com/macxq/foxess-ha/wiki/Understand-PV-string-power-generation-using-foxess-ha)

## 🤔 Troubleshooting 

API Error summary:

- `{"errno":41930,"result":null}` ⟶ incorrect inverter id
- `{"errno":40261,"result":null}` ⟶ incorrect inverter id
- `{"errno":41807,"result":null}` ⟶ wrong user name or password
- `{"errno":41808,"result":null}` ⟶ token expired
- `{"errno":41809,"result":null}` ⟶ invalid token
- `{"errno":40256,"result":null}` ⟶ Request header parameters are missing. Check whether the request headers are consistent with OpenAPI requirements.
- `{"errno":40257,"result":null}` ⟶ Request body parameters are invalid. Check whether the request body is consistent with OpenAPI requirements.
- `{"errno":40400,"result":null}` ⟶ The number of requests is too frequent. Please reduce the frequency of access.


Increase log level in your `/configuration.yaml` by adding:

```yaml
logger:
  default: warning
  logs:
    custom_components.foxess: debug
```

## FoxESS Open API Access and Limits
FoxESS provide an OpenAPI that allows registered users to make request to return datasets.

The OpenAPI access is limited and each user must have an `apiKey` to access it. This API key can be generated by logging into the FoxESS Developer Portal at [developer-eu.foxesscloud.com/apiKeys](https://developer-eu.foxesscloud.com/apiKeys) (or [developer-us.foxesscloud.com](https://developer-us.foxesscloud.com) for US accounts) using your FoxESS Cloud account credentials and clicking 'Generate API Key'. Copy this key and use it to configure the integration.

The OpenAPI has a limit of 1,440 API calls per day, after which the OpenAPI will stop responding to requests and generate a "40400" error.

This sounds like a large number of calls, but bear in mind that multiple API calls have to be made on each scan to gain the complete dataset for a system.

The integration paces the number of API calls that are made, with the following frequency -

- Site status and plant details - every 15 minutes
- Real time variables - every 5 minutes
- Cumulative total reports (generation, feedin, gridConsumption, BatterychargeTotal, Batterydischargetotal, home load) - every 15 minutes
- Daily Generation report (Daily Energy Generated - 'total yield') - every 60 minutes
- Battery minSoC settings - every 60 minutes

The integration is using approximately 22 API calls an hour (528 a day and well within the 1,440).

If you have multiple inverters in your account, you will receive 1,440 calls per inverter, so for 2 inverters you will have 2,880 api calls.

### 🍃 Reduced API Calls Mode (Eco Mode)

If your FoxESS account is shared with an external **Virtual Power Plant (VPP)** provider (e.g. Amber Electric, Evergen, Reposit) or you have multiple inverters and are approaching the 1,440 calls/day limit, enable **Reduced API calls mode (Eco mode)** in the integration settings (**Settings ➔ Devices & services ➔ FoxESS ➔ Configure**):

- **Real time telemetry:** every 10 minutes (instead of 5 minutes)
- **Site status and device details:** every 30 minutes (instead of 15 minutes)
- **Energy total reports:** every 60 minutes (instead of 15 minutes)
- **Daily generation report:** every 60 minutes
- **Battery minSoC settings:** every 60 minutes

This reduces polling to approximately **11 API calls per hour** (~264 calls per day per inverter), cutting API consumption by more than **50%** and ensuring your setup remains safely below daily quota limits.


## 📚 Usefull wiki articles
* [Understand PV string power generation using foxess ha](https://github.com/macxq/foxess-ha/wiki/Understand-PV-string-power-generation-using-foxess-ha)
* [Sample sensors for better solar monitoring](https://github.com/macxq/foxess-ha/wiki/Sample-sensors-for-better-solar-monitoring)
* [How to fix Energy Dashboard data (statistic data)](https://github.com/macxq/foxess-ha/wiki/How-to-fix-Energy-Dashboard-data-(statistic-data))
