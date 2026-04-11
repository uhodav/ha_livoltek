"""The Livoltek integration."""
import json
import logging
import time
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
    ENERGY_REPORT_INTERVAL,
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

_LOGGER = logging.getLogger(__name__)

BASE_PLATFORMS = ["sensor"]
CONTROL_PLATFORMS = ["button", "select"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Livoltek from a config entry."""
    hass.data.setdefault(DOMAIN, {})

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

    api = LivoltekApi(base_url, secuid, key, user_token, auth_token)

    update_interval = int(
        entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    )
    if update_interval < MIN_UPDATE_INTERVAL:
        update_interval = MIN_UPDATE_INTERVAL

    # Throttle state for daily energy report (max 1x/hour)
    energy_state: dict = {"last_fetch": 0.0, "cached": {}}

    async def async_update_data() -> dict:
        """Fetch data from Livoltek API."""
        try:
            result: dict = {}

            # ── Power flow ───────────────────────────────────────────
            if GROUP_POWER_FLOW in enabled_groups:
                result["power_flow"] = await api.get_current_power_flow(site_id) or {}
            else:
                result["power_flow"] = {}

            # ── Overview ─────────────────────────────────────────────
            if GROUP_OVERVIEW in enabled_groups:
                result["overview"] = await api.get_site_overview(site_id) or {}
            else:
                result["overview"] = {}

            # ── Storage (ESS) ────────────────────────────────────────
            if GROUP_STORAGE in enabled_groups:
                try:
                    result["storage"] = await api.get_storage_info(site_id) or {}
                except LivoltekApiError:
                    _LOGGER.error("Storage info not available for site %s", site_id)
                    result["storage"] = {}
            else:
                result["storage"] = {}

            # ── Device electricity ───────────────────────────────────
            if GROUP_DEVICE_ELECTRICITY in enabled_groups and device_id:
                try:
                    result["device_electricity"] = await api.get_device_real_electricity(device_id) or {}
                except LivoltekApiError:
                    _LOGGER.error("Device electricity not available for device %s", device_id)
                    result["device_electricity"] = {}
            else:
                result["device_electricity"] = {}

            # ── Social contribution ──────────────────────────────────
            if GROUP_SOCIAL in enabled_groups:
                try:
                    result["social"] = await api.get_social_contribution(site_id) or {}
                except LivoltekApiError:
                    _LOGGER.error("Social contribution not available for site %s", site_id)
                    result["social"] = {}
            else:
                result["social"] = {}

            # ── Alarms ───────────────────────────────────────────────
            if GROUP_ALARMS in enabled_groups:
                try:
                    alarms_resp = await api.get_device_alarms(site_id, device_sn)
                    if isinstance(alarms_resp, dict):
                        records = alarms_resp.get("list") or alarms_resp.get("records") or []
                        total = alarms_resp.get("count") or alarms_resp.get("total") or len(records)
                        result["alarms"] = {"records": records, "total": total}
                    elif isinstance(alarms_resp, list):
                        result["alarms"] = {"records": alarms_resp, "total": len(alarms_resp)}
                    else:
                        result["alarms"] = {"records": [], "total": 0}
                except LivoltekApiError:
                    _LOGGER.error("Alarms not available for device %s", device_sn)
                    result["alarms"] = {}
            else:
                result["alarms"] = {}

            # ── Site details ─────────────────────────────────────────
            if GROUP_SITE_DETAILS in enabled_groups:
                try:
                    result["site_details"] = await api.get_site_details(site_id) or {}
                except LivoltekApiError:
                    _LOGGER.error("Site details not available for site %s", site_id)
                    result["site_details"] = {}
            else:
                result["site_details"] = {}

            # ── Device details ───────────────────────────────────────
            if GROUP_DEVICE_DETAILS in enabled_groups:
                try:
                    result["device_details"] = await api.get_device_details(site_id, device_sn) or {}
                except LivoltekApiError:
                    _LOGGER.error("Device details not available for %s", device_sn)
                    result["device_details"] = {}
            else:
                result["device_details"] = {}

            # ── Realtime technical parameters ────────────────────────
            if GROUP_REALTIME in enabled_groups:
                try:
                    result["realtime"] = await api.get_device_realtime(site_id, device_sn) or {}
                except LivoltekApiError:
                    _LOGGER.error("Realtime data not available for %s", device_sn)
                    result["realtime"] = {}
            else:
                result["realtime"] = {}

            # ── Daily energy report (throttled: 1x/hour) ────────────
            if GROUP_DAILY_ENERGY in enabled_groups and device_id:
                now_ts = time.monotonic()
                if now_ts - energy_state["last_fetch"] >= ENERGY_REPORT_INTERVAL:
                    try:
                        daily = await api.get_daily_energy_report(device_id)
                        energy_state["cached"] = daily or {}
                        energy_state["last_fetch"] = now_ts
                    except LivoltekApiError:
                        _LOGGER.error("Daily energy report not available for device %s", device_id)
                result["daily_energy"] = energy_state["cached"]
            else:
                result["daily_energy"] = {}

            # ── Site installer ───────────────────────────────────────
            if GROUP_SITE_INSTALLER in enabled_groups:
                try:
                    raw_inst = await api.get_site_installer(site_id)
                    if isinstance(raw_inst, list):
                        result["site_installer"] = raw_inst[0] if raw_inst else {}
                    else:
                        result["site_installer"] = raw_inst or {}
                except LivoltekApiError:
                    _LOGGER.error("Site installer not available for site %s", site_id)
                    result["site_installer"] = {}
            else:
                result["site_installer"] = {}

            # ── Site owner ───────────────────────────────────────────
            if GROUP_SITE_OWNER in enabled_groups:
                try:
                    raw_owner = await api.get_site_owner(site_id)
                    if isinstance(raw_owner, list):
                        result["site_owner"] = raw_owner[0] if raw_owner else {}
                    else:
                        result["site_owner"] = raw_owner or {}
                except LivoltekApiError:
                    _LOGGER.error("Site owner not available for site %s", site_id)
                    result["site_owner"] = {}
            else:
                result["site_owner"] = {}

            # ── Device basic data ────────────────────────────────────
            if GROUP_DEVICE_BASIC in enabled_groups:
                try:
                    raw_basic = await api.get_device_basic_data(device_sn)
                    # API may return a list; extract first element
                    if isinstance(raw_basic, list):
                        result["device_basic"] = raw_basic[0] if raw_basic else {}
                    else:
                        result["device_basic"] = raw_basic or {}
                except LivoltekApiError:
                    _LOGGER.error("Device basic data not available for %s", device_sn)
                    result["device_basic"] = {}
            else:
                result["device_basic"] = {}

            # ── Device description (BESS capabilities) ───────────────
            device_description = None
            if has_control:
                try:
                    device_description = await api.get_device_description(device_sn)
                except LivoltekApiError as err:
                    _LOGGER.error("Device description not available for %s: %s", device_sn, err)
            result["device_description"] = device_description or {}

            # ── Persist refreshed auth token ─────────────────────────
            if api.auth_token and api.auth_token != entry.data.get(CONF_AUTH_TOKEN):
                new_data = {**entry.data, CONF_AUTH_TOKEN: api.auth_token}
                hass.config_entries.async_update_entry(entry, data=new_data)

            return result
        except LivoltekApiError as err:
            raise UpdateFailed(f"Error fetching data from Livoltek API: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"Livoltek {site_id}",
        update_method=async_update_data,
        update_interval=timedelta(minutes=update_interval),
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
        "config": entry.data,
        "has_control": has_control,
        "platforms": platforms,
        "enabled_groups": enabled_groups,
        "current_workmode": entry.data.get(CONF_WORKMODE),
    }

    # Keep coordinator alive
    coordinator.async_add_listener(lambda: None)

    await coordinator.async_config_entry_first_refresh()

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
    """Apply updated options to a running coordinator."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not runtime:
        return
    coordinator = runtime.get("coordinator")
    if coordinator is None:
        return

    new_interval = int(
        entry.options.get(CONF_UPDATE_INTERVAL, entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    )
    if new_interval < MIN_UPDATE_INTERVAL:
        new_interval = MIN_UPDATE_INTERVAL
    coordinator.update_interval = timedelta(minutes=new_interval)

    # Clean up devices for groups that are no longer enabled
    _cleanup_orphan_devices(hass, entry)

    await coordinator.async_request_refresh()


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
