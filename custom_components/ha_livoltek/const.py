DOMAIN = "ha_livoltek"

CONF_SERVER_TYPE = "server_type"
CONF_SECUID = "secuid"
CONF_KEY = "key"
CONF_TOKEN = "token"  # user-provided token, used as userToken query param
CONF_AUTH_TOKEN = "auth_token"  # JWT from login, used as Authorization header
CONF_SITE_ID = "site_id"
CONF_SITE_NAME = "site_name"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_SN = "device_sn"
CONF_DEVICE_MODEL = "device_model"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_WORKMODE = "workmode"
CONF_ACCOUNT = "account"
CONF_PASSWORD = "password"  # stored as MD5 hash
CONF_ENABLED_GROUPS = "enabled_groups"

# Endpoint group identifiers for selective data fetching
GROUP_POWER_FLOW = "power_flow"
GROUP_OVERVIEW = "overview"
GROUP_SITE_DETAILS = "site_details"
GROUP_DEVICE_DETAILS = "device_details"
GROUP_STORAGE = "storage"
GROUP_DEVICE_ELECTRICITY = "device_electricity"
GROUP_SOCIAL = "social"
GROUP_ALARMS = "alarms"
GROUP_REALTIME = "realtime"
GROUP_DAILY_ENERGY = "daily_energy"

ALL_GROUPS = [
    GROUP_POWER_FLOW,
    GROUP_OVERVIEW,
    GROUP_SITE_DETAILS,
    GROUP_DEVICE_DETAILS,
    GROUP_STORAGE,
    GROUP_DEVICE_ELECTRICITY,
    GROUP_SOCIAL,
    GROUP_ALARMS,
    GROUP_REALTIME,
    GROUP_DAILY_ENERGY,
]

GROUP_LABELS = {
    GROUP_POWER_FLOW: "⚡ Power Flow — PV, Grid, Battery, Load",
    GROUP_OVERVIEW: "📊 Site Overview — Generation, Revenue",
    GROUP_SITE_DETAILS: "🏠 Site Details — Status, Capacity, Type",
    GROUP_DEVICE_DETAILS: "🔧 Device Details — Firmware, Work Mode",
    GROUP_STORAGE: "🔋 Battery / ESS — SOC, Charge, Discharge",
    GROUP_DEVICE_ELECTRICITY: "📈 Lifetime Energy — Total Generation",
    GROUP_SOCIAL: "🌱 Social — CO₂, Trees, Coal Saved",
    GROUP_ALARMS: "🚨 Alarms — Device Alerts",
    GROUP_REALTIME: "📡 Realtime — MPPT, AC, Battery, EPS",
    GROUP_DAILY_ENERGY: "📅 Daily Energy Report",
}

GROUP_LABELS_UK = {
    GROUP_POWER_FLOW: "⚡ Потоки енергії — PV, мережа, батарея, навантаження",
    GROUP_OVERVIEW: "📊 Огляд сайту — генерація, дохід",
    GROUP_SITE_DETAILS: "🏠 Деталі сайту — статус, потужність, тип",
    GROUP_DEVICE_DETAILS: "🔧 Деталі пристрою — прошивка, режим роботи",
    GROUP_STORAGE: "🔋 Батарея / ESS — SOC, заряд, розряд",
    GROUP_DEVICE_ELECTRICITY: "📈 Загальна енергія — генерація за весь час",
    GROUP_SOCIAL: "🌱 Соціальний внесок — CO₂, дерева, вугілля",
    GROUP_ALARMS: "🚨 Тривоги — сповіщення пристрою",
    GROUP_REALTIME: "📡 Реальний час — MPPT, AC, батарея, EPS",
    GROUP_DAILY_ENERGY: "📅 Добовий звіт енергії",
}

SERVER_INTERNATIONAL = "international"
SERVER_EUROPEAN = "european"

SERVERS = {
    SERVER_INTERNATIONAL: "https://api.livoltek-portal.com:8081",
    SERVER_EUROPEAN: "https://api-eu.livoltek-portal.com:8081",
}

DEFAULT_UPDATE_INTERVAL = 5  # minutes

# Daily energy report fetch interval (seconds)
ENERGY_REPORT_INTERVAL = 3600  # 1 hour

# Human-readable status mappings
RUNNING_STATUS_MAP = {
    "0": "Normal",
    "1": "Standby",
    "2": "Fault",
    "3": "Offline",
    "4": "Self-test",
    "5": "Upgrading",
}

SITE_STATUS_MAP = {
    1: "All Online",
    2: "All Offline",
    3: "Partial Offline",
}

SITE_TYPE_MAP = {
    "1": "Grid-tied solar system",
    "2": "Solar storage system",
    "3": "EV charging hub",
    "4": "EV charging hub with solar storage",
}

WORK_MODE_MAP = {
    "1": "Back Up",
    "2": "Self Use",
    "3": "User Defined",
    "4": "Command Mode",
}

CONTROL_TYPE_MAP = {
    0: "Inverter Start",
    1: "Inverter Stop",
    2: "Inverter Restart",
    3: "BMS Restart",
    4: "Emergency Charging",
}
