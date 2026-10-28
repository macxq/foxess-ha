"""Constants and enums for FoxESS Cloud integration."""
from datetime import timedelta
import enum

DOMAIN = "foxess"
DEFAULT_NAME = "FoxESS"

# Configuration keys
CONF_APIKEY = "apiKey"
CONF_DEVICESN = "deviceSN"
CONF_DEVICEID = "deviceID"
CONF_NAME = "name"
CONF_SYSTEM_ID = "system_id"
CONF_EXTPV = "extendPV"
CONF_XTZONE = "xtZone"
CONF_GET_VARIABLES = "Restrict"
CONF_V1_API = "Use_V1_Api"
CONF_EVO = "Evo"
CONF_ENERGY_GENERATED_SANITY = "energyGeneratedSanityCheck"
DEFAULT_ENERGY_GENERATED_SANITY = 100.0
CONF_REDUCE_API_CALLS = "reduceAPICalls"
DEFAULT_REDUCE_API_CALLS = False

# Timing and Intervals
SCAN_MINUTES = 1  # number of minutes between coordinator refresh evaluations
SCAN_INTERVAL = timedelta(minutes=SCAN_MINUTES)
DEFAULT_TIMEOUT = 50
RETRY_NEXT_SLOT = -1
RETRY_IN_5_MINS = 25
RETRY_IN_10_MINS = 20

# API Endpoints
_ENDPOINT_OA_DOMAIN = "https://www.foxesscloud.com"
_ENDPOINT_OA_BATTERY_SETTINGS = "/op/v0/device/battery/soc/get?sn="
_ENDPOINT_OA_BATTERY_SOC_SET = "/op/v0/device/battery/soc/set"
_ENDPOINT_OA_BATTERY_FORCE_CHARGE_GET = "/op/v0/device/battery/forceChargeTime/get"
_ENDPOINT_OA_BATTERY_FORCE_CHARGE_SET = "/op/v0/device/battery/forceChargeTime/set"
_ENDPOINT_OA_SETTING_SET = "/op/v0/device/setting/set"
_ENDPOINT_OA_SETTING_GET = "/op/v0/device/setting/get"
_ENDPOINT_OA_SCHEDULER_FLAG_SET = "/op/v1/device/scheduler/set/flag"
_ENDPOINT_OA_SCHEDULER_FLAG_GET = "/op/v1/device/scheduler/get/flag"
_ENDPOINT_OA_SCHEDULER_ENABLE = "/op/v2/device/scheduler/enable"
_ENDPOINT_OA_SCHEDULER_GET = "/op/v2/device/scheduler/get"
_ENDPOINT_OA_REPORT = "/op/v0/device/report/query"
_ENDPOINT_OA_DEVICE_DETAIL = "/op/v0/device/detail"
_ENDPOINT_OA_DEVICE_DETAIL_V1 = "/op/v1/device/detail"
_ENDPOINT_OA_DEVICE_VARIABLES = "/op/v0/device/real/query"
_ENDPOINT_OA_DEVICE_VARIABLES_V1 = "/op/v1/device/real/query"
_ENDPOINT_OA_DAILY_GENERATION = "/op/v0/device/generation?sn="
_ENDPOINT_OA_DEVICE_LIST = "/op/v0/device/list"

# Error numbers for authentication failure (invalid/missing token)
_AUTH_ERRNO = {41808, 41809}

# Key under hass.data where YAML-configured device info is stored
YAML_CONFIGS_KEY = "foxess_yaml_configs"

# Attributes
ATTR_DEVICE_SN = "deviceSN"
ATTR_PLANTNAME = "plantName"
ATTR_MODULESN = "moduleSN"
ATTR_DEVICE_TYPE = "deviceType"
ATTR_MASTER = "masterVersion"
ATTR_MANAGER = "managerVersion"
ATTR_SLAVE = "slaveVersion"
ATTR_BATTERYLIST = "batteryList"
ATTR_LASTCLOUDSYNC = "lastCloudSync"

BATTERY_LEVELS = {"High": 80, "Medium": 50, "Low": 25, "Empty": 10}


class FetchResult(enum.Enum):
    """Result of a FoxESS Cloud API fetch call."""

    OK = "ok"
    ERROR = "error"
    AUTH_FAILED = "auth_failed"
    DNS_TIMEOUT = "dns_timeout"

    def __bool__(self) -> bool:
        """Return False for OK so callers can use `if not result:` for success."""
        return self is not FetchResult.OK
