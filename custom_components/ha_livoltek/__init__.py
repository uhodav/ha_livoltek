"""The Livoltek integration."""
import json
import logging
from datetime import timedelta

import voluptuous as vol
from pathlib import Path
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LivoltekApi, LivoltekApiError
from .const import (
    ALL_GROUPS,
    CONF_ACCOUNT,
    CONF_AUTH_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_SN,
    CONF_ENABLED_GROUPS,
    CONF_KEY,
    CONF_PASSWORD,
    CONF_SECUID,
    CONF_SERVER_TYPE,
    CONF_SITE_ID,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    CONF_WORKMODE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    GROUP_ALARMS,
    GROUP_DAILY_ENERGY,
    GROUP_DEVICE_BASIC,
    GROUP_DEVICE_DETAILS,
    GROUP_DEVICE_ELECTRICITY,
    GROUP_OVERVIEW,
    GROUP_POWER_FLOW,
    GROUP_REALTIME,
    GROUP_SITE_DETAILS,
    GROUP_SITE_INSTALLER,
    GROUP_SITE_OWNER,
    GROUP_SOCIAL,
    GROUP_STORAGE,
    MIN_UPDATE_INTERVAL,
    SERVERS,
)
from .coordinator import (
    LivoltekMediumCoordinator,
    LivoltekSlowCoordinator,
)

DOMAIN = "ha_livoltek"
_LOGGER = logging.getLogger(__name__)

BASE_PLATFORMS = ["sensor"]
CONTROL_PLATFORMS = ["button", "select"]

FRONTEND_KEY = "_frontend_registered"
FRONTEND_URL = "/ha_livoltek/livoltek-power-card.js"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Livoltek from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    if not hass.data[DOMAIN].get(FRONTEND_KEY):
        frontend_dir = Path(__file__).parent / "frontend"
        files = [
            ("livoltek-power-card.js", "/ha_livoltek/livoltek-power-card.js"),
            ("livoltek-power-card-editor.js", "/ha_livoltek/livoltek-power-card-editor.js"),
        ]
        await hass.http.async_register_static_paths([
            StaticPathConfig(url, str(frontend_dir / fname), cache_headers=False)
            for fname, url in files
        ])
        hass.data[DOMAIN][FRONTEND_KEY] = True

    server_type = entry.data[CONF_SERVER_TYPE]
    base_url = SERVERS[server_type]
    secuid = entry.data[CONF_SECUID]
    key = entry.data[CONF_KEY]
    user_token = entry.data[CONF_TOKEN]
    auth_token = entry.data.get(CONF_AUTH_TOKEN)
    site_id = entry.data[CONF_SITE_ID]
    device_sn = entry.data[CONF_DEVICE_SN]
    device_id = entry.data.get(CONF_DEVICE_ID)

    # BESS control credentials (optional)
    has_control = bool(entry.data.get(CONF_ACCOUNT) and entry.data.get(CONF_PASSWORD))
    platforms = BASE_PLATFORMS + (CONTROL_PLATFORMS if has_control else [])

    # Enabled endpoint groups (default: all for backward compatibility)
    enabled_groups = set(entry.data.get(CONF_ENABLED_GROUPS, ALL_GROUPS))

    api = LivoltekApi(
        base_url, secuid, key, user_token, auth_token,
        session=async_get_clientsession(hass),
        server_type=server_type,
    )

    update_interval = int(
        entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    )
    if update_interval < MIN_UPDATE_INTERVAL:
        update_interval = MIN_UPDATE_INTERVAL

    coord_medium = LivoltekMediumCoordinator(
        hass, entry, api,
        update_interval=timedelta(minutes=update_interval),
        has_control=has_control,
    )
    coord_slow = LivoltekSlowCoordinator(hass, entry, api)

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coord_medium,
        "coordinator_slow": coord_slow,
        "api": api,
        "config": entry.data,
        "has_control": has_control,
        "platforms": platforms,
        "enabled_groups": enabled_groups,
        "current_workmode": entry.data.get(CONF_WORKMODE),
    }

    # Keep coordinators alive
    coord_medium.async_add_listener(lambda: None)
    coord_slow.async_add_listener(lambda: None)

    # First refresh — medium is mandatory, slow is optional
    await coord_medium.async_config_entry_first_refresh()

    # Slow coordinator can fail without blocking setup
    if GROUP_DAILY_ENERGY in enabled_groups:
        try:
            await coord_slow.async_config_entry_first_refresh()
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Slow coordinator first refresh failed, will retry")

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    # Clean up devices for disabled groups (or leftover single-device from old version)
    _cleanup_orphan_devices(hass, entry)

    # Register services (once per domain)
    if not hass.services.has_service(DOMAIN, "set_work_mode_schedule"):
        _register_services(hass)

    return True


# ── Service definitions ──────────────────────────────────────────────

