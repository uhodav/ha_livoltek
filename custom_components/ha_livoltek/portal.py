"""Client for the Livoltek web portal API (unofficial).

The portal API is what the Livoltek web UI uses. It is not documented by
Livoltek, so field names come from observed responses and may change.

Auth: POST /nbp/login/customer {login_account, password: md5} returns a
Bearer JWT (data.access_token) with data.session_expiry_time in unix ms.
POST /ctrller-manager/login/login registers the session (needed for alarms).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.util import dt as dt_util

from .api import LivoltekApiError, LivoltekAuthError, LivoltekConnectionError

_LOGGER = logging.getLogger(__name__)

_SUCCESS_CODE = "operate.success"
_TOKEN_REFRESH_BUFFER_MS = int(timedelta(hours=24).total_seconds() * 1000)
_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)

_LOGIN = "/nbp/login/customer"
_SESSION_REGISTER = "/ctrller-manager/login/login"
_STATIONS = "/ctrller-manager/powerstation/getAllStationInfoToC"
_DEVICES = "/ctrller-manager/powerstation/inverterSelect"
_ENERGY_STORAGE_INFO = "/ctrller-manager/energystorage/energyStorageInfo"
_POINT_INFO = "/hess-ota/device/operation/point/info"
_ALARMS = "/ctrller-manager/alarm/findAllFilter"


def _msg_code(payload: dict[str, Any]) -> str | None:
    code = payload.get("msgCode", payload.get("msg_code"))
    return code if isinstance(code, str) else None


def _msg_text(payload: dict[str, Any]) -> str | None:
    for key in ("message", "msg"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _as_list(data: Any) -> list[dict[str, Any]]:
    """Portal list endpoints return either a list or {"list": [...]}."""
    if isinstance(data, dict):
        data = data.get("list")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


class LivoltekPortalApi:
    """Async client for the Livoltek portal API."""

    def __init__(
        self,
        base_url: str,
        account: str,
        password_md5: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._account = account
        self._password_md5 = password_md5
        self._session = session
        self._token: str | None = None
        self._token_expiry_ms = 0
        self._token_lock = asyncio.Lock()

    async def login(self) -> None:
        """Log in and register the portal session."""
        try:
            async with self._session.post(
                f"{self._base_url}{_LOGIN}",
                json={"login_account": self._account, "password": self._password_md5},
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status >= 500:
                    raise LivoltekConnectionError(f"Portal login HTTP {resp.status}")
                payload = await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise LivoltekConnectionError("Portal login timed out") from err
        except aiohttp.ClientError as err:
            raise LivoltekConnectionError(f"Portal login failed: {err}") from err
        except ValueError as err:
            raise LivoltekApiError(f"Invalid JSON from portal login: {err}") from err

        if not isinstance(payload, dict) or _msg_code(payload) != _SUCCESS_CODE:
            message = _msg_text(payload) if isinstance(payload, dict) else None
            raise LivoltekAuthError(f"Portal login rejected: {message!r}")

        data = payload.get("data") or {}
        token = data.get("access_token")
        expiry = data.get("session_expiry_time")
        if not isinstance(token, str) or not token:
            raise LivoltekAuthError("Portal login response has no access token")
        self._token = token
        self._token_expiry_ms = int(expiry) if isinstance(expiry, (int, float)) else 0
        # Called without the token lock: login() runs inside ensure_token() which holds it
        await self._register_session()

    async def _register_session(self) -> None:
        try:
            async with self._session.post(
                f"{self._base_url}{_SESSION_REGISTER}",
                json={},
                headers=self._headers(),
                timeout=_TIMEOUT,
            ) as resp:
                await resp.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Portal session registration failed: %s", err)

    async def ensure_token(self) -> None:
        """Log in when there is no token or it expires within 24 h."""
        async with self._token_lock:
            now_ms = int(time.time() * 1000)
            if self._token and self._token_expiry_ms > now_ms + _TOKEN_REFRESH_BUFFER_MS:
                return
            await self.login()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "language": "en",
        }

    async def _post(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        *,
        retry_on_auth: bool = True,
    ) -> Any:
        await self.ensure_token()
        try:
            async with self._session.post(
                f"{self._base_url}{path}",
                json=body or {},
                params=params,
                headers=self._headers(),
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status == 401 and retry_on_auth:
                    self._token_expiry_ms = 0
                    return await self._post(path, body, params, retry_on_auth=False)
                if resp.status >= 400:
                    raise LivoltekApiError(f"Portal POST {path} -> HTTP {resp.status}")
                payload = await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise LivoltekConnectionError(f"Portal timeout on {path}") from err
        except aiohttp.ClientError as err:
            raise LivoltekConnectionError(f"Portal connection error on {path}: {err}") from err
        except ValueError as err:
            raise LivoltekApiError(f"Invalid JSON from portal {path}: {err}") from err

        if not isinstance(payload, dict):
            raise LivoltekApiError(f"Unexpected portal response from {path}")
        code = _msg_code(payload)
        if code != _SUCCESS_CODE:
            if code and "token" in code.lower() and retry_on_auth:
                self._token_expiry_ms = 0
                return await self._post(path, body, params, retry_on_auth=False)
            raise LivoltekApiError(f"Portal {path}: msgCode={code!r} message={_msg_text(payload)!r}")
        return payload.get("data")

    async def get_stations(self) -> list[dict[str, Any]]:
        return _as_list(await self._post(_STATIONS))

    async def get_devices(self, station_id: int) -> list[dict[str, Any]]:
        return _as_list(await self._post(_DEVICES, {"id": station_id, "seriesGroup": None}))

    async def get_energy_storage_info(self, device_id: int) -> dict[str, Any]:
        data = await self._post(_ENERGY_STORAGE_INFO, params={"id": str(device_id), "isUseChangeUnit": "true"})
        return data if isinstance(data, dict) else {}

    async def get_point_info(self, device_id: int, collector_sn: str, product_type: int) -> dict[str, Any]:
        data = await self._post(
            _POINT_INFO, {"deviceId": collector_sn, "id": device_id, "productType": product_type}
        )
        return data if isinstance(data, dict) else {}

    async def get_alarms(self, station_id: int, inverter_sn: str, days: int = 7) -> list[dict[str, Any]]:
        now = dt_util.utcnow()
        fmt = "%Y-%m-%dT%H:%M:%S.000Z"
        body = {
            "powerStationFilter": [int(station_id)],
            "level": None,
            "filterTime": [(now - timedelta(days=days)).strftime(fmt), now.strftime(fmt)],
            "alarmType": None,
            "pageSize": 50,
            "start": 1,
            "sn": inverter_sn,
            "fuzzyQueryId": True,
            "showDescribe": True,
        }
        return _as_list(await self._post(_ALARMS, body))

