"""Diagnostics support for Livoltek."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCOUNT,
    CONF_AUTH_TOKEN,
    CONF_KEY,
    CONF_PASSWORD,
    CONF_SECUID,
    CONF_TOKEN,
    DOMAIN,
)

TO_REDACT = {
    # credentials
    CONF_SECUID, CONF_KEY, CONF_TOKEN, CONF_AUTH_TOKEN, CONF_ACCOUNT, CONF_PASSWORD,
    "access_token", "userToken",
    # owner / location
    "name", "email", "loginAccount", "phone", "address",
    "latitude", "longitude", "lat", "lng",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry with credentials and personal data removed."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinators = {}
    for key in ("coordinator", "coordinator_slow", "coordinator_portal"):
        coordinator = runtime.get(key)
        if coordinator is None:
            continue
        coordinators[key] = {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "last_exception": str(coordinator.last_exception) if coordinator.last_exception else None,
            "data": coordinator.data,
        }
    return async_redact_data(
        {
            "entry": {"data": dict(entry.data), "options": dict(entry.options)},
            "coordinators": coordinators,
        },
        TO_REDACT,
    )
