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
foxess:
  foxesscloud_username:
   password: foxesscloud_password
   devices: 
      device_name: foxesscloud_inverter_id
```
replacing:
- `foxesscloud_username` username that you use to login to foxess clous
- `foxesscloud_password` password that you use to login to foxess clous
- `device_name` - device name , the prefix that will be in all entitys related with one device, if you are migrating to new config use `FoxESS` to keep the history continuity 
- `foxesscloud_inverter_id` id of your device

#### Auxiliary notes:
- `foxesscloud_inverter_id` in UUID that can be found on the foxesscloud in the url path on the `Inverter Details` page.
⚠️  Please make sure that this is exact value from inverter details page address between = and & character:
![Screenshot 2021-11-08 at 08 42 05](https://user-images.githubusercontent.com/2965092/140761535-edb12226-b2b8-4f2b-87ce-11b67476a9e2.png)
- Multi-inverter support 
   - if you have more then one device on one account
   
      ```yaml
      foxess:
        joe@gmail.com:
         password: $ecret4
         devices: 
            FoxESS: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee5
            FoxESS_2: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee4
      ```
   - if you have more then one device on  difrent accounts
      ```yaml
      foxess:
        joe@gmail.com:
         password: $ecret4
         devices: 
            FoxESS_2: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee3
        big@gmail.com:
         password: $ecret##$1:L<MNB
         devices: 
            FoxESS_Garage: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee1
            Uncle_Bob: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeee2
      ```


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
PV1 Power | kW
PV2 Power | kW
PV3 Power | kW
PV4 Power | kW
Energy Generated  |  kWh 
Grid Consumption  |  kWh 
FeedIn  |  kWh  
Solar  |  kWh 
Load |  kWh 
Bat Charge  |  kWh 
Bat Discharge  |  kWh  
Bat SoC | %
Bat Temp | °C 


💡 If you want to understand energy generation per string check out this wiki [article](https://github.com/macxq/foxess-ha/wiki/Understand-PV-string-power-generation-using-foxess-ha)

## 🤔 Troubleshooting 

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
