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

Copy content of `custom_components` folder into your HA `/config/custom_components` folder



## 💾 Configuration

Edit your home-assistan `/configuration.yaml`  and add:

```yaml
sensor:
  - platform: foxess
    username: foxesscloud_username
    password: foxesscloud_password
    deviceID: foxesscloud_inverter_id
    deviceSN: foxesscloud_inverter_serial_number
    apiKey: foxesscloud_personal_api_key
```

#### Auxiliary notes:
- `foxesscloud_inverter_serial_number` is the serial number of the inverter this integration will be gathering data from, you can see the deviceSN by logging into the Foxesscloud.com website, in the left hand menu click on 'Device', then 'Inverter' this will display a table and your Inverter SN - the format will be similar to : 60BHnnnnnnXnnn - copy and paste this into the config setting deviceSN: replacing the text `foxesscloud_inverter_serial_number`

- `foxesscloud_personal_api_key` is a personal api_key that is generated in your profile seection of your Foxesscloud account. To do this log into the Foxesscloud.com website, click on the profile icon in the top right corner and select 'User Profile', then on the menu select 'API Management' and click 'Generate API Key, the long string that it generates should be copied and pasted into the config setting apiKey: replacing the text `foxesscloud_personal_api_key` above.

- `foxesscloud_inverter_id` in UUID that can be found on the foxesscloud in the url path on the `Inverter Details` page.
⚠️  Please make sure that this is exact value from inverter details page address between = and & character:
![Screenshot 2021-11-08 at 08 42 05](https://user-images.githubusercontent.com/2965092/140761535-edb12226-b2b8-4f2b-87ce-11b67476a9e2.png)
- Multi-inverter support - if you have more than one FoxESS device in your installation, you can leverage the optional `name` field in you config, if you want see an example check out [here](https://github.com/macxq/foxess-ha/wiki/Multi-Inverter-Support)



## 📊 Provided entities

HA Entity  | Measurement
|---|---|
Inverter |  on/off
Generation Power  |  kW 
Grid Consumption Power  |  kW  
FeedIn Power  |  kW  
Bat Discharge Power  |  kW   
Bat Charge Power  |  kW  
Solar Power | kW
Load Power | kW
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
Energy Generated  |  kWh 
Grid Consumption  |  kWh 
FeedIn  |  kWh  
Solar  |  kWh 
Load |  kWh 
Bat Charge  |  kWh 
Bat Discharge  |  kWh  
Bat SoC | %
Bat Temp | °C 
Ambient Temp | °C
Boost Temp | °C
Inv Temp | °C


💡 If you want to understand energy generation per string check out this wiki [article](https://github.com/macxq/foxess-ha/wiki/Understand-PV-string-power-generation-using-foxess-ha)

## 🤔 Troubleshooting 

API Error summary:

- `{"errno":41930,"result":null}` ⟶ incorrect inverter id
- `{"errno":40261,"result":null}` ⟶ incorrect inverter id
- `{"errno":41807,"result":null}` ⟶ wrong user name or password
- `{"errno":41808,"result":null}` ⟶ token expierd
- `{"errno":41809,"result":null}` ⟶ invalid token


Increase log level in your `/configuration.yaml` by adding:

```yaml
logger:
  default: warning
  logs:
    custom_components.foxess: debug
```
## 📚 Usefull wiki articles
* [Understand PV string power generation using foxess ha](https://github.com/macxq/foxess-ha/wiki/Understand-PV-string-power-generation-using-foxess-ha)
* [Sample sensors for better solar monitoring](https://github.com/macxq/foxess-ha/wiki/Sample-sensors-for-better-solar-monitoring)
* [How to fix Energy Dashboard data (statistic data)](https://github.com/macxq/foxess-ha/wiki/How-to-fix-Energy-Dashboard-data-(statistic-data))
