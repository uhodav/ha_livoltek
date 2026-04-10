"""Button platform for Livoltek BESS control."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .const import (
    CONF_ACCOUNT,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_SN,
    CONF_PASSWORD,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    CONTROL_TYPE_MAP,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# (key, control_type, icon)
BUTTON_DEFINITIONS = [
    ("inverter_start", 0, "mdi:play"),
    ("inverter_stop", 1, "mdi:stop"),
    ("inverter_restart", 2, "mdi:restart"),
    ("bms_restart", 3, "mdi:battery-sync"),
    ("emergency_charging", 4, "mdi:battery-alert"),
]


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


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Livoltek buttons from a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    if not runtime.get("has_control"):
        return

    coordinator = runtime["coordinator"]
    api = runtime["api"]
    entry_data = entry.data

    buttons = []
    for key, control_type, icon in BUTTON_DEFINITIONS:
        buttons.append(
            LivoltekControlButton(
                coordinator=coordinator,
                api=api,
                entry_data=entry_data,
                button_key=key,
                control_type=control_type,
                icon=icon,
            )
        )

    async_add_entities(buttons)


class LivoltekControlButton(ButtonEntity):
    """A button entity for Livoltek inverter control."""

    def __init__(
        self,
        coordinator,
        api,
        entry_data: dict,
        button_key: str,
        control_type: int,
        icon: str,
    ) -> None:
        self._coordinator = coordinator
        self._api = api
        self._entry_data = entry_data
        self._button_key = button_key
        self._control_type = control_type

        site_id = entry_data.get(CONF_SITE_ID, "")
        device_sn = entry_data.get(CONF_DEVICE_SN, "")
        uid = f"livoltek_{site_id}_{device_sn}_{button_key}"

        self._attr_unique_id = uid
        self._attr_translation_key = button_key
        self._attr_has_entity_name = True
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self):
        return _build_device_info(self._entry_data, self._coordinator.data)

    async def async_press(self) -> None:
        """Handle the button press."""
        account = self._entry_data.get(CONF_ACCOUNT, "")
        pwd_md5 = self._entry_data.get(CONF_PASSWORD, "")
        device_sn = self._entry_data.get(CONF_DEVICE_SN, "")

        await self._api.remote_start_or_stop(
            account=account,
            pwd_md5=pwd_md5,
            sn=device_sn,
            control_type=self._control_type,
        )
