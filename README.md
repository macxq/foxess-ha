# [FoxESS](https://www.fox-ess.com/) and [Home Assistant](https://www.home-assistant.io/) integration 


```yaml
sensor:
  - platform: foxess
    username: foxesscloud_username
    password: foxesscloud_password
    deviceID: foxesscloud_inverter_id
```

`foxesscloud_inverter_id` in UUID that can be found on the foxesscloud in the url path on the `Inverter Details` page 
