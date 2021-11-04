## [FoxESS](https://www.fox-ess.com/) and [Home Assistant](https://www.home-assistant.io/) integration  🏡 ☀️

## ⚙️ Installation & ♻️ Update

Use hacs.io to install and update by adding [custom repositories](https://hacs.xyz/docs/faq/custom_repositories)


## 💾 Configuration

Edit your home-assistan `/configuration.yaml`  and add:

```yaml
sensor:
  - platform: foxess
    username: foxesscloud_username
    password: foxesscloud_password
    deviceID: foxesscloud_inverter_id
```

`foxesscloud_inverter_id` in UUID that can be found on the foxesscloud in the url path on the `Inverter Details` page 


## 📊 Provided entities

HA Entity  | Measurement
|---|---|
Generation Power  |  kW 
Grid Consumption Power  |  kW  
FeedIn Power  |  kW  
Bat Discharge Power  |  kW   
Bat Charge Power  |  kW  
Energy Generated  |  kWh 
Grid Consumption  |  kWh 
FeedIn  |  kWh  
Bat Charge  |  kWh 
Bat Discharge  |  kWh  
Bat SoC | %
Bat Temp | °C 

## 🤔 Troubleshooting 

Increase log level in your `/configuration.yaml` by adding:

```yaml
logger:
  default: warning
  logs:
    custom_components.foxess: debug
```

