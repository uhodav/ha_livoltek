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
GROUP_SITE_INSTALLER = "site_installer"
GROUP_SITE_OWNER = "site_owner"
GROUP_DEVICE_BASIC = "device_basic"

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
    GROUP_SITE_INSTALLER,
    GROUP_SITE_OWNER,
    GROUP_DEVICE_BASIC,
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
    GROUP_SITE_INSTALLER: "🏗️ Site Installer — Company, Org Code",
    GROUP_SITE_OWNER: "👤 Site Owner — Name, Email, Account",
    GROUP_DEVICE_BASIC: "📋 Device Basic Data — Daily Counters, Registration",
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
    GROUP_SITE_INSTALLER: "🏗️ Інсталятор — компанія, код організації",
    GROUP_SITE_OWNER: "👤 Власник сайту — ім'я, email, акаунт",
    GROUP_DEVICE_BASIC: "📋 Базові дані пристрою — добові лічильники, реєстрація",
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

# ── Battery type (from Storage /ESS endpoint) ────────────────────────
BATTERY_TYPE_MAP = {
    "0": "No battery",
    "1": "LIVOLTEK Low Voltage Li",
    "2": "Lithium",
    "3": "Other Li-ion (no BMS)",
    "4": "LFP15 (no BMS)",
    "5": "LFP16 (no BMS)",
    "10": "AGM",
    "11": "FLD",
    "12": "USER",
    "13": "Li2",
    "14": "Li4",
    "100": "Lead-acid (AGM/Flooded/Gel)",
    "101": "LIVOLTEK",
}

BATTERY_TYPE_MAP_UK = {
    "0": "Немає батареї",
    "1": "LIVOLTEK низьковольтний Li",
    "2": "Літій",
    "3": "Інший Li-ion (без BMS)",
    "4": "LFP15 (без BMS)",
    "5": "LFP16 (без BMS)",
    "10": "AGM",
    "11": "FLD",
    "12": "USER",
    "13": "Li2",
    "14": "Li4",
    "100": "Свинцево-кислотний (AGM/Flooded/Gel)",
    "101": "LIVOLTEK",
}

# ── Power flow statuses ──────────────────────────────────────────────
ENERGY_STATUS_MAP = {
    "charging": "Charging",
    "disCharging": "Discharging",
    "idel": "Idle",
    "idle": "Idle",
}

ENERGY_STATUS_MAP_UK = {
    "charging": "Заряджається",
    "disCharging": "Розряджається",
    "idel": "Простій",
    "idle": "Простій",
}

PV_STATUS_MAP = {
    "generating": "Generating",
    "offline": "Offline",
}

PV_STATUS_MAP_UK = {
    "generating": "Генерація",
    "offline": "Офлайн",
}

GRID_STATUS_MAP = {
    "importing": "Importing",
    "exporting": "Exporting",
}

GRID_STATUS_MAP_UK = {
    "importing": "Імпорт",
    "exporting": "Експорт",
}

LOAD_STATUS_MAP = {
    "consuming": "Consuming",
    "idel": "Idle",
    "idle": "Idle",
}

LOAD_STATUS_MAP_UK = {
    "consuming": "Споживання",
    "idel": "Простій",
    "idle": "Простій",
}

CHARGING_PILE_STATUS_MAP = {
    "available": "Available",
    "EV：Charging": "EV Charging",
    "EV:Charging": "EV Charging",
}

CHARGING_PILE_STATUS_MAP_UK = {
    "available": "Доступний",
    "EV：Charging": "EV заряджається",
    "EV:Charging": "EV заряджається",
}

# ── Alarm type ───────────────────────────────────────────────────────
ALARM_TYPE_MAP = {
    "0": "Notice",
    "1": "Fault",
    "Notice": "Notice",
    "fault": "Fault",
}

ALARM_TYPE_MAP_UK = {
    "0": "Повідомлення",
    "1": "Несправність",
    "Notice": "Повідомлення",
    "fault": "Несправність",
}

# ── Alarm action (MQTT) ─────────────────────────────────────────────
ALARM_ACTION_MAP = {
    "0": "Alarm",
    "1": "Fault",
}

ALARM_ACTION_MAP_UK = {
    "0": "Тривога",
    "1": "Несправність",
}

# ── Site active status ───────────────────────────────────────────────
SITE_ACTIVE_MAP = {
    0: "Not Active",
    1: "Active",
    2: "Not Active",
    3: "Active",
}

SITE_ACTIVE_MAP_UK = {
    0: "Неактивний",
    1: "Активний",
    2: "Неактивний",
    3: "Активний",
}

# ── Device upgrade status ────────────────────────────────────────────
UP_STATUS_MAP = {
    "1": "Upgrading",
    "2": "Upgrade Successful",
    "-1": "Upgrade Failed",
    "0": "ODM Abnormal Interruption",
}

UP_STATUS_MAP_UK = {
    "1": "Оновлення",
    "2": "Оновлення успішне",
    "-1": "Оновлення невдале",
    "0": "ODM аварійне переривання",
}

# ── Point interval (sampling accuracy) ───────────────────────────────
POINT_INTERVAL_MAP = {
    0: "Every 5 minutes",
    1: "Every 10 minutes",
    2: "Every 15 minutes",
}

# ── Grid connection type ─────────────────────────────────────────────
GRID_TIED_TYPE_MAP = {
    1: "100% Feed-in",
    2: "Self-use First",
    3: "0 Feed-in",
    4: "Off-grid",
}

GRID_TIED_TYPE_MAP_UK = {
    1: "100% віддача",
    2: "Самоспоживання",
    3: "0 віддача",
    4: "Автономний",
}

# ── UA translations for existing maps ────────────────────────────────
RUNNING_STATUS_MAP_UK = {
    "0": "Нормальний",
    "1": "Очікування",
    "2": "Несправність",
    "3": "Офлайн",
    "4": "Самоперевірка",
    "5": "Оновлення",
}

SITE_STATUS_MAP_UK = {
    1: "Всі онлайн",
    2: "Всі офлайн",
    3: "Частково офлайн",
}

SITE_TYPE_MAP_UK = {
    "1": "Мережева сонячна система",
    "2": "Сонячна акумуляторна система",
    "3": "EV зарядний хаб",
    "4": "EV зарядний хаб з акумулятором",
}

WORK_MODE_MAP_UK = {
    "1": "Резервний",
    "2": "Самоспоживання",
    "3": "Визначений користувачем",
    "4": "Командний режим",
}

CONTROL_TYPE_MAP_UK = {
    0: "Запуск інвертора",
    1: "Зупинка інвертора",
    2: "Перезапуск інвертора",
    3: "Перезапуск BMS",
    4: "Аварійна зарядка",
}

# ── MQTT configuration (informational) ───────────────────────────────
MQTT_SERVERS = {
    SERVER_INTERNATIONAL: "mqtt://api.livoltek-portal.com:1883",
    SERVER_EUROPEAN: "mqtt://api-eu.livoltek-portal.com:1883",
}
MQTT_TOPIC_ALARM = "ev_alarm_topic/{sn}"
MQTT_TOPIC_WORK_STATUS = "ev_work_status_topic/{sn}"

# ── API rate limits ──────────────────────────────────────────────────
# Minimum update interval (minutes) to respect API rate limits
MIN_UPDATE_INTERVAL = 5  # realtime data interval is 5 min on server side
# Device power report & site day energy: max 1 request per hour per device/site
ENERGY_REPORT_MIN_INTERVAL = 3600  # seconds
