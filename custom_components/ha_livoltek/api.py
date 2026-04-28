"""API client for Livoltek ESS API."""
import asyncio
import base64
import binascii
import json as json_mod
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from .const import (
    SERVER_INTERNATIONAL,
    TOKEN_REFRESH_BUFFER,
)

_LOGGER = logging.getLogger(__name__)

_SUCCESS_APP_CODE = "operate.success"
_TRANSPORT_OK_MARKERS = frozenset({"200", "SUCCESS"})
_AUTH_FAIL_CODES = frozenset({"login.invalid", "token.invalid", "user.token.invalid"})
_STALE_TOKEN_CODES = frozenset({"token.expiried", "token.expired"})


class LivoltekApiError(Exception):
    """Base exception for Livoltek API errors."""


class LivoltekAuthError(LivoltekApiError):
    """Authentication error."""


class LivoltekConnectionError(LivoltekApiError):
    """Connection/transport error."""


def _msg_text(payload: dict[str, Any]) -> str | None:
    """Extract human-readable message from payload."""
    text = payload.get("message") or payload.get("msg")
    return text if isinstance(text, str) else None


def _normalise_response(payload: Any) -> dict[str, Any]:
    """Collapse all three Livoltek response shapes into one canonical form.

    Shape 1 (login): {"code": "200", "data": {"msgCode": "operate.success", "data": "<jwt>"}}
    Shape 2 (data):  {"code": "200", "data": {...actual data...}}
    Shape 3 (flat):  {"msgCode": "operate.success", "data": {...}}
    """
    if not isinstance(payload, dict):
        return {"msgCode": None, "message": None, "data": payload}

    if "msgCode" in payload:
        return payload

    code = str(payload.get("code") or "")
    msg = (_msg_text(payload) or "").upper()
    transport_ok = code in _TRANSPORT_OK_MARKERS or msg in _TRANSPORT_OK_MARKERS

    if not transport_ok:
        return {
            "msgCode": code,
            "message": _msg_text(payload),
            "data": payload.get("data"),
        }

    inner = payload.get("data")

    if isinstance(inner, dict) and "msgCode" in inner:
        return inner

    return {
        "msgCode": _SUCCESS_APP_CODE,
        "message": _msg_text(payload),
        "data": inner,
    }


def _is_success(payload: dict[str, Any]) -> bool:
    """Check if normalized response indicates success."""
    return payload.get("msgCode") == _SUCCESS_APP_CODE

def _decode_token_expiry(token: str) -> int | None:
    """Decode JWT exp claim without signature verification."""
    try:
        payload_part = token.split(".")[1]
        padded = payload_part + "=" * (4 - len(payload_part) % 4)
        payload = json_mod.loads(base64.b64decode(padded))
        return int(payload["exp"])
    except (IndexError, KeyError, ValueError, binascii.Error, Exception):
        _LOGGER.debug("Could not decode JWT expiry, will use reactive refresh")
        return None


