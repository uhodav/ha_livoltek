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
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_MODEL,
    CONF_DEVICE_SN,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    CONF_WORKMODE,
    DOMAIN,
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


def _build_device_info(entry_data: dict, coordinator_data: dict | None = None) -> dict:
    """Build device info dict."""
    site_id = entry_data.get(CONF_SITE_ID, "")
    device_sn = entry_data.get(CONF_DEVICE_SN, "")
    site_name = entry_data.get(CONF_SITE_NAME, "Livoltek")
    device_model = entry_data.get(CONF_DEVICE_MODEL, "inverter")
    product_type = entry_data.get("product_type", "")

    sw_version = None
    if coordinator_data:
        device_details = coordinator_data.get("device_details") or {}
        sw_version = device_details.get("firmwareVersion")

    return {
        "identifiers": {(DOMAIN, f"{site_id}_{device_sn}")},
        "name": f"{site_name} ({device_sn})",
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
    ("current_soc", "storage", "currentSoc", SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT, PERCENTAGE, "mdi:battery", None),
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
    ("grid_active_power", "realtime", "dwActivePower", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, UnitOfPower.WATT, "mdi:flash", None),
    ("grid_apparent_power", "realtime", "dwApparentPower", SensorDeviceClass.APPARENT_POWER, SensorStateClass.MEASUREMENT, "VA", "mdi:flash-outline", None),
    ("grid_frequency", "realtime", "girdFrequency", SensorDeviceClass.FREQUENCY, SensorStateClass.MEASUREMENT, UnitOfFrequency.HERTZ, "mdi:sine-wave", None),
]

REALTIME_BATTERY_SENSORS = [
    ("battery_voltage", "realtime", "batteryVoltage", SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT, UnitOfElectricPotential.VOLT, "mdi:battery", None),
    ("battery_current", "realtime", "batteryCurrent", SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT, UnitOfElectricCurrent.AMPERE, "mdi:battery-charging", None),
    ("battery_soc_realtime", "realtime", "batterySoc", SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT, PERCENTAGE, "mdi:battery", None),
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
)

# Set of sensor keys that represent ms-epoch timestamps
_TIMESTAMP_KEYS = {
    "power_flow_timestamp", "overview_update_time", "site_update_time",
    "device_update_time", "realtime_timestamp",
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Livoltek sensors from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    entry_data = entry.data
    enabled_groups = runtime.get("enabled_groups", set())

    sensors = []
    for sensor_def in ALL_SENSOR_DEFINITIONS:
        key, data_source, data_field, device_class, state_class, unit, icon, entity_category = sensor_def
        # Skip sensors whose data_source group is not enabled
        if data_source not in enabled_groups:
            continue
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

        site_id = entry_data.get(CONF_SITE_ID, "")
        device_sn = entry_data.get(CONF_DEVICE_SN, "")
        uid = f"livoltek_{site_id}_{device_sn}_{sensor_key}"

        self._attr_unique_id = uid
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

    @property
    def device_info(self):
        return _build_device_info(self._entry_data, self.coordinator.data)

    @property
    def native_value(self):
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
        if self._sensor_key == "running_status":
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
                    attrs[f"{prefix}_type"] = rec.get("alarmType")
                    attrs[f"{prefix}_time"] = rec.get("originTime")
                    attrs[f"{prefix}_event"] = rec.get("alarmEvent")

        return attrs
