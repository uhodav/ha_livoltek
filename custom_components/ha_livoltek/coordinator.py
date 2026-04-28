"""Coordinators for Livoltek ESS integration.

Two coordinators split the API load:
- Medium (user-configurable) — public API (power flow, overview, storage …)
- Slow   (1 h)  — daily energy report (rate-limited server-side)
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LivoltekApi, LivoltekApiError, LivoltekAuthError
from .const import (
    ALL_GROUPS,
    BACKOFF_INTERVALS,
    CONF_AUTH_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_SN,
    CONF_ENABLED_GROUPS,
    CONF_SITE_ID,
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
    SCAN_INTERVAL_SLOW,
)

_LOGGER = logging.getLogger(__name__)


# ── Base coordinator ─────────────────────────────────────────────────

class _LivoltekBaseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Base coordinator with startup jitter, exponential backoff and token persistence."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: LivoltekApi,
        *,
        name: str,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
        )
        self._api = api
        self._entry = entry
        self._consecutive_failures: int = 0
        self._normal_interval = update_interval
        self._first_refresh = True

    # ── Backoff ──────────────────────────────────────────────────────

    def _record_failure(self) -> None:
        """Increase consecutive failure count and apply exponential backoff."""
        self._consecutive_failures += 1
        idx = min(self._consecutive_failures - 1, len(BACKOFF_INTERVALS) - 1)
        self.update_interval = BACKOFF_INTERVALS[idx]
        _LOGGER.debug(
            "%s: failure #%d, backing off to %s",
            self.name, self._consecutive_failures, self.update_interval,
        )

    def _record_success(self) -> None:
        """Reset failure count and restore normal interval."""
        if self._consecutive_failures > 0:
            _LOGGER.debug(
                "%s: recovered after %d failures, restoring %s interval",
                self.name, self._consecutive_failures, self._normal_interval,
            )
        self._consecutive_failures = 0
        self.update_interval = self._normal_interval

    # ── Token helpers ────────────────────────────────────────────────

    async def _ensure_token(self) -> None:
        """Call api.ensure_token, converting auth errors to ConfigEntryAuthFailed."""
        try:
            await self._api.ensure_token()
        except LivoltekAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

    def _persist_token(self) -> None:
        """Save refreshed auth token to config entry data."""
        if self._api.auth_token and self._api.auth_token != self._entry.data.get(CONF_AUTH_TOKEN):
            new_data = {**self._entry.data, CONF_AUTH_TOKEN: self._api.auth_token}
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)

    # ── Jitter ───────────────────────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        """Override in subclass."""
        raise NotImplementedError

    async def _async_update_data_with_jitter(self) -> dict[str, Any]:
        """Wrap update with optional startup jitter."""
        if self._first_refresh:
            self._first_refresh = False
            # Skip jitter on very first refresh so HA shows data quickly
        return await self._async_update_data()


# ── Medium coordinator (public API) ──────────────────────────────────

class LivoltekMediumCoordinator(_LivoltekBaseCoordinator):
    """Polls public API at user-configurable interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: LivoltekApi,
        *,
        update_interval: timedelta,
        has_control: bool = False,
    ) -> None:
        super().__init__(
            hass,
            entry,
            api,
            name=f"Livoltek Medium {entry.data.get(CONF_SITE_ID, '')}",
            update_interval=update_interval,
        )
        self._site_id = entry.data.get(CONF_SITE_ID, "")
        self._device_sn = entry.data.get(CONF_DEVICE_SN, "")
        self._device_id = entry.data.get(CONF_DEVICE_ID)
        self._has_control = has_control
        self._enabled = set(entry.data.get(CONF_ENABLED_GROUPS, ALL_GROUPS))

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Livoltek public API."""
        await self._ensure_token()

        try:
            result: dict[str, Any] = {}

            # ── Power flow ───────────────────────────────────────────
            if GROUP_POWER_FLOW in self._enabled:
                result["power_flow"] = await self._api.get_current_power_flow(self._site_id) or {}
            else:
                result["power_flow"] = {}

            # ── Overview ─────────────────────────────────────────────
            if GROUP_OVERVIEW in self._enabled:
                result["overview"] = await self._api.get_site_overview(self._site_id) or {}
            else:
                result["overview"] = {}

            # ── Storage (ESS) ────────────────────────────────────────
            if GROUP_STORAGE in self._enabled:
                try:
                    result["storage"] = await self._api.get_storage_info(self._site_id) or {}
                except LivoltekApiError:
                    _LOGGER.error("Storage info not available for site %s", self._site_id)
                    result["storage"] = {}
            else:
                result["storage"] = {}

            # ── Device electricity ───────────────────────────────────
            if GROUP_DEVICE_ELECTRICITY in self._enabled and self._device_id:
                try:
                    result["device_electricity"] = await self._api.get_device_real_electricity(self._device_id) or {}
                except LivoltekApiError:
                    _LOGGER.error("Device electricity not available for device %s", self._device_id)
                    result["device_electricity"] = {}
            else:
                result["device_electricity"] = {}

            # ── Social contribution ──────────────────────────────────
            if GROUP_SOCIAL in self._enabled:
                try:
                    result["social"] = await self._api.get_social_contribution(self._site_id) or {}
                except LivoltekApiError:
                    _LOGGER.error("Social contribution not available for site %s", self._site_id)
                    result["social"] = {}
            else:
                result["social"] = {}

            # ── Alarms ───────────────────────────────────────────────
            if GROUP_ALARMS in self._enabled:
                try:
                    alarms_resp = await self._api.get_device_alarms(self._site_id, self._device_sn)
                    if isinstance(alarms_resp, dict):
                        records = alarms_resp.get("list") or alarms_resp.get("records") or []
                        total = alarms_resp.get("count") or alarms_resp.get("total") or len(records)
                        result["alarms"] = {"records": records, "total": total}
                    elif isinstance(alarms_resp, list):
                        result["alarms"] = {"records": alarms_resp, "total": len(alarms_resp)}
                    else:
                        result["alarms"] = {"records": [], "total": 0}
                except LivoltekApiError:
                    _LOGGER.error("Alarms not available for device %s", self._device_sn)
                    result["alarms"] = {}
            else:
                result["alarms"] = {}

            # ── Site details ─────────────────────────────────────────
            if GROUP_SITE_DETAILS in self._enabled:
                try:
                    result["site_details"] = await self._api.get_site_details(self._site_id) or {}
                except LivoltekApiError:
                    _LOGGER.error("Site details not available for site %s", self._site_id)
                    result["site_details"] = {}
            else:
                result["site_details"] = {}

            # ── Device details ───────────────────────────────────────
            if GROUP_DEVICE_DETAILS in self._enabled:
                try:
                    result["device_details"] = await self._api.get_device_details(self._site_id, self._device_sn) or {}
                except LivoltekApiError:
                    _LOGGER.error("Device details not available for %s", self._device_sn)
                    result["device_details"] = {}
            else:
                result["device_details"] = {}

            # ── Realtime technical parameters ────────────────────────
            if GROUP_REALTIME in self._enabled:
                try:
                    result["realtime"] = await self._api.get_device_realtime(self._site_id, self._device_sn) or {}
                except LivoltekApiError:
                    _LOGGER.error("Realtime data not available for %s", self._device_sn)
                    result["realtime"] = {}
            else:
                result["realtime"] = {}

            # ── Site installer ───────────────────────────────────────
            if GROUP_SITE_INSTALLER in self._enabled:
                try:
                    raw_inst = await self._api.get_site_installer(self._site_id)
                    if isinstance(raw_inst, list):
                        result["site_installer"] = raw_inst[0] if raw_inst else {}
                    else:
                        result["site_installer"] = raw_inst or {}
                except LivoltekApiError:
                    _LOGGER.error("Site installer not available for site %s", self._site_id)
                    result["site_installer"] = {}
            else:
                result["site_installer"] = {}

            # ── Site owner ───────────────────────────────────────────
            if GROUP_SITE_OWNER in self._enabled:
                try:
                    raw_owner = await self._api.get_site_owner(self._site_id)
                    if isinstance(raw_owner, list):
                        result["site_owner"] = raw_owner[0] if raw_owner else {}
                    else:
                        result["site_owner"] = raw_owner or {}
                except LivoltekApiError:
                    _LOGGER.error("Site owner not available for site %s", self._site_id)
                    result["site_owner"] = {}
            else:
                result["site_owner"] = {}

            # ── Device basic data ────────────────────────────────────
            if GROUP_DEVICE_BASIC in self._enabled:
                try:
                    raw_basic = await self._api.get_device_basic_data(self._device_sn)
                    if isinstance(raw_basic, list):
                        result["device_basic"] = raw_basic[0] if raw_basic else {}
                    else:
                        result["device_basic"] = raw_basic or {}
                except LivoltekApiError:
                    _LOGGER.error("Device basic data not available for %s", self._device_sn)
                    result["device_basic"] = {}
            else:
                result["device_basic"] = {}

            # ── Device description (BESS capabilities) ───────────────
            device_description = None
            if self._has_control:
                try:
                    device_description = await self._api.get_device_description(self._device_sn)
                except LivoltekApiError as err:
                    _LOGGER.error("Device description not available for %s: %s", self._device_sn, err)
            result["device_description"] = device_description or {}

            self._record_success()
            self._persist_token()
            return result

        except LivoltekAuthError as err:
            self._record_failure()
            raise ConfigEntryAuthFailed(str(err)) from err
        except LivoltekApiError as err:
            self._record_failure()
            raise UpdateFailed(f"Medium coordinator error: {err}") from err


# ── Slow coordinator (daily energy) ──────────────────────────────────

class LivoltekSlowCoordinator(_LivoltekBaseCoordinator):
    """Polls daily energy report every hour (API is rate-limited 1x/hour)."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: LivoltekApi,
    ) -> None:
        super().__init__(
            hass,
            entry,
            api,
            name=f"Livoltek Slow {entry.data.get(CONF_SITE_ID, '')}",
            update_interval=SCAN_INTERVAL_SLOW,
        )
        self._device_id = entry.data.get(CONF_DEVICE_ID)
        self._enabled = set(entry.data.get(CONF_ENABLED_GROUPS, ALL_GROUPS))

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch daily energy report."""
        await self._ensure_token()

        result: dict[str, Any] = {}
        try:
            if GROUP_DAILY_ENERGY in self._enabled and self._device_id:
                try:
                    result["daily_energy"] = await self._api.get_daily_energy_report(self._device_id) or {}
                except LivoltekApiError:
                    _LOGGER.error("Daily energy report not available for device %s", self._device_id)
                    result["daily_energy"] = {}
            else:
                result["daily_energy"] = {}

            self._record_success()
            self._persist_token()
            return result

        except LivoltekAuthError as err:
            self._record_failure()
            raise ConfigEntryAuthFailed(str(err)) from err
        except LivoltekApiError as err:
            self._record_failure()
            raise UpdateFailed(f"Slow coordinator error: {err}") from err
