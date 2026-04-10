"""API client for Livoltek ESS API."""
import json as json_mod
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class LivoltekApiError(Exception):
    """Base exception for Livoltek API errors."""


class LivoltekAuthError(LivoltekApiError):
    """Authentication error."""


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
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._secuid = secuid
        self._key = key
        self._user_token = user_token
        self._auth_token = auth_token
        self._session: aiohttp.ClientSession | None = None

    @property
    def auth_token(self) -> str | None:
        """Return the current JWT auth token (from login)."""
        return self._auth_token

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
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
                ssl=False,
            ) as resp:
                raw = await resp.text()
                data = json_mod.loads(raw)
                if str(data.get("code")) != "200":
                    raise LivoltekAuthError(
                        f"Login failed: code={data.get('code')} message={data.get('message')} body={raw[:500]}"
                    )
                inner = data.get("data")

                if isinstance(inner, dict):
                    token = inner.get("data")
                elif isinstance(inner, str):
                    token = inner
                else:
                    token = None
                if not token:
                    raise LivoltekAuthError(
                        f"No token in login response: data_type={type(inner).__name__} data={str(inner)[:300]} full_body={raw[:500]}"
                    )
                self._auth_token = token
                return token
        except LivoltekApiError:
            raise
        except aiohttp.ClientError as err:
            raise LivoltekApiError(f"Connection error during login: {err}") from err
        except Exception as err:
            raise LivoltekApiError(f"Unexpected error during login: {err}") from err

    async def _request(self, method: str, path: str, params: dict | None = None, json_body: dict | None = None) -> Any:
        """Make an authenticated API request."""
        if not self._auth_token:
            await self.login()

        url = f"{self._base_url}{path}"
        # userToken = user-provided token, Authorization header = JWT from login
        query_params = {"userToken": self._user_token, "userType": "0"}
        if params:
            query_params.update(params)

        headers = {"Authorization": self._auth_token}

        session = await self._get_session()
        try:
            async with session.request(
                method,
                url,
                params=query_params,
                json=json_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
                ssl=False,
            ) as resp:
                raw = await resp.text()
                data = json_mod.loads(raw)

                if str(data.get("code")) == "401":
                    # Auth token expired, re-login and retry
                    await self.login()
                    headers["Authorization"] = self._auth_token
                    async with session.request(
                        method,
                        url,
                        params=query_params,
                        json=json_body,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                        ssl=False,
                    ) as retry_resp:
                        raw_retry = await retry_resp.text()
                        data = json_mod.loads(raw_retry)

                if str(data.get("code")) != "200":
                    raise LivoltekApiError(
                        f"API error {data.get('code')}: {data.get('message', 'Unknown')}"
                    )
                return data.get("data")
        except LivoltekApiError:
            raise
        except aiohttp.ClientError as err:
            raise LivoltekApiError(f"Connection error: {err}") from err

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
            "epsOutputenergy", "dgtotalEnergy",
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