class LivoltekApi:
    """Livoltek API client.

    Two tokens are used:
    - user_token: provided by the user manually, sent as `userToken` query parameter
    - auth_token: JWT obtained from /hess/api/login, sent as `Authorization` header
    """

    def __init__(
        self,
        base_url: str,
        secuid: str,
        key: str,
        user_token: str,
        auth_token: str | None = None,
        session: aiohttp.ClientSession | None = None,
        server_type: str = SERVER_INTERNATIONAL,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._secuid = secuid
        self._key = key
        self._user_token = user_token
        self._auth_token = auth_token
        self._token_expiry: int | None = None
        self._token_lock = asyncio.Lock()
        self._session = session  # HA shared session or None
        self._owns_session = session is None
        self._server_type = server_type

    @property
    def auth_token(self) -> str | None:
        """Return the current JWT auth token (from login)."""
        return self._auth_token

    @property
    def token_expiry(self) -> int | None:
        """Return the token expiry timestamp."""
        return self._token_expiry

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session
        if self._owns_session:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the session only if we own it."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def login(self) -> str:
        """Login and obtain a JWT auth token."""
        url = f"{self._base_url}/hess/api/login"
        # The API key from Livoltek portal ends with \r\n (CRLF).
        # User may paste it as literal text "\r\n" or with actual CR/LF chars.
        # Normalize: remove all trailing whitespace, literal \r\n text, then append real CRLF.
        key = self._key.strip()
        # Remove literal text \r\n / \n at end (the characters backslash-r-backslash-n)
        while key.endswith("\\r\\n") or key.endswith("\\n"):
            if key.endswith("\\r\\n"):
                key = key[:-4]
            elif key.endswith("\\n"):
                key = key[:-2]
        key = key.strip()
        key = key + "\r\n"
        payload = {"secuid": self._secuid, "key": key}

        session = await self._get_session()
        try:
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                raw = await resp.text()
                raw_data = json_mod.loads(raw)
        except LivoltekApiError:
            raise
        except aiohttp.ClientError as err:
            raise LivoltekApiError(f"Connection error during login: {err}") from err
        except Exception as err:
            raise LivoltekApiError(f"Unexpected error during login: {err}") from err

        if not isinstance(raw_data, dict):
            raise LivoltekAuthError(f"Unexpected login response: {str(raw_data)[:500]}")

        body = _normalise_response(raw_data)

        if not _is_success(body):
            msg_code = body.get("msgCode")
            msg = _msg_text(body)
            raise LivoltekAuthError(
                f"Login failed: msgCode={msg_code!r} message={msg!r}"
            )

        token = body.get("data")
        if not token or not isinstance(token, str):
            raise LivoltekAuthError(
                f"No token in login response: body={str(body)[:500]}"
            )

        self._auth_token = token
        self._token_expiry = _decode_token_expiry(token)
        if self._token_expiry:
            _LOGGER.debug(
                "Login successful, token expires at %s",
                datetime.fromtimestamp(self._token_expiry, tz=timezone.utc).isoformat(),
            )
        else:
            _LOGGER.debug("Login successful, token expiry unknown")
        return token

    async def ensure_token(self) -> None:
        """Proactively refresh token if it's about to expire."""
        async with self._token_lock:
            now = int(time.time())
            buffer = int(TOKEN_REFRESH_BUFFER.total_seconds())

            if (
                self._auth_token
                and self._token_expiry
                and self._token_expiry > now + buffer
            ):
                return  # Token still valid

            if self._auth_token and self._token_expiry is None:
                # Can't determine expiry — keep current token
                # Will fall back to reactive refresh on 401
                return

            _LOGGER.debug("Token expired or about to expire, refreshing...")
            await self.login()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
        *,
        retry_on_auth: bool = True,
    ) -> Any:
        """Make an authenticated API request with 3-shape response normalization."""
        await self.ensure_token()

        if not self._auth_token:
            await self.login()

        url = f"{self._base_url}{path}"

        query_params = {"userToken": self._user_token, "userType": "0"}
        if params:
            query_params.update(params)

        headers = {"Authorization": self._auth_token}

        session = await self._get_session()
        try:
            async with session.request(
                method,
                url,
                params=query_params if query_params else None,
                json=json_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 401 and retry_on_auth:
                    _LOGGER.debug("Got 401 from %s, refreshing token", url)
                    self._token_expiry = 0
                    await self.ensure_token()
                    return await self._request(
                        method, path, params, json_body,
                        retry_on_auth=False,
                    )
                if resp.status >= 400:
                    body_text = await resp.text()
                    raise LivoltekApiError(
                        f"{method} {url} -> HTTP {resp.status}: {body_text[:500]}"
                    )
                raw = await resp.text()
                data = json_mod.loads(raw)
        except LivoltekApiError:
            raise
        except asyncio.TimeoutError as err:
            raise LivoltekConnectionError(f"Timeout on {method} {url}") from err
        except aiohttp.ClientError as err:
            raise LivoltekConnectionError(f"Connection error: {err}") from err

        if not isinstance(data, dict):
            raise LivoltekApiError(f"Unexpected response from {url}: {str(data)[:300]}")

        body = _normalise_response(data)

        if not _is_success(body):
            msg_code = body.get("msgCode", "")
            msg = _msg_text(body) or ""

            # Check for stale token
            looks_stale = (
                msg_code in _STALE_TOKEN_CODES
                or msg.lower() == "please login"
                or str(data.get("code")) in ("401", "403")
            )
            if looks_stale and retry_on_auth:
                _LOGGER.debug("Stale token from %s, refreshing and retrying", url)
                self._token_expiry = 0
                await self.ensure_token()
                return await self._request(
                    method, path, params, json_body,
                    retry_on_auth=False,
                )

            # Check for auth failure
            if msg_code in _AUTH_FAIL_CODES:
                raise LivoltekAuthError(f"{url}: msgCode={msg_code!r} message={msg!r}")

            raise LivoltekApiError(
                f"API error from {url}: msgCode={msg_code!r} message={msg!r}"
            )

        return body.get("data")

    async def get_sites(self, page: int = 1, size: int = 100) -> dict:
        """Get list of sites."""
        return await self._request(
            "GET",
            "/hess/api/userSites/list",
            params={"page": str(page), "size": str(size)},
        )

    async def get_site_details(self, site_id: str) -> dict:
        """Get site details."""
        return await self._request("GET", f"/hess/api/site/{site_id}/details")

    async def get_site_overview(self, site_id: str) -> dict:
        """Get site generation overview."""
        return await self._request("GET", f"/hess/api/site/{site_id}/overview")

    async def get_current_power_flow(self, site_id: str) -> dict:
        """Get current power flow for a site."""
        return await self._request("GET", f"/hess/api/site/{site_id}/curPowerflow")

    async def get_devices(self, site_id: str, page: int = 1, size: int = 100) -> dict:
        """Get list of devices for a site."""
        return await self._request(
            "GET",
            f"/hess/api/device/{site_id}/list",
            params={"page": str(page), "size": str(size)},
        )

    async def get_device_details(self, site_id: str, serial_number: str) -> dict:
        """Get device details."""
        return await self._request(
            "GET", f"/hess/api/device/{site_id}/{serial_number}/details"
        )

    async def get_device_real_electricity(self, device_id: str) -> dict:
        """Get device lifetime generation/consumption."""
        return await self._request(
            "GET", f"/hess/api/device/{device_id}/realElectricity"
        )

    async def get_storage_info(self, site_id: str) -> dict:
        """Get storage (ESS/battery) information for a site."""
        return await self._request("GET", f"/hess/api/site/{site_id}/ESS")

    async def get_social_contribution(self, site_id: str) -> dict:
        """Get site social contribution (CO2, trees, coal)."""
        return await self._request("GET", f"/hess/api/site/{site_id}/socialContr")

    async def get_device_alarms(
        self, site_id: str, serial_number: str, days: int = 7, page: int = 1, size: int = 20
    ) -> dict:
        """Get device alarms for the last N days."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)
        return await self._request(
            "GET",
            f"/hess/api/device/{site_id}/{serial_number}/alarm",
            params={
                "startTime": start.strftime("%Y-%m-%d"),
                "endTime": now.strftime("%Y-%m-%d"),
                "page": str(page),
                "size": str(size),
            },
        )

    async def get_device_realtime(self, site_id: str, serial_number: str) -> dict:
        """Get device realtime technical parameters (MPPT, AC, battery, EPS)."""
        data = await self._request(
            "GET", f"/hess/api/device/{site_id}/{serial_number}/realTime"
        )
        # Response is a historyMap: {timestamp_str: [{fields...}]}
        # Extract the latest data point
        if not data or not isinstance(data, dict):
            return {}
        latest_ts = None
        latest_entry = {}
        for ts_key, entries in data.items():
            if not isinstance(entries, list) or not entries:
                continue
            try:
                ts_val = int(ts_key)
            except (ValueError, TypeError):
                continue
            if latest_ts is None or ts_val > latest_ts:
                latest_ts = ts_val
                latest_entry = entries[0] if entries else {}
        if latest_ts is not None:
            latest_entry["timestamp"] = latest_ts
        return latest_entry

    async def get_daily_energy_report(self, device_id: str) -> dict:
        """Get daily energy report for a device (POST, rate-limited 1x/hour).

        Returns summed daily totals for each metric.
        """
        now = datetime.now(timezone.utc)
        start_str = now.strftime("%Y-%m-%d 00:00:00")
        end_str = now.strftime("%Y-%m-%d 23:59:59")
        data = await self._request(
            "POST",
            "/hess/api/sample/energy",
            json_body={
                "id": device_id,
                "startTime": start_str,
                "endTime": end_str,
            },
        )
        if not data or not isinstance(data, dict):
            return {}
        # Sum the values for each metric
        result = {}
        for metric in (
            "pvYield", "loadConsumption", "energyImportFromGrid",
            "energyExportToGrid", "dischargeCapacity", "chargingCapacity",
            "epsOutputenergy", "dgtotalEnergy", "evConsumption",
        ):
            entries = data.get(metric)
            if not entries or not isinstance(entries, list):
                result[metric] = None
                continue
            total = 0.0
            for entry in entries:
                val = entry.get("value")
                if val is not None:
                    try:
                        total += float(val)
                    except (ValueError, TypeError):
                        pass
            result[metric] = round(total, 3)
        return result

    # ── BESS Management API ──────────────────────────────────────────

    async def get_device_description(self, sn: str) -> dict:
        """Get device self-description (supported commands and work modes)."""
        return await self._request(
            "GET", f"/hess/api/cmc/device/{sn}/description"
        )

    async def remote_start_or_stop(
        self, account: str, pwd_md5: str, sn: str, control_type: int
    ) -> dict:
        """Remote start/stop/restart inverter or BMS.

        control_type: 0=Inverter Start, 1=Inverter Stop, 2=Inverter Restart,
                      3=BMS Restart, 4=Emergency Charging
        """
        return await self._request(
            "POST",
            "/hess/api/cmc/device/remoteStartOrStop",
            json_body={
                "account": account,
                "pwd": pwd_md5,
                "sn": sn,
                "controlType": control_type,
            },
        )

    async def set_work_mode(
        self,
        account: str,
        pwd_md5: str,
        sn: str,
        work_mode: int,
        schedule_list: list[dict] | None = None,
    ) -> dict:
        """Set inverter working mode.

        work_mode values depend on product type (see device_description.workmode).
        schedule_list: optional list of charge/discharge schedule entries for
                       User Defined Mode.  Each entry:
                         {"chargeType": 1|2, "startHour": int, "startMin": int,
                          "endHour": int, "endMin": int,
                          "chargingDays": [0..6]}  # days optional (modbus >= 0.48)
        """
        body: dict = {
            "account": account,
            "pwd": pwd_md5,
            "sn": sn,
            "workMode": work_mode,
        }
        if schedule_list is not None:
            body["scheduleList"] = schedule_list
        return await self._request(
            "POST",
            "/hess/api/cmc/device/workModeSet",
            json_body=body,
        )

    # ── New endpoints from API v1.4.6 documentation ──────────────────

    async def get_site_installer(self, site_id: str) -> dict:
        """Get site installer information."""
        return await self._request("GET", f"/hess/api/site/{site_id}/siteInstaller")

    async def get_site_owner(self, site_id: str) -> dict:
        """Get site owner (end user) information."""
        return await self._request("GET", f"/hess/api/site/{site_id}/siteOwner")

    async def get_device_basic_data(self, sn: str) -> dict:
        """Get device basic data (registration, daily counters, status)."""
        return await self._request(
            "GET", "/hess/api/device/basicData", params={"sn": sn}
        )
