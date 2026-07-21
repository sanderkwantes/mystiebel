"""Constants for the Mystiebel integration."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

DOMAIN = "mystiebel"
WS_URL = "wss://serviceapi.mystiebel.com/ws/v1"

# API Configuration
BASE_URL = "https://auth.mystiebel.com"
SERVICE_URL = "https://serviceapi.mystiebel.com"

# App Configuration
APP_NAME = "MyStiebelApp"
APP_VERSION_ANDROID = "Android_2.3.0"
USER_AGENT = f"{APP_NAME}/2.3.0 Dalvik/2.1.0"

# Timing Constants
WEBSOCKET_HEARTBEAT = 30  # seconds
WEBSOCKET_RECONNECT_INITIAL = 5  # seconds
WEBSOCKET_RECONNECT_MAX = 300  # 5 minutes
TOKEN_REFRESH_MARGIN = 300  # Refresh token 5 minutes before expiry
API_RATE_LIMIT_DELAY = 1  # Minimum seconds between API calls

# Message ID Range
MSG_ID_MIN = 1_000_000
MSG_ID_MAX = 9_999_999
MSG_ID_LONG_MIN = 1_000_000_000
MSG_ID_LONG_MAX = 9_999_999_999

# List of essential read-only sensors.
# These will be enabled by default. All other sensor-type entities will be disabled by default.
ESSENTIAL_SENSORS = [
    15,  # Dome Temperature
    2378,  # Current Target Temperature
    2395,  # Mixed Water Volume
    2758,  # Operating Mode
    2388,  # SG-Ready State
    1111,  # Compressor (state)
    1116,  # Heating Element (state)
    1130,  # Defrosting (state)
    2370,  # Integral Temperature
    2372,  # Air Inlet Temperature
]

# List of essential control entities (switches, numbers, selects).
# These will also be enabled by default. All other controls will be disabled.
ESSENTIAL_CONTROLS = [
    13,  # Setpoint Temperature Comfort
    14,  # Setpoint Temperature Eco
    2466,  # Eco heating mode
    2382,  # Boost Request (Select)
    2487,  # Hot Water Plus Requested (Switch)
    2498,  # Weekly Hygiene Program Requested (Switch)
    2384,  # Frost Protection Requested (Switch)
    2481,  # End of Vacation (Switch)
]

# List of individual sensors to exclude from creation,
# because they are used to build more advanced, combined sensors.
EXCLUDED_INDIVIDUAL_SENSORS = {
    # Version numbers (major, minor, patch, revision for Controller and Wi-Fi)
    65523,
    65524,
    65525,
    65535,
    65536,
    65537,
    65559,
    65560,
    # Product and Gateway ID numbers (order, production, factory, plant)
    65553,
    65554,
    65555,
    65556,
    65557,
    65558,
    65593,
    65594,
    # Runtime numbers in days and hours (are combined into a single sensor)
    2449,
    555,
    2450,
    558,
    # Weekly hygiene program time (combined into single time entity)
    2477,  # Minutes
    2483,  # Hours
}

# --- Centralized Mappings ---

UNIT_MAP = {
    "degree_celsius": "°C",
    "degree_celtius": "°C",
    "liter": "L",
    "second": "s",
    "minute": "min",
    "hour": "h",
    "day": "d",
    "watt": "W",
    "kilowatt": "kW",
    "watt_hour": "Wh",
    "kilowatt_hour": "kWh",
    "humidity": "%",
    "none": None,
    "": None,
    "None": None,
}

DEVICE_CLASS_MAP = {
    "°C": SensorDeviceClass.TEMPERATURE,
    "s": SensorDeviceClass.DURATION,
    "min": SensorDeviceClass.DURATION,
    "h": SensorDeviceClass.DURATION,
    "d": SensorDeviceClass.DURATION,
    "L": SensorDeviceClass.VOLUME,
    "W": SensorDeviceClass.POWER,
    "kW": SensorDeviceClass.POWER,
    "kWh": SensorDeviceClass.ENERGY,
    "Wh": SensorDeviceClass.ENERGY,
    "Pa": SensorDeviceClass.PRESSURE,
    "%": SensorDeviceClass.HUMIDITY,
}

STATE_CLASS_MAP = {
    "Temperature": SensorStateClass.MEASUREMENT,
    "Number": SensorStateClass.MEASUREMENT,
    "Pressure": SensorStateClass.MEASUREMENT,
    "Humidity": SensorStateClass.MEASUREMENT,
    "Second": SensorStateClass.MEASUREMENT,
    "Hour": SensorStateClass.MEASUREMENT,
    "Minute": SensorStateClass.MEASUREMENT,
    "DurationHours": SensorStateClass.MEASUREMENT,
    "DurationDays": SensorStateClass.MEASUREMENT,
    "WWK_LuminosityLevel": SensorStateClass.MEASUREMENT,
    "Power": SensorStateClass.MEASUREMENT,
    "Energy": SensorStateClass.TOTAL_INCREASING,
    "State": None,
    "NotificationCode": None,
    "SwitchingTime": None,
    "LocalTime": None,
}

DATA_TYPE_DEVICE_CLASS_MAP = {
    "LocalTime": SensorDeviceClass.TIMESTAMP,
}

NUMERIC_CONTROL_TYPES = {
    "Temperature",
    "Number",
    "Percentage",
    "Hour",
    "Minute",
    "DurationHours",
    "DurationDays",
    "WWK_LuminosityLevel",
}
