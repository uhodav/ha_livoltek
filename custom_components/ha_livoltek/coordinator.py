"""Coordinators for Livoltek ESS integration.

Two coordinators split the API load:
- Medium (user-configurable) — public API (power flow, overview, storage …)
- Slow   (1 h)  — daily energy report (rate-limited server-side)
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
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
    STATIC_DATA_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


# ── Base coordinator ─────────────────────────────────────────────────

class _LivoltekBaseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Base coordinator with exponential backoff and token persistence."""

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

    # ── Backoff ──────────────────────────────────────────────────────

    def _record_failure(self) -> None:
        """Increase consecutive failure count and apply exponential backoff."""
        self._consecutive_failures += 1
        idx = min(self._consecutive_failures - 1, len(BACKOFF_INTERVALS) - 1)
        self.update_interval = max(self._normal_interval, BACKOFF_INTERVALS[idx])
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

    def _persist_token(self) -> None:
        """Save refreshed auth token to config entry data."""
        if self._api.auth_token and self._api.auth_token != self._entry.data.get(CONF_AUTH_TOKEN):
            new_data = {**self._entry.data, CONF_AUTH_TOKEN: self._api.auth_token}
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data, translating API errors and applying backoff."""
        try:
            await self._api.ensure_token()
            result = await self._async_fetch()
        except LivoltekAuthError as err:
            self._record_failure()
            raise ConfigEntryAuthFailed(str(err)) from err
        except LivoltekApiError as err:
            self._record_failure()
            raise UpdateFailed(f"{self.name}: {err}") from err

        self._record_success()
        self._persist_token()
        return result

    async def _async_fetch(self) -> dict[str, Any]:
        """Override in subclass."""
        raise NotImplementedError


def _first_if_list(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else {}
    return value


def _normalize_alarms(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        records = value.get("list") or value.get("records") or []
        total = value.get("count") or value.get("total") or len(records)
        return {"records": records, "total": total}
    if isinstance(value, list):
        return {"records": value, "total": len(value)}
    return {"records": [], "total": 0}


def _identity(value: Any) -> Any:
    return value


# (fetch, transform, required)
_Request = tuple[Callable[[], Awaitable[Any]], Callable[[Any], Any], bool]

_MEDIUM_RESULT_KEYS = (
    "power_flow", "overview", "storage", "device_electricity", "social",
    "alarms", "site_details", "device_details", "realtime",
    "site_installer", "site_owner", "device_basic", "device_description",
)


# ── Medium coordinator (public API) ──────────────────────────────────

class LivoltekMediumCoordinator(_LivoltekBaseCoordinator):
    """Polls public API at user-configurable interval."""

    _MAX_PARALLEL_REQUESTS = 4

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
        self._static_cache: dict[str, Any] = {}
        self._static_fetched_at: float | None = None
        self._semaphore = asyncio.Semaphore(self._MAX_PARALLEL_REQUESTS)

    def _requests(self) -> dict[str, _Request]:
        """Requests polled on every update."""
        api, site_id, sn = self._api, self._site_id, self._device_sn
        requests: dict[str, _Request] = {}
        if GROUP_POWER_FLOW in self._enabled:
            requests["power_flow"] = (lambda: api.get_current_power_flow(site_id), _identity, True)
        if GROUP_OVERVIEW in self._enabled:
            requests["overview"] = (lambda: api.get_site_overview(site_id), _identity, True)
        if GROUP_STORAGE in self._enabled:
            requests["storage"] = (lambda: api.get_storage_info(site_id), _identity, False)
        if GROUP_DEVICE_ELECTRICITY in self._enabled and self._device_id:
            requests["device_electricity"] = (lambda: api.get_device_real_electricity(self._device_id), _identity, False)
        if GROUP_ALARMS in self._enabled:
            requests["alarms"] = (lambda: api.get_device_alarms(site_id, sn), _normalize_alarms, False)
        if GROUP_SITE_DETAILS in self._enabled:
            requests["site_details"] = (lambda: api.get_site_details(site_id), _identity, False)
        if GROUP_DEVICE_DETAILS in self._enabled:
            requests["device_details"] = (lambda: api.get_device_details(site_id, sn), _identity, False)
        if GROUP_REALTIME in self._enabled:
            requests["realtime"] = (lambda: api.get_device_realtime(site_id, sn), _identity, False)
        if GROUP_DEVICE_BASIC in self._enabled:
            requests["device_basic"] = (lambda: api.get_device_basic_data(sn), _first_if_list, False)
        return requests

    def _static_requests(self) -> dict[str, _Request]:
        """Requests for rarely changing data, polled every STATIC_DATA_INTERVAL."""
        api, site_id, sn = self._api, self._site_id, self._device_sn
        requests: dict[str, _Request] = {}
        if GROUP_SOCIAL in self._enabled:
            requests["social"] = (lambda: api.get_social_contribution(site_id), _identity, False)
        if GROUP_SITE_INSTALLER in self._enabled:
            requests["site_installer"] = (lambda: api.get_site_installer(site_id), _first_if_list, False)
        if GROUP_SITE_OWNER in self._enabled:
            requests["site_owner"] = (lambda: api.get_site_owner(site_id), _first_if_list, False)
        if self._has_control:
            requests["device_description"] = (lambda: api.get_device_description(sn), _identity, False)
        return requests

    async def _fetch_one(self, key: str, request: _Request) -> Any:
        """Fetch one endpoint; optional endpoints return None on API errors."""
        fetch, transform, required = request
        async with self._semaphore:
            try:
                return transform(await fetch() or {}) or {}
            except LivoltekAuthError:
                raise
            except LivoltekApiError as err:
                if required:
                    raise
                _LOGGER.warning("%s not available for %s: %s", key, self._device_sn, err)
                return None

    async def _fetch_all(self, requests: dict[str, _Request]) -> dict[str, Any]:
        keys = list(requests)
        values = await asyncio.gather(
            *(self._fetch_one(key, requests[key]) for key in keys),
            return_exceptions=True,
        )
        errors = [v for v in values if isinstance(v, BaseException)]
        if errors:
            raise next((e for e in errors if isinstance(e, LivoltekAuthError)), errors[0])
        return dict(zip(keys, values))

    async def _async_fetch(self) -> dict[str, Any]:
        """Fetch data from Livoltek public API."""
        now = self.hass.loop.time()
        static_due = (
            self._static_fetched_at is None
            or now - self._static_fetched_at >= STATIC_DATA_INTERVAL.total_seconds()
        )
        requests = self._requests()
        static_requests = self._static_requests() if static_due else {}

        fetched = await self._fetch_all({**requests, **static_requests})

        if static_due:
            for key in static_requests:
                if fetched[key] is not None:
                    self._static_cache[key] = fetched[key]
            if all(fetched[key] is not None for key in static_requests):
                self._static_fetched_at = now

        previous = self.data or {}
        result: dict[str, Any] = {}
        for key in _MEDIUM_RESULT_KEYS:
            if key in requests:
                result[key] = fetched[key] if fetched[key] is not None else {}
            else:
                result[key] = self._static_cache.get(key) or previous.get(key) or {}
        return result


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

    async def _async_fetch(self) -> dict[str, Any]:
        """Fetch daily energy report."""
        if GROUP_DAILY_ENERGY not in self._enabled or not self._device_id:
            return {"daily_energy": {}}
        try:
            daily = await self._api.get_daily_energy_report(self._device_id) or {}
        except LivoltekAuthError:
            raise
        except LivoltekApiError as err:
            _LOGGER.warning("Daily energy report not available for device %s: %s", self._device_id, err)
            daily = (self.data or {}).get("daily_energy") or {}
        return {"daily_energy": daily}
