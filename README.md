## [FoxESS](https://www.fox-ess.com/) and [Home Assistant](https://www.home-assistant.io/) integration  🏡 ☀️

## Installation

Go to to home-assistan `/configcustom_components` folder and fetch the component:

```bash
git clone https://github.com/macxq/foxess-ha.git
```
## Configuration

Edit your home-assistan `/configuration.yaml`  and add:

```yaml
sensor:
  - platform: foxess
    username: foxesscloud_username
    password: foxesscloud_password
    deviceID: foxesscloud_inverter_id
```

`foxesscloud_inverter_id` in UUID that can be found on the foxesscloud in the url path on the `Inverter Details` page 
