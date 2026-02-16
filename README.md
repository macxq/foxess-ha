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

Edit your home-assistant `/configuration.yaml`  and add:

```yaml
sensor:
  - platform: foxess
    deviceID: enter_your_inverter_id
    deviceSN: enter_your_inverter_serial_number
    apiKey: enter_your_personal_api_key
```

#### Auxiliary notes:
- `username & password` are no longer required for this integration, it uses your_personal_api_key instead.

- `your_inverter_serial_number` is the serial number of the inverter this integration will be gathering data from, you can see the deviceSN by logging into the Foxesscloud.com website, in the left hand menu click on 'Device', then 'Inverter' this will display a table and your Inverter SN - the format will be similar to : 60BHnnnnnnXnnn - copy and paste this into the config setting deviceSN: replacing the text `foxesscloud_inverter_serial_number`

- `your_personal_api_key` is a personal api_key that is generated in your profile selection of your Foxesscloud account. To do this log into the Foxesscloud.com website, click on the 'profile icon' in the top right corner and select 'User Profile'. Then on the menu on the left hand side select 'API Management' and click 'Generate API Key, the long string that it generates should be copied and pasted into the platform config setting of your configuration.yaml apiKey: replacing the text `foxesscloud_personal_api_key` (see example above).

- `your_inverter_id` ⚠️  Please note the inverter_id requirement has changed and the deviceID is only required for legacy installations installed prior to the OpenAPI being introduced, for these older installations do not remove it as it will affect your entity history and follow the notes for legacy installations below.

   **For new 'OpenAPI' installations, follow these instructions:**

    For all new OpenAPI installs (since March 2024) simply re-use your unique inverter_serial_number `deviceSN:` in the `deviceID:` (i.e. you would enter your inverter serial number in both of these fields)
   i.e. it would look like this:
   ```yaml
   sensor:
     - platform: foxess
       deviceID: enter_your_inverter_serial_number
       deviceSN: enter_your_inverter_serial_number
       apiKey: enter_your_personal_api_key
   ```


   For **legacy installations only** you must continue to use the inverter_id as it sets the unique_id for the entities and it will delete your entity history if it is changed.
   It can be found in the UUID on the foxesscloud in the url path of the `Inverter Details` page; make sure that this is exact value from inverter details page address between the %2522 and %2522 characters:
![112](https://github.com/macxq/foxess-ha/assets/123640536/1e024286-7215-4bab-8e7d-5dfe5e719275)

- Fox R series or inverters with more than 6 PV strings - if you have an inverter that supports more than 16 PV strings, please add the following switch `extendPV: true` to your platform config and the integration will attempt to read PV strings 7-18 volts, current power sensors.
   ```
       deviceID: enter_your_inverter_serial_number
       deviceSN: enter_your_inverter_serial_number
       apiKey: enter_your_personal_api_key
       extendPV: true
   ```


- Multi-inverter support - if you have more than one FoxESS device in your installation, you can leverage the optional `name` field in your config,
   ```
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

The OpenAPI access is limited and each user must have a personal_api_key to access it, this personal_api_key can be generated by logging into the FoxESS cloud wesbite - then click on the Profile Icon in the top right hand corner of the screen, select User Profile and then from the menu select API Management, click the button to 'Generate API Key' - this long string of numbers is your personal_api_key and must be used for access to your systems details.

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


## 📚 Usefull wiki articles
* [Understand PV string power generation using foxess ha](https://github.com/macxq/foxess-ha/wiki/Understand-PV-string-power-generation-using-foxess-ha)
* [Sample sensors for better solar monitoring](https://github.com/macxq/foxess-ha/wiki/Sample-sensors-for-better-solar-monitoring)
* [How to fix Energy Dashboard data (statistic data)](https://github.com/macxq/foxess-ha/wiki/How-to-fix-Energy-Dashboard-data-(statistic-data))
