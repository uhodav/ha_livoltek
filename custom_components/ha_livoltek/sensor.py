"""Sensor platform for Livoltek integration."""
import json
import logging
from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfMass,
    UnitOfPower,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ALARM_TYPE_MAP,
    BATTERY_TYPE_MAP,
    CHARGING_PILE_STATUS_MAP,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_SN,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    CONF_WORKMODE,
    DOMAIN,
    ENERGY_STATUS_MAP,
    GRID_STATUS_MAP,
    GROUP_DAILY_ENERGY,
    GROUP_LABELS,
    GROUP_LABELS_UK,
    LOAD_STATUS_MAP,
    PV_STATUS_MAP,
    RUNNING_STATUS_MAP,
    SITE_STATUS_MAP,
    SITE_TYPE_MAP,
    WORK_MODE_MAP,
)

_LOGGER = logging.getLogger(__name__)


def _safe_float(value) -> float | None:
    """Convert value to float safely."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _ms_to_datetime(value) -> datetime | None:
    """Convert millisecond epoch timestamp to datetime."""
    if value is None:
        return None
    try:
        ts = int(value)
        if ts > 1e12:
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _get_last_alarm_field(alarms_data: dict, field: str):
    """Get a field from the most recent alarm record."""
    records = alarms_data.get("records")
    if not records or not isinstance(records, list):
        return None
    return records[0].get(field)


def _get_group_label(hass, group: str) -> str:
    """Return group label in HA configured language."""
    lang = getattr(hass.config, "language", "en") if hass else "en"
    labels = GROUP_LABELS_UK if lang and lang.startswith("uk") else GROUP_LABELS
    return labels.get(group, group)


def _build_device_info(
    entry_data: dict,
    coordinator_data: dict | None = None,
    group: str | None = None,
    group_label: str | None = None,
) -> dict:
    """Build device info dict. Each group becomes a separate device."""
    site_id = entry_data.get(CONF_SITE_ID, "")
    device_sn = entry_data.get(CONF_DEVICE_SN, "")
    device_model = entry_data.get(CONF_DEVICE_MODEL, "inverter")
    product_type = entry_data.get("product_type", "")

    sw_version = None
    if coordinator_data:
        device_details = coordinator_data.get("device_details") or {}
        sw_version = device_details.get("firmwareVersion")

    dev_id = f"{site_id}_{device_sn}"
    dev_name = device_sn
    if group:
        dev_id = f"{site_id}_{device_sn}_{group}"
        dev_name = f"{device_sn} ({group_label or group})"

    return {
        "identifiers": {(DOMAIN, dev_id)},
        "name": dev_name,
        "manufacturer": "LIVOLTEK",
        "model": product_type or device_model,
        "sw_version": sw_version,
    }


# -- Sensor definitions ---------------------------------------------------
# Each tuple: (key, data_source, data_field, device_class, state_class, unit, icon, entity_category)
# Name and description come from translations via translation_key

POWER_FLOW_SENSORS = [
    ("pv_power", "power_flow", "pvPower", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.KILO_WATT, "mdi:solar-power", None),
    ("grid_power", "power_flow", "powerGridPower", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.KILO_WATT, "mdi:transmission-tower", None),
    ("load_power", "power_flow", "loadPower", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.KILO_WATT, "mdi:home-lightning-bolt", None),
    ("battery_power", "power_flow", "energyPower", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.KILO_WATT, "mdi:battery-charging", None),
    ("battery_soc", "power_flow", "energySoc", SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT, PERCENTAGE, "mdi:battery", None),
    ("charging_pile_power", "power_flow", "chargingPilePower", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.KILO_WATT, "mdi:ev-station", None),
    ("pv_status", "power_flow", "pvStatus", None, None, None, "mdi:solar-power-variant", EntityCategory.DIAGNOSTIC),
    ("grid_status", "power_flow", "powerGridStatus", None, None, None, "mdi:transmission-tower", EntityCategory.DIAGNOSTIC),
    ("load_status", "power_flow", "loadStatus", None, None, None, "mdi:home-lightning-bolt", EntityCategory.DIAGNOSTIC),
    ("battery_status", "power_flow", "energyStatus", None, None, None, "mdi:battery-heart-variant", EntityCategory.DIAGNOSTIC),
    ("charging_pile_status", "power_flow", "chargingPileStatus", None, None, None, "mdi:ev-station", EntityCategory.DIAGNOSTIC),
    ("power_flow_timestamp", "power_flow", "timestamp", SensorDeviceClass.TIMESTAMP, None, None, "mdi:clock-outline", EntityCategory.DIAGNOSTIC),
]

OVERVIEW_SENSORS = [
    ("current_power", "overview", "currentPower", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.KILO_WATT, "mdi:flash", None),
    ("daily_generation", "overview", "eoutDaily", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:solar-power", None),
    ("monthly_generation", "overview", "eoutMonth", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:calendar-month", None),
    ("yearly_generation", "overview", "eoutCurrentYear", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:calendar", None),
    ("lifetime_generation", "overview", "etotalToGrid", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:chart-line", None),
    ("online_devices", "overview", "onlineDevice", None, None, None, "mdi:devices", EntityCategory.DIAGNOSTIC),
    ("overview_update_time", "overview", "updateTime", SensorDeviceClass.TIMESTAMP, None, None, "mdi:clock-outline", EntityCategory.DIAGNOSTIC),
]

SITE_DETAILS_SENSORS = [
    ("site_type", "site_details", "powerStationType", None, None, None, "mdi:solar-panel", EntityCategory.DIAGNOSTIC),
    ("site_status", "site_details", "powerStationStatus", None, None, None, "mdi:lan-connect", EntityCategory.DIAGNOSTIC),
    ("pv_capacity", "site_details", "pvCapacity", None, None, "kWp", "mdi:solar-panel-large", EntityCategory.DIAGNOSTIC),
    ("has_alarm", "site_details", "hasAlarm", None, None, None, "mdi:alarm-light-outline", EntityCategory.DIAGNOSTIC),
    ("site_country", "site_details", "country", None, None, None, "mdi:earth", EntityCategory.DIAGNOSTIC),
    ("site_timezone", "site_details", "timezone", None, None, None, "mdi:clock-time-four", EntityCategory.DIAGNOSTIC),
    ("site_update_time", "site_details", "updateTime", SensorDeviceClass.TIMESTAMP, None, None, "mdi:clock-outline", EntityCategory.DIAGNOSTIC),
]

DEVICE_DETAILS_SENSORS = [
    ("device_sn", "device_details", "inverterSn", None, None, None, "mdi:identifier", EntityCategory.DIAGNOSTIC),
    ("product_type", "device_details", "productType", None, None, None, "mdi:tag", EntityCategory.DIAGNOSTIC),
    ("running_status", "device_details", "runningStatus", None, None, None, "mdi:state-machine", EntityCategory.DIAGNOSTIC),
    ("firmware_version", "device_details", "firmwareVersion", None, None, None, "mdi:chip", EntityCategory.DIAGNOSTIC),
    ("device_type", "device_details", "deviceType", None, None, None, "mdi:devices", EntityCategory.DIAGNOSTIC),
    ("device_manufacturer", "device_details", "deviceManufacturer", None, None, None, "mdi:factory", EntityCategory.DIAGNOSTIC),
    ("device_update_time", "device_details", "updateTime", SensorDeviceClass.TIMESTAMP, None, None, "mdi:clock-outline", EntityCategory.DIAGNOSTIC),
    ("work_mode", "device_details", "workmode", None, None, None, "mdi:cog-play", EntityCategory.DIAGNOSTIC),
]

STORAGE_SENSORS = [
    ("bms_capacity", "storage", "BMSCapacity", None, SensorStateClass.MEASUREMENT, "Ah", "mdi:battery-high", None),
    ("battery_cycle_count", "storage", "cycleCount", None, SensorStateClass.TOTAL_INCREASING, None, "mdi:battery-sync", EntityCategory.DIAGNOSTIC),
    ("battery_sn", "storage", "batterySn", None, None, None, "mdi:identifier", EntityCategory.DIAGNOSTIC),
]

DEVICE_ELECTRICITY_SENSORS = [
    ("pv_produce_electric", "device_electricity", "pvProduceElectric", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:solar-panel-large", None),
    ("load_customer_electric", "device_electricity", "loadCustomerElectric", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:home-lightning-bolt", None),
]

SOCIAL_SENSORS = [
    ("saving_co2", "social", "savingCO2", None, SensorStateClass.TOTAL_INCREASING, UnitOfMass.KILOGRAMS, "mdi:molecule-co2", None),
    ("saving_tree", "social", "savingTree", None, SensorStateClass.TOTAL_INCREASING, None, "mdi:tree", None),
    ("saving_coal", "social", "savingCoal", None, SensorStateClass.TOTAL_INCREASING, UnitOfMass.KILOGRAMS, "mdi:fire", None),
]

ALARM_SENSORS = [
    ("alarm_total", "alarms", "total", None, None, None, "mdi:alarm-light", EntityCategory.DIAGNOSTIC),
    ("last_alarm_name", "alarms", "_last_alarm_name", None, None, None, "mdi:alert-circle", EntityCategory.DIAGNOSTIC),
    ("last_alarm_time", "alarms", "_last_alarm_time", SensorDeviceClass.TIMESTAMP, None, None, "mdi:clock-alert", EntityCategory.DIAGNOSTIC),
]

# Realtime: MPPT PV channels (p1..p12)
REALTIME_PV_SENSORS = []
for _i in range(1, 13):
    REALTIME_PV_SENSORS.extend([
        (f"pv{_i}_voltage", "realtime", f"p{_i}Voltage", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, UnitOfElectricPotential.VOLT, "mdi:solar-power", None),
        (f"pv{_i}_current", "realtime", f"p{_i}Current", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, UnitOfElectricCurrent.AMPERE, "mdi:solar-power", None),
    ])

REALTIME_AC_SENSORS = [
    ("ac_phase_a_voltage", "realtime", "rVoltage", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, UnitOfElectricPotential.VOLT, "mdi:sine-wave", None),
    ("ac_phase_a_current", "realtime", "rCurrent", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, UnitOfElectricCurrent.AMPERE, "mdi:sine-wave", None),
    ("ac_phase_b_voltage", "realtime", "sVoltage", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, UnitOfElectricPotential.VOLT, "mdi:sine-wave", None),
    ("ac_phase_b_current", "realtime", "sCurrent", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, UnitOfElectricCurrent.AMPERE, "mdi:sine-wave", None),
    ("ac_phase_c_voltage", "realtime", "tVoltage", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, UnitOfElectricPotential.VOLT, "mdi:sine-wave", None),
    ("ac_phase_c_current", "realtime", "tCurrent", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, UnitOfElectricCurrent.AMPERE, "mdi:sine-wave", None),
    ("grid_active_power", "realtime", "dwActivePower", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.KILO_WATT, "mdi:flash", None),
    ("grid_apparent_power", "realtime", "dwApparentPower", SensorDeviceClass.APPARENT_POWER, SensorStateClass.MEASUREMENT, "VA", "mdi:flash-outline", None),
    ("grid_frequency", "realtime", "girdFrequency", SensorDeviceClass.FREQUENCY, SensorStateClass.MEASUREMENT, UnitOfFrequency.HERTZ, "mdi:sine-wave", None),
]

REALTIME_BATTERY_SENSORS = [
    ("battery_voltage", "realtime", "batteryVoltage", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, UnitOfElectricPotential.VOLT, "mdi:battery", None),
    ("battery_current", "realtime", "batteryCurrent", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, UnitOfElectricCurrent.AMPERE, "mdi:battery-charging", None),
]

REALTIME_EPS_SENSORS = [
    ("eps_voltage", "realtime", "epsVoltage", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, UnitOfElectricPotential.VOLT, "mdi:power-plug-battery", None),
    ("eps_current", "realtime", "epsCurrent", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, UnitOfElectricCurrent.AMPERE, "mdi:power-plug-battery", None),
    ("eps_frequency", "realtime", "epsFrequency", SensorDeviceClass.FREQUENCY, SensorStateClass.MEASUREMENT, UnitOfFrequency.HERTZ, "mdi:power-plug-battery", None),
]

REALTIME_TIMESTAMP_SENSOR = [
    ("realtime_timestamp", "realtime", "timestamp", SensorDeviceClass.TIMESTAMP, None, None, "mdi:clock-outline", EntityCategory.DIAGNOSTIC),
]

DAILY_ENERGY_SENSORS = [
    ("daily_pv_yield", "daily_energy", "pvYield", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:solar-power", None),
    ("daily_load_consumption", "daily_energy", "loadConsumption", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:home-lightning-bolt", None),
    ("daily_grid_import", "daily_energy", "energyImportFromGrid", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:transmission-tower-import", None),
    ("daily_grid_export", "daily_energy", "energyExportToGrid", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:transmission-tower-export", None),
    ("daily_battery_charge", "daily_energy", "chargingCapacity", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:battery-arrow-up", None),
    ("daily_battery_discharge", "daily_energy", "dischargeCapacity", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:battery-arrow-down", None),
    ("daily_eps_output", "daily_energy", "epsOutputenergy", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:power-plug-battery", None),
    ("daily_diesel_energy", "daily_energy", "dgtotalEnergy", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:fuel", None),
    ("daily_ev_consumption", "daily_energy", "evConsumption", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:ev-station", None),
]

SITE_INSTALLER_SENSORS = [
    ("installer_name", "site_installer", "installer", None, None, None, "mdi:domain", EntityCategory.DIAGNOSTIC),
    ("installer_org_code", "site_installer", "orgCode", None, None, None, "mdi:identifier", EntityCategory.DIAGNOSTIC),
]

SITE_OWNER_SENSORS = [
    ("owner_name", "site_owner", "name", None, None, None, "mdi:account", EntityCategory.DIAGNOSTIC),
    ("owner_email", "site_owner", "email", None, None, None, "mdi:email", EntityCategory.DIAGNOSTIC),
    ("owner_login_account", "site_owner", "loginAccount", None, None, None, "mdi:account-key", EntityCategory.DIAGNOSTIC),
    ("owner_country", "site_owner", "country", None, None, None, "mdi:earth", EntityCategory.DIAGNOSTIC),
]

DEVICE_BASIC_SENSORS = [
    ("device_communication_status", "device_basic", "communicationStatus", None, None, None, "mdi:lan-connect", EntityCategory.DIAGNOSTIC),
    ("device_running_status_basic", "device_basic", "runningStatus", None, None, None, "mdi:state-machine", EntityCategory.DIAGNOSTIC),
    ("device_registration_time", "device_basic", "registrationTime", None, None, None, "mdi:calendar-clock", EntityCategory.DIAGNOSTIC),
    ("device_power_gen_day", "device_basic", "powerGenerationDay", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:solar-power", None),
    ("device_grid_export_day", "device_basic", "negativeDay", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:transmission-tower-export", None),
    ("device_grid_import_day", "device_basic", "positiveDay", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:transmission-tower-import", None),
    ("device_charge_day", "device_basic", "chargeDay", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:battery-arrow-up", None),
    ("device_discharge_day", "device_basic", "dischargeDay", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:battery-arrow-down", None),
    ("device_load_day", "device_basic", "loadDay", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_WATT_HOUR, "mdi:home-lightning-bolt", None),
]

ALL_SENSOR_DEFINITIONS = (
    POWER_FLOW_SENSORS
    + OVERVIEW_SENSORS
    + SITE_DETAILS_SENSORS
    + DEVICE_DETAILS_SENSORS
    + STORAGE_SENSORS
    + DEVICE_ELECTRICITY_SENSORS
    + SOCIAL_SENSORS
    + ALARM_SENSORS
    + REALTIME_PV_SENSORS
    + REALTIME_AC_SENSORS
    + REALTIME_BATTERY_SENSORS
    + REALTIME_EPS_SENSORS
    + REALTIME_TIMESTAMP_SENSOR
    + DAILY_ENERGY_SENSORS
    + SITE_INSTALLER_SENSORS
    + SITE_OWNER_SENSORS
    + DEVICE_BASIC_SENSORS
)

# Set of sensor keys that represent ms-epoch timestamps
_TIMESTAMP_KEYS = {
    "power_flow_timestamp", "overview_update_time", "site_update_time",
    "device_update_time", "realtime_timestamp",
}

_DISABLED_BY_DEFAULT_KEYS = _TIMESTAMP_KEYS

_NO_HISTORY_KEYS = _TIMESTAMP_KEYS | {
    "device_sn", "product_type", "firmware_version", "device_type",
    "device_manufacturer", "device_registration_time",
    "site_type", "site_country", "site_timezone", "pv_capacity",
    "installer_name", "installer_org_code",
    "owner_name", "owner_email", "owner_login_account", "owner_country",
    "battery_sn",

    "pv_status", "grid_status", "load_status", "battery_status",
    "charging_pile_status", "running_status", "device_running_status_basic",
    "site_status", "device_communication_status", "has_alarm",
    "online_devices",

    "alarm_total", "last_alarm_name", "last_alarm_time",

    "bms_firmware_version", "battery_module_count", "battery_cell_count",
    "battery_max_cell_voltage_id", "battery_min_cell_voltage_id",
    "battery_max_cell_temp_id",
    "inverter_grid_charge_flag", "inverter_work_mode_setting",
}

_SLOW_COORDINATOR_SOURCES = frozenset({"daily_energy"})


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Livoltek sensors from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coord_medium = runtime["coordinator"]
    coord_slow = runtime.get("coordinator_slow")
    entry_data = entry.data
    enabled_groups = runtime.get("enabled_groups", set())

    sensors = []
    for sensor_def in ALL_SENSOR_DEFINITIONS:
        key, data_source, data_field, device_class, state_class, unit, icon, entity_category = sensor_def
        # Skip sensors whose data_source group is not enabled
        if data_source not in enabled_groups:
            continue

        if data_source in _SLOW_COORDINATOR_SOURCES and coord_slow is not None:
            coordinator = coord_slow
        else:
            coordinator = coord_medium

        sensors.append(
            LivoltekSensor(
                coordinator=coordinator,
                entry_data=entry_data,
                entry_id=entry.entry_id,
                sensor_key=key,
                data_source=data_source,
                data_field=data_field,
                device_class=device_class,
                state_class=state_class,
                unit=unit,
                icon=icon,
                entity_category=entity_category,
            )
        )

    async_add_entities(sensors)


class LivoltekSensor(CoordinatorEntity, SensorEntity):
    """A sensor entity for Livoltek data."""

    def __init__(
        self,
        coordinator,
        entry_data: dict,
        entry_id: str,
        sensor_key: str,
        data_source: str,
        data_field: str,
        device_class,
        state_class,
        unit,
        icon: str,
        entity_category,
    ) -> None:
        super().__init__(coordinator)
        self._entry_data = entry_data
        self._entry_id = entry_id
        self._sensor_key = sensor_key
        self._data_source = data_source
        self._data_field = data_field
        self._last_valid_value = None

        site_id = entry_data.get(CONF_SITE_ID, "")
        device_sn = entry_data.get(CONF_DEVICE_SN, "")
        uid = f"livoltek_{site_id}_{device_sn}_{sensor_key}"

        self._attr_unique_id = uid
        self._attr_suggested_object_id = f"livoltek_{site_id}_{device_sn}_{sensor_key}"
        self._attr_device_sn = device_sn
        self._attr_translation_key = sensor_key
        self._attr_has_entity_name = True
        self._attr_icon = icon

        if device_class is not None:
            self._attr_device_class = device_class
        if state_class is not None:
            self._attr_state_class = state_class
        if unit is not None:
            self._attr_native_unit_of_measurement = unit
        if entity_category is not None:
            self._attr_entity_category = entity_category
        if sensor_key in _DISABLED_BY_DEFAULT_KEYS:
            self._attr_entity_registry_enabled_default = False

    async def async_added_to_hass(self) -> None:
        """Set recorder options when entity is registered."""
        await super().async_added_to_hass()
        if self._sensor_key in _NO_HISTORY_KEYS:
            registry = er.async_get(self.hass)
            entry = registry.async_get(self.entity_id)
            if entry and entry.options.get("recorder", {}).get("should_record") is not False:
                registry.async_update_entity_options(
                    self.entity_id, "recorder", {"should_record": False},
                )

    @property
    def device_info(self):
        group_label = _get_group_label(self.hass, self._data_source)
        return _build_device_info(
            self._entry_data, self.coordinator.data,
            group=self._data_source, group_label=group_label,
        )

    @property
    def native_value(self):
        value = self._compute_value()
        if value is not None:
            self._last_valid_value = value
            return value
        # Keep last known value when API returns None/empty
        return self._last_valid_value

    def _compute_value(self):
        """Compute the raw sensor value from coordinator data."""
        if self._sensor_key == "battery_soc":
            data = self.coordinator.data or {}
            soc_realtime = (data.get("realtime") or {}).get("batterySoc")
            soc_storage = (data.get("storage") or {}).get("currentSoc")
            soc_powerflow = (data.get("power_flow") or {}).get("energySoc")
            # Используем последнее не-None значение
            for val in (soc_realtime, soc_storage, soc_powerflow):
                if val is not None:
                    self._last_soc = _safe_float(val)
                    break
            return getattr(self, "_last_soc", None)

        data = self.coordinator.data or {}
        source_data = data.get(self._data_source, {})
        if source_data is None:
            return None

        # -- Alarm computed fields -----------------------------------------
        if self._data_field == "_last_alarm_name":
            return _get_last_alarm_field(source_data, "alarmName")

        if self._data_field == "_last_alarm_time":
            raw_time = _get_last_alarm_field(source_data, "originTime")
            if raw_time:
                try:
                    return datetime.fromisoformat(str(raw_time)).replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    return _ms_to_datetime(raw_time)
            return None

        # -- Work mode: parse JSON, map to description ---------------------
        if self._sensor_key == "work_mode":
            return self._parse_workmode(source_data)

        raw_value = source_data.get(self._data_field)
        if raw_value is None:
            return None

        # -- Timestamp sensors: ms epoch -> datetime -----------------------
        if self._sensor_key in _TIMESTAMP_KEYS:
            return _ms_to_datetime(raw_value)

        # -- Running status: human-readable --------------------------------
        if self._sensor_key in ("running_status", "device_running_status_basic"):
            return RUNNING_STATUS_MAP.get(str(raw_value), str(raw_value))

        # -- Site type: human-readable -------------------------------------
        if self._sensor_key == "site_type":
            return SITE_TYPE_MAP.get(str(raw_value), str(raw_value))

        # -- Site status: human-readable -----------------------------------
        if self._sensor_key == "site_status":
            val = raw_value
            if isinstance(val, int):
                return SITE_STATUS_MAP.get(val, str(val))
            return str(val)

        # -- Power flow status sensors: human-readable ---------------------
        if self._sensor_key == "pv_status":
            return PV_STATUS_MAP.get(str(raw_value), str(raw_value))

        if self._sensor_key == "grid_status":
            return GRID_STATUS_MAP.get(str(raw_value), str(raw_value))

        if self._sensor_key == "load_status":
            return LOAD_STATUS_MAP.get(str(raw_value), str(raw_value))

        if self._sensor_key == "battery_status":
            return ENERGY_STATUS_MAP.get(str(raw_value), str(raw_value))

        if self._sensor_key == "charging_pile_status":
            return CHARGING_PILE_STATUS_MAP.get(str(raw_value), str(raw_value))

        # -- Communication status: map numeric to text ---------------------
        if self._sensor_key == "device_communication_status":
            comm_map = {"0": "Offline", "1": "Online"}
            return comm_map.get(str(raw_value), str(raw_value))

        # -- Numeric sensors -----------------------------------------------
        dev_class = getattr(self, "_attr_device_class", None)
        if dev_class in (
            SensorDeviceClass.POWER,
            SensorDeviceClass.ENERGY,
            SensorDeviceClass.BATTERY,
            SensorDeviceClass.VOLTAGE,
            SensorDeviceClass.CURRENT,
            SensorDeviceClass.FREQUENCY,
            SensorDeviceClass.APPARENT_POWER,
        ) or (getattr(self, "_attr_state_class", None) is not None and self._data_field not in ("onlineDevice",)):
            return _safe_float(raw_value)

        return raw_value

    def _parse_workmode(self, source_data: dict):
        """Return current work mode from tracked runtime value."""
        runtime = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        current_value = runtime.get("current_workmode")
        if current_value is None:
            return None

        # Map value to description using device_description
        data = self.coordinator.data or {}
        desc = (data.get("device_description") or {}).get("workmode", "")
        if isinstance(desc, str) and desc.startswith("["):
            try:
                modes = json.loads(desc)
                for m in modes:
                    if str(m.get("value")) == str(current_value):
                        return m.get("description", str(current_value))
            except (json.JSONDecodeError, TypeError):
                pass

        # Fallback to hardcoded map
        return WORK_MODE_MAP.get(str(current_value), str(current_value))

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        source_data = data.get(self._data_source, {})
        if source_data is None:
            return {}
        attrs = {"data_group": self._data_source}

        if self._sensor_key == "battery_soc":
            site_time = data.get("site_details", {}).get("updateTime")
            realtime_time = data.get("realtime", {}).get("timestamp")
            def _to_dt(val):
                if val is None:
                    return None
                try:
                    if isinstance(val, datetime):
                        return val
                    if isinstance(val, (int, float)):
                        return _ms_to_datetime(val)
                    # Если это строка
                    return datetime.fromisoformat(str(val))
                except Exception:
                    return None
            dt_site = _to_dt(site_time)
            dt_real = _to_dt(realtime_time)
            last_update = None
            if dt_site and dt_real:
                last_update = max(dt_site, dt_real)
            elif dt_site:
                last_update = dt_site
            elif dt_real:
                last_update = dt_real
            if last_update:
                attrs["last_update_time"] = last_update

        # -- Work mode: all mode options as attributes ---------------------
        if self._sensor_key == "work_mode":
            desc_data = (data.get("device_description") or {}).get("workmode", "")
            if isinstance(desc_data, str) and desc_data.startswith("["):
                try:
                    modes = json.loads(desc_data)
                    if isinstance(modes, list):
                        for mode in modes:
                            val = mode.get("value", "")
                            desc = mode.get("description", "")
                            attrs[f"mode_{val}"] = desc
                except (json.JSONDecodeError, TypeError):
                    pass
            if not attrs:
                for k, v in WORK_MODE_MAP.items():
                    attrs[f"mode_{k}"] = v

        # -- Running status: raw value + description -----------------------
        if self._sensor_key == "running_status":
            raw = source_data.get("runningStatus")
            if raw is not None:
                attrs["raw_value"] = raw
                attrs["description"] = RUNNING_STATUS_MAP.get(str(raw), "Unknown")

        # -- Site type: raw value + description ----------------------------
        if self._sensor_key == "site_type":
            raw = source_data.get("powerStationType")
            if raw is not None:
                attrs["raw_value"] = raw
                attrs["description"] = SITE_TYPE_MAP.get(str(raw), "Unknown")

        # -- Site status: raw value + description --------------------------
        if self._sensor_key == "site_status":
            raw = source_data.get("powerStationStatus")
            if raw is not None:
                attrs["raw_value"] = raw
                try:
                    key = raw if isinstance(raw, int) else int(raw)
                    attrs["description"] = SITE_STATUS_MAP.get(key, "Unknown")
                except (ValueError, TypeError):
                    attrs["description"] = "Unknown"

        # -- Alarm details as attributes -----------------------------------
        if self._sensor_key == "alarm_total":
            records = source_data.get("records")
            if records and isinstance(records, list):
                for i, rec in enumerate(records[:5]):
                    prefix = f"alarm_{i + 1}"
                    attrs[f"{prefix}_name"] = rec.get("alarmName")
                    attrs[f"{prefix}_code"] = rec.get("alarmCode")
                    attrs[f"{prefix}_status"] = rec.get("alarmStatus")
                    raw_type = rec.get("alarmType")
                    attrs[f"{prefix}_type_raw"] = raw_type
                    attrs[f"{prefix}_type"] = ALARM_TYPE_MAP.get(str(raw_type), str(raw_type)) if raw_type is not None else None
                    attrs[f"{prefix}_time"] = rec.get("originTime")
                    attrs[f"{prefix}_event"] = rec.get("alarmEvent")

        # -- Power flow status sensors: raw + description ------------------
        _STATUS_ATTR_MAP = {
            "pv_status": ("pvStatus", PV_STATUS_MAP),
            "grid_status": ("powerGridStatus", GRID_STATUS_MAP),
            "load_status": ("loadStatus", LOAD_STATUS_MAP),
            "battery_status": ("energyStatus", ENERGY_STATUS_MAP),
            "charging_pile_status": ("chargingPileStatus", CHARGING_PILE_STATUS_MAP),
        }
        if self._sensor_key in _STATUS_ATTR_MAP:
            field, enum_map = _STATUS_ATTR_MAP[self._sensor_key]
            raw = source_data.get(field)
            if raw is not None:
                attrs["raw_value"] = raw
                attrs["description"] = enum_map.get(str(raw), str(raw))

        # -- Battery type in storage attributes ----------------------------
        if self._data_source == "storage":
            bt = source_data.get("batteryType")
            if bt is not None:
                attrs["battery_type_raw"] = bt
                attrs["battery_type"] = BATTERY_TYPE_MAP.get(str(bt), str(bt))

        return attrs
