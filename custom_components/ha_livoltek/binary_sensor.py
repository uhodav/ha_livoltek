"""Binary sensor platform for Livoltek (web portal alarms)."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_SN, CONF_SITE_ID, DOMAIN, GROUP_PORTAL
from .sensor import _build_device_info, _get_group_label


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Livoltek binary sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator_portal")
    if coordinator is None:
        return
    async_add_entities([LivoltekActiveAlarmSensor(coordinator, entry.data)])


class LivoltekActiveAlarmSensor(CoordinatorEntity, BinarySensorEntity):
    """On while an Important or Urgent alarm is active in the portal."""

    _attr_has_entity_name = True
    _attr_translation_key = "active_alarm"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alarm-light"

    def __init__(self, coordinator, entry_data: dict) -> None:
        super().__init__(coordinator)
        self._entry_data = entry_data
        site_id = entry_data.get(CONF_SITE_ID, "")
        device_sn = entry_data.get(CONF_DEVICE_SN, "")
        self._attr_unique_id = f"livoltek_{site_id}_{device_sn}_active_alarm"
        self._attr_suggested_object_id = self._attr_unique_id

    @property
    def device_info(self):
        return _build_device_info(
            self._entry_data, None,
            group=GROUP_PORTAL, group_label=_get_group_label(self.hass, GROUP_PORTAL),
        )

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("active_alarms"))

    @property
    def extra_state_attributes(self):
        active = (self.coordinator.data or {}).get("active_alarms") or []
        return {
            "active_count": len(active),
            "alarms": [
                {"level": a.get("level"), "content": a.get("content"), "time": a.get("alarmTime") or a.get("createTime")}
                for a in active[:5]
            ],
        }
