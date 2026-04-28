"""Select platform for Livoltek work mode control."""
import json
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ACCOUNT,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_SN,
    CONF_PASSWORD,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    CONF_WORKMODE,
    DOMAIN,
    GROUP_DEVICE_DETAILS,
    GROUP_LABELS,
    GROUP_LABELS_UK,
    WORK_MODE_MAP,
)

_LOGGER = logging.getLogger(__name__)

# Reverse map: description -> mode value string
_MODE_TO_VALUE = {v: k for k, v in WORK_MODE_MAP.items()}


def _parse_supported_modes(coordinator_data: dict) -> list[dict]:
    """Parse supported work modes from device_description.workmode JSON."""
    desc = (coordinator_data or {}).get("device_description") or {}
    raw = desc.get("workmode", "")
    if isinstance(raw, str) and raw.startswith("["):
        try:
            modes = json.loads(raw)
            if isinstance(modes, list):
                return modes
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _build_device_info(entry_data: dict, coordinator_data: dict | None = None, hass=None) -> dict:
    """Build device info dict for the device_details group."""
    site_id = entry_data.get(CONF_SITE_ID, "")
    device_sn = entry_data.get(CONF_DEVICE_SN, "")
    device_model = entry_data.get(CONF_DEVICE_MODEL, "inverter")
    product_type = entry_data.get("product_type", "")

    sw_version = None
    if coordinator_data:
        device_details = coordinator_data.get("device_details") or {}
        sw_version = device_details.get("firmwareVersion")

    group = GROUP_DEVICE_DETAILS
    lang = getattr(hass.config, "language", "en") if hass else "en"
    labels = GROUP_LABELS_UK if lang and lang.startswith("uk") else GROUP_LABELS
    group_label = labels.get(group, group)

    return {
        "identifiers": {(DOMAIN, f"{site_id}_{device_sn}_{group}")},
        "name": f"{device_sn} ({group_label})",
        "manufacturer": "LIVOLTEK",
        "model": product_type or device_model,
        "sw_version": sw_version,
    }


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Livoltek select entities from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    if not runtime.get("has_control"):
        return

    coordinator = runtime["coordinator"]
    api = runtime["api"]
    entry_data = entry.data

    async_add_entities([
        LivoltekWorkModeSelect(
            hass=hass,
            entry=entry,
            coordinator=coordinator,
            api=api,
            entry_data=entry_data,
        )
    ])


class LivoltekWorkModeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for inverter work mode."""

    def __init__(self, hass, entry, coordinator, api, entry_data: dict) -> None:
        super().__init__(coordinator)
        self._hass = hass
        self._entry = entry
        self._api = api
        self._entry_data = entry_data

        site_id = entry_data.get(CONF_SITE_ID, "")
        device_sn = entry_data.get(CONF_DEVICE_SN, "")
        uid = f"livoltek_{site_id}_{device_sn}_work_mode_select"

        self._attr_unique_id = uid
        self._attr_suggested_object_id = f"livoltek_{site_id}_{device_sn}_work_mode_select"
        self._attr_device_sn = device_sn
        self._attr_translation_key = "work_mode_select"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:cog-play"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self):
        return _build_device_info(self._entry_data, self.coordinator.data, hass=self._hass)

    @property
    def options(self) -> list[str]:
        """Build options dynamically from device_description.workmode."""
        modes = _parse_supported_modes(self.coordinator.data)
        if modes:
            return [m.get("description", f"Mode {m.get('value', '?')}") for m in modes]
        # Fallback to hardcoded map
        return list(WORK_MODE_MAP.values())

    @property
    def current_option(self) -> str | None:
        """Return the current work mode from tracked runtime value."""
        runtime = self._hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
        current_value = runtime.get("current_workmode")
        if current_value is None:
            return None

        # Map value ("1", "2", ...) to description using device_description
        modes = _parse_supported_modes(self.coordinator.data)
        for m in modes:
            if str(m.get("value")) == str(current_value):
                return m.get("description", f"Mode {current_value}")

        # Fallback to hardcoded map
        return WORK_MODE_MAP.get(str(current_value), str(current_value))

    async def async_select_option(self, option: str) -> None:
        """Set the work mode."""
        # Find mode value by description from device_description
        mode_value = None
        modes = _parse_supported_modes(self.coordinator.data)
        for m in modes:
            if m.get("description") == option:
                mode_value = str(m.get("value"))
                break

        # Fallback to hardcoded reverse map
        if mode_value is None:
            mode_value = _MODE_TO_VALUE.get(option)

        if mode_value is None:
            _LOGGER.error("Unknown work mode option: %s", option)
            return

        account = self._entry_data.get(CONF_ACCOUNT, "")
        pwd_md5 = self._entry_data.get(CONF_PASSWORD, "")
        device_sn = self._entry_data.get(CONF_DEVICE_SN, "")

        await self._api.set_work_mode(
            account=account,
            pwd_md5=pwd_md5,
            sn=device_sn,
            work_mode=int(mode_value),
        )

        # Track selected mode in runtime
        runtime = self._hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
        runtime["current_workmode"] = mode_value

        # Persist to config entry for restore after restart
        new_data = {**self._entry.data, CONF_WORKMODE: mode_value}
        self._hass.config_entries.async_update_entry(self._entry, data=new_data)

        self.async_write_ha_state()
