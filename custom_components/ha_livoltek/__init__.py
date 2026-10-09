"""The Livoltek integration."""
import json
import logging
from datetime import timedelta

import voluptuous as vol
from pathlib import Path
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from .api import LivoltekApi, LivoltekApiError
from .card_loader import async_register_cards
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
    CONF_USE_PORTAL,
    CONF_WORKMODE,
    CONF_WORK_MODE_HIDDEN,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    GROUP_DAILY_ENERGY,
    GROUP_PORTAL,
    MIN_UPDATE_INTERVAL,
    PORTAL_SERVERS,
    SERVERS,
)
from .coordinator import (
    LivoltekMediumCoordinator,
    LivoltekPortalCoordinator,
    LivoltekSlowCoordinator,
)
from .portal import LivoltekPortalApi

_LOGGER = logging.getLogger(__name__)

BASE_PLATFORMS = ["sensor"]
CONTROL_PLATFORMS = ["button", "select"]
PORTAL_PLATFORMS = ["binary_sensor"]

FRONTEND_KEY = "_frontend_registered"

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
        integration = await async_get_integration(hass, DOMAIN)
        await async_register_cards(
            hass, DOMAIN, frontend_dir, ["livoltek-power-card.js"], "/ha_livoltek", str(integration.version)
        )
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
    use_portal = has_control and bool(entry.data.get(CONF_USE_PORTAL))
    platforms = (
        BASE_PLATFORMS
        + (CONTROL_PLATFORMS if has_control else [])
        + (PORTAL_PLATFORMS if use_portal else [])
    )

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
    coord_portal = None
    if use_portal:
        portal = LivoltekPortalApi(
            PORTAL_SERVERS[server_type],
            entry.data[CONF_ACCOUNT],
            entry.data[CONF_PASSWORD],
            async_get_clientsession(hass),
        )
        coord_portal = LivoltekPortalCoordinator(hass, entry, portal)

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coord_medium,
        "coordinator_slow": coord_slow,
        "coordinator_portal": coord_portal,
        "api": api,
        "config": entry.data,
        "has_control": has_control,
        "platforms": platforms,
        "enabled_groups": enabled_groups,
        "current_workmode": entry.data.get(CONF_WORKMODE),
    }

    # First refresh — medium is mandatory, slow is optional
    await coord_medium.async_config_entry_first_refresh()

    # Slow coordinator can fail without blocking setup
    if GROUP_DAILY_ENERGY in enabled_groups:
        try:
            await coord_slow.async_config_entry_first_refresh()
        except Exception:  # noqa: BLE001
            _LOGGER.warning("Slow coordinator first refresh failed, will retry")

    # Portal is optional: a failure leaves its entities unavailable and is retried
    if coord_portal is not None:
        await coord_portal.async_refresh()
        if not coord_portal.last_update_success:
            _LOGGER.warning("Livoltek portal is not available, will retry: %s", coord_portal.last_exception)

    _sync_work_mode_entities(hass, entry, site_id, device_sn, use_portal)

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

SCHEDULE_LIST_SCHEMA = vol.Schema([SCHEDULE_ENTRY_SCHEMA])

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("device_sn"): str,
        vol.Required("work_mode"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
        vol.Optional("schedule_list"): vol.Any(
            SCHEDULE_LIST_SCHEMA,
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
                    schedule_list = SCHEDULE_LIST_SCHEMA(json.loads(schedule_raw))
                except (json.JSONDecodeError, TypeError, vol.Invalid) as err:
                    raise ServiceValidationError(f"Invalid schedule_list: {err}") from err
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
            raise ServiceValidationError(f"No Livoltek integration found for device_sn={device_sn}")

        if not runtime.get("has_control"):
            raise ServiceValidationError(f"BESS control not configured for device {device_sn}")

        api = runtime["api"]
        account = entry.data.get(CONF_ACCOUNT, "")
        pwd_md5 = entry.data.get(CONF_PASSWORD, "")

        try:
            await api.set_work_mode(
                account=account,
                pwd_md5=pwd_md5,
                sn=device_sn,
                work_mode=work_mode,
                schedule_list=schedule_list,
            )
        except LivoltekApiError as err:
            raise HomeAssistantError(f"Failed to set work mode: {err}") from err

        # Track selected mode in runtime
        runtime["current_workmode"] = str(work_mode)
        if runtime.get("coordinator_portal") is not None:
            runtime["coordinator_portal"].work_mode_changed(str(work_mode))
        new_data = {**entry.data, CONF_WORKMODE: str(work_mode)}
        hass.config_entries.async_update_entry(entry, data=new_data)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_WORK_MODE_SCHEDULE,
        handle_set_work_mode_schedule,
        schema=SERVICE_SCHEMA,
    )


def _sync_work_mode_entities(
    hass: HomeAssistant, entry: ConfigEntry, site_id: str, device_sn: str, use_portal: bool
) -> None:
    """Work mode sensor/select need the portal: only it reports the actual work mode.

    Without the portal they are disabled once; with it, entities disabled by the
    integration are enabled again. Entities disabled by the user are left alone.
    """
    if not use_portal and entry.data.get(CONF_WORK_MODE_HIDDEN):
        return
    ent_reg = er.async_get(hass)
    for platform, key in (("sensor", "work_mode"), ("select", "work_mode_select")):
        entity_id = ent_reg.async_get_entity_id(platform, DOMAIN, f"livoltek_{site_id}_{device_sn}_{key}")
        entity = ent_reg.async_get(entity_id) if entity_id else None
        if entity is None:
            continue
        if use_portal and entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
            ent_reg.async_update_entity(entity_id, disabled_by=None)
        elif not use_portal and entity.disabled_by is None:
            ent_reg.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)
    if not entry.data.get(CONF_WORK_MODE_HIDDEN):
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_WORK_MODE_HIDDEN: True})


def _cleanup_orphan_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove devices whose group is no longer in enabled_groups."""
    enabled_groups = set(entry.data.get(CONF_ENABLED_GROUPS, ALL_GROUPS))
    if entry.data.get(CONF_USE_PORTAL) and entry.data.get(CONF_ACCOUNT):
        enabled_groups.add(GROUP_PORTAL)
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