SERVICE_SET_WORK_MODE_SCHEDULE = "set_work_mode_schedule"

SCHEDULE_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("chargeType"): vol.In([1, 2]),
        vol.Required("startHour"): vol.All(int, vol.Range(min=0, max=23)),
        vol.Required("startMin"): vol.All(int, vol.Range(min=0, max=59)),
        vol.Required("endHour"): vol.All(int, vol.Range(min=0, max=23)),
        vol.Required("endMin"): vol.All(int, vol.Range(min=0, max=59)),
        vol.Optional("chargingDays"): [vol.All(int, vol.Range(min=0, max=6))],
    }
)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("device_sn"): str,
        vol.Required("work_mode"): vol.All(int, vol.Range(min=0, max=10)),
        vol.Optional("schedule_list"): vol.Any(
            [SCHEDULE_ENTRY_SCHEMA],
            str,  # allow JSON string too
        ),
    }
)


def _register_services(hass: HomeAssistant) -> None:
    """Register Livoltek services."""

    async def handle_set_work_mode_schedule(call: ServiceCall) -> None:
        """Handle the set_work_mode_schedule service call."""
        device_sn = call.data["device_sn"]
        work_mode = call.data["work_mode"]
        schedule_raw = call.data.get("schedule_list")

        # Parse schedule_list from JSON string if needed
        schedule_list = None
        if schedule_raw is not None:
            if isinstance(schedule_raw, str):
                try:
                    schedule_list = json.loads(schedule_raw)
                except (json.JSONDecodeError, TypeError) as err:
                    _LOGGER.error("Invalid schedule_list JSON: %s", err)
                    return
            else:
                schedule_list = schedule_raw

        # Find the right config entry by device_sn
        runtime = None
        entry = None
        for eid, rt in hass.data.get(DOMAIN, {}).items():
            if not isinstance(rt, dict):
                continue
            cfg = rt.get("config", {})
            if cfg.get(CONF_DEVICE_SN) == device_sn:
                runtime = rt
                # Find the matching entry
                for e in hass.config_entries.async_entries(DOMAIN):
                    if e.entry_id == eid:
                        entry = e
                        break
                break

        if runtime is None or entry is None:
            _LOGGER.error("No Livoltek integration found for device_sn=%s", device_sn)
            return

        if not runtime.get("has_control"):
            _LOGGER.error("BESS control not configured for device %s", device_sn)
            return

        api = runtime["api"]
        account = entry.data.get(CONF_ACCOUNT, "")
        pwd_md5 = entry.data.get(CONF_PASSWORD, "")

        await api.set_work_mode(
            account=account,
            pwd_md5=pwd_md5,
            sn=device_sn,
            work_mode=work_mode,
            schedule_list=schedule_list,
        )

        # Track selected mode in runtime
        runtime["current_workmode"] = str(work_mode)
        new_data = {**entry.data, CONF_WORKMODE: str(work_mode)}
        hass.config_entries.async_update_entry(entry, data=new_data)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_WORK_MODE_SCHEDULE,
        handle_set_work_mode_schedule,
        schema=SERVICE_SCHEMA,
    )


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply updated options to running coordinators."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not runtime:
        return

    new_interval = int(
        entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    )
    if new_interval < MIN_UPDATE_INTERVAL:
        new_interval = MIN_UPDATE_INTERVAL

    # Only the medium coordinator uses user-configurable interval
    coord_medium = runtime.get("coordinator")
    if coord_medium is not None:
        coord_medium.update_interval = timedelta(minutes=new_interval)
        coord_medium._normal_interval = timedelta(minutes=new_interval)

    # Clean up devices for groups that are no longer enabled
    _cleanup_orphan_devices(hass, entry)

    # Refresh all coordinators
    for key in ("coordinator", "coordinator_fast", "coordinator_slow"):
        coord = runtime.get(key)
        if coord is not None:
            await coord.async_request_refresh()


def _cleanup_orphan_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove devices whose group is no longer in enabled_groups."""
    enabled_groups = set(entry.data.get(CONF_ENABLED_GROUPS, ALL_GROUPS))
    site_id = entry.data.get(CONF_SITE_ID, "")
    device_sn = entry.data.get(CONF_DEVICE_SN, "")

    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        for domain, identifier in device.identifiers:
            if domain != DOMAIN:
                continue
            # Identifier format: "{site_id}_{device_sn}_{group}"
            prefix = f"{site_id}_{device_sn}_"
            if identifier.startswith(prefix):
                group = identifier[len(prefix):]
                if group and group not in enabled_groups:
                    _LOGGER.info("Removing orphan device %s (group %s)", device.name, group)
                    dev_reg.async_remove_device(device.id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow removal of a device from the integration."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Livoltek config entry."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    platforms = runtime.get("platforms", BASE_PLATFORMS)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id, None)
        if runtime:
            api = runtime.get("api")
            if api:
                await api.close()
    return unload_ok
