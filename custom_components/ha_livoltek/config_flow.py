"""Config flow for Livoltek integration."""
import hashlib
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ALL_GROUPS,
    CONF_ACCOUNT,
    CONF_AUTH_TOKEN,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_RESERVE_SOC,
    CONF_DEVICE_ID,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_SN,
    CONF_ENABLED_GROUPS,
    CONF_KEY,
    CONF_PASSWORD,
    CONF_SECUID,
    CONF_SERVER_TYPE,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    CONF_USE_PORTAL,
    CONF_WORKMODE,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_RESERVE_SOC,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    GROUP_LABELS,
    GROUP_LABELS_UK,
    MIN_UPDATE_INTERVAL,
    PORTAL_SERVERS,
    SERVER_EUROPEAN,
    SERVER_INTERNATIONAL,
    SERVERS,
)
from .api import LivoltekApi, LivoltekApiError, LivoltekAuthError
from .portal import LivoltekPortalApi

_LOGGER = logging.getLogger(__name__)


def _get_group_labels(hass) -> dict[str, str]:
    """Return group labels in HA configured language."""
    lang = hass.config.language if hass else "en"
    if lang and lang.startswith("uk"):
        return GROUP_LABELS_UK
    return GROUP_LABELS


async def _check_portal(hass, server_type: str, account: str, password_md5: str) -> str | None:
    """Try to log in to the web portal; return an error key or None."""
    portal = LivoltekPortalApi(PORTAL_SERVERS[server_type], account, password_md5, async_get_clientsession(hass))
    try:
        await portal.login()
    except LivoltekAuthError:
        return "portal_auth"
    except LivoltekApiError:
        return "portal_connect"
    return None


def _control_schema(account_default: dict, use_portal: bool) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_ACCOUNT, description=account_default): str,
            vol.Optional(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_USE_PORTAL, default=use_portal): bool,
        }
    )


class LivoltekConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Livoltek."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._server_type: str | None = None
        self._secuid: str | None = None
        self._key: str | None = None
        self._token: str | None = None  # user-provided token (userToken query param)
        self._auth_token: str | None = None  # JWT from login (Authorization header)
        self._sites: list[dict] = []
        self._site_id: str | None = None
        self._site_name: str | None = None
        self._devices: list[dict] = []
        self._account: str | None = None
        self._password_md5: str | None = None
        self._enabled_groups: list[str] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Step 1: Server type and API credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._server_type = user_input[CONF_SERVER_TYPE]
            self._secuid = user_input[CONF_SECUID]
            self._key = user_input[CONF_KEY]
            self._token = user_input[CONF_TOKEN]

            base_url = SERVERS[self._server_type]
            session = async_get_clientsession(self.hass)
            api = LivoltekApi(base_url, self._secuid, self._key, self._token, session=session, server_type=self._server_type)
            try:
                self._auth_token = await api.login()
                return await self.async_step_site()
            except LivoltekAuthError as err:
                _LOGGER.error("Livoltek auth error: %s", err)
                errors["base"] = "invalid_auth"
            except LivoltekApiError as err:
                _LOGGER.error("Livoltek API error: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Livoltek login")
                errors["base"] = "unknown"
            finally:
                await api.close()

        server_options = [
            selector.SelectOptionDict(value=SERVER_INTERNATIONAL, label="International server"),
            selector.SelectOptionDict(value=SERVER_EUROPEAN, label="European server"),
        ]

        # Preserve previously entered values on error
        defaults = {
            CONF_SERVER_TYPE: (user_input or {}).get(CONF_SERVER_TYPE, self._server_type or SERVER_EUROPEAN),
            CONF_SECUID: (user_input or {}).get(CONF_SECUID, self._secuid or ""),
            CONF_KEY: (user_input or {}).get(CONF_KEY, self._key or ""),
            CONF_TOKEN: (user_input or {}).get(CONF_TOKEN, self._token or ""),
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERVER_TYPE, default=defaults[CONF_SERVER_TYPE]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=server_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(CONF_SECUID, default=defaults[CONF_SECUID]): str,
                    vol.Required(CONF_KEY, default=defaults[CONF_KEY]): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required(CONF_TOKEN, default=defaults[CONF_TOKEN]): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_site(self, user_input: dict[str, Any] | None = None):
        """Step 2: Select a site."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_site_id = user_input[CONF_SITE_ID]
            for site in self._sites:
                if str(site.get("powerStationId")) == selected_site_id:
                    self._site_id = selected_site_id
                    self._site_name = site.get("powerStationName", selected_site_id)
                    break
            if self._site_id:
                return await self.async_step_device()
            errors["base"] = "invalid_site"

        # Fetch sites list
        if not self._sites:
            base_url = SERVERS[self._server_type]
            session = async_get_clientsession(self.hass)
            api = LivoltekApi(base_url, self._secuid, self._key, self._token, self._auth_token, session=session, server_type=self._server_type)
            try:
                data = await api.get_sites()
                self._sites = data.get("list", []) if data else []
            except LivoltekApiError as err:
                _LOGGER.error("Failed to fetch sites: %s", err)
                errors["base"] = "cannot_connect"
            finally:
                await api.close()

        if not self._sites and "base" not in errors:
            errors["base"] = "no_sites"

        site_options = [
            selector.SelectOptionDict(
                value=str(site["powerStationId"]),
                label=f"{site.get('powerStationName', 'Unknown')} ({site.get('powerStationId')})",
            )
            for site in self._sites
        ]

        return self.async_show_form(
            step_id="site",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SITE_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=site_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None):
        """Step 3: Select a device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_device_id = user_input[CONF_DEVICE_SN]
            update_interval = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

            for device in self._devices:
                if str(device.get("inverterSn")) == selected_device_id:
                    device_id = device.get("id")
                    device_model = device.get("deviceModel", "inverter")
                    product_type = device.get("productType", "")

                    await self.async_set_unique_id(
                        f"livoltek_{self._site_id}_{selected_device_id}"
                    )
                    self._abort_if_unique_id_configured()

                    self._selected_device_id = selected_device_id
                    self._device_id = str(device_id)
                    self._device_model = device_model
                    self._product_type = product_type
                    self._update_interval = update_interval
                    self._device_workmode = device.get("workmode", "")

                    return await self.async_step_groups()

            errors["base"] = "invalid_device"

        # Fetch devices list
        if not self._devices:
            base_url = SERVERS[self._server_type]
            session = async_get_clientsession(self.hass)
            api = LivoltekApi(base_url, self._secuid, self._key, self._token, self._auth_token, session=session, server_type=self._server_type)
            try:
                data = await api.get_devices(self._site_id)
                self._devices = data.get("list", []) if data else []
            except LivoltekApiError as err:
                _LOGGER.error("Failed to fetch devices: %s", err)
                errors["base"] = "cannot_connect"
            finally:
                await api.close()

        if not self._devices and "base" not in errors:
            errors["base"] = "no_devices"

        device_options = [
            selector.SelectOptionDict(
                value=str(device["inverterSn"]),
                label=f"{device.get('inverterSn', 'Unknown')} ({device.get('productType', '')}, {device.get('deviceModel', '')})",
            )
            for device in self._devices
        ]

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_SN): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=device_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_UPDATE_INTERVAL, max=60)),
                }
            ),
            errors=errors,
        )

    async def async_step_groups(self, user_input: dict[str, Any] | None = None):
        """Step 4: Select endpoint groups."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = user_input.get(CONF_ENABLED_GROUPS, [])
            if not selected:
                errors["base"] = "no_groups_selected"
            else:
                self._enabled_groups = selected
                return await self.async_step_control()

        labels = _get_group_labels(self.hass)
        group_options = [
            selector.SelectOptionDict(value=g, label=labels.get(g, g))
            for g in ALL_GROUPS
        ]

        return self.async_show_form(
            step_id="groups",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLED_GROUPS, default=list(ALL_GROUPS)
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=group_options,
                            mode=selector.SelectSelectorMode.LIST,
                            multiple=True,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_control(self, user_input: dict[str, Any] | None = None):
        """Step 5: Optional BESS control credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            account = user_input.get(CONF_ACCOUNT, "").strip()
            password = user_input.get(CONF_PASSWORD, "").strip()
            use_portal = bool(user_input.get(CONF_USE_PORTAL))
            if account and password:
                self._account = account
                self._password_md5 = hashlib.md5(password.encode()).hexdigest()
            if use_portal:
                if not self._account:
                    errors["base"] = "portal_needs_account"
                elif error := await _check_portal(self.hass, self._server_type, self._account, self._password_md5):
                    errors["base"] = error

        if user_input is not None and not errors:
            title = f"{self._site_name} - {self._selected_device_id}"

            return self.async_create_entry(
                title=title,
                data={
                    CONF_SERVER_TYPE: self._server_type,
                    CONF_SECUID: self._secuid,
                    CONF_KEY: self._key,
                    CONF_TOKEN: self._token,
                    CONF_AUTH_TOKEN: self._auth_token,
                    CONF_SITE_ID: self._site_id,
                    CONF_SITE_NAME: self._site_name,
                    CONF_DEVICE_ID: self._device_id,
                    CONF_DEVICE_SN: self._selected_device_id,
                    CONF_DEVICE_MODEL: self._device_model,
                    CONF_UPDATE_INTERVAL: self._update_interval,
                    "product_type": self._product_type,
                    CONF_WORKMODE: self._device_workmode,
                    CONF_ENABLED_GROUPS: self._enabled_groups,
                    CONF_ACCOUNT: self._account or "",
                    CONF_PASSWORD: self._password_md5 or "",
                    CONF_USE_PORTAL: use_portal,
                },
            )

        return self.async_show_form(
            step_id="control",
            data_schema=_control_schema({}, False),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        """Start reauthentication when the stored credentials stop working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        """Ask for new API credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            secuid = user_input[CONF_SECUID].strip()
            key = user_input[CONF_KEY].strip()
            token = user_input[CONF_TOKEN].strip()
            server_type = entry.data[CONF_SERVER_TYPE]
            session = async_get_clientsession(self.hass)
            api = LivoltekApi(SERVERS[server_type], secuid, key, token, session=session, server_type=server_type)
            try:
                auth_token = await api.login()
            except LivoltekAuthError:
                errors["base"] = "invalid_auth"
            except LivoltekApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Livoltek login")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        **entry.data,
                        CONF_SECUID: secuid,
                        CONF_KEY: key,
                        CONF_TOKEN: token,
                        CONF_AUTH_TOKEN: auth_token,
                    },
                )
            finally:
                await api.close()

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SECUID, default=entry.data.get(CONF_SECUID, "")): str,
                    vol.Required(CONF_KEY): str,
                    vol.Required(CONF_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return LivoltekOptionsFlow(config_entry)


class LivoltekOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Livoltek — multi-step with pre-filled values."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._new_data: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Step 1/3: API credentials (pre-filled)."""
        errors: dict[str, str] = {}
        cur = self._config_entry.data

        if user_input is not None:
            server_type = user_input[CONF_SERVER_TYPE]
            secuid = user_input[CONF_SECUID].strip()
            key = user_input[CONF_KEY].strip()
            token = user_input[CONF_TOKEN].strip()

            # Validate credentials by attempting login
            base_url = SERVERS[server_type]
            session = async_get_clientsession(self.hass)
            api = LivoltekApi(base_url, secuid, key, token, session=session, server_type=server_type)
            try:
                auth_token = await api.login()
                self._new_data = {
                    **dict(cur),
                    CONF_SERVER_TYPE: server_type,
                    CONF_SECUID: secuid,
                    CONF_KEY: key,
                    CONF_TOKEN: token,
                    CONF_AUTH_TOKEN: auth_token,
                }
                return await self.async_step_groups()
            except LivoltekAuthError:
                errors["base"] = "invalid_auth"
            except LivoltekApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Livoltek login")
                errors["base"] = "unknown"
            finally:
                await api.close()

        server_options = [
            selector.SelectOptionDict(value=SERVER_INTERNATIONAL, label="International server"),
            selector.SelectOptionDict(value=SERVER_EUROPEAN, label="European server"),
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SERVER_TYPE,
                        default=cur.get(CONF_SERVER_TYPE, SERVER_EUROPEAN),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=server_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_SECUID,
                        default=cur.get(CONF_SECUID, ""),
                    ): str,
                    vol.Required(
                        CONF_KEY,
                        default=cur.get(CONF_KEY, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required(
                        CONF_TOKEN,
                        default=cur.get(CONF_TOKEN, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_groups(self, user_input: dict[str, Any] | None = None):
        """Step 2/3: Update interval and data groups."""
        errors: dict[str, str] = {}
        cur = self._config_entry.data

        if user_input is not None:
            selected = user_input.get(CONF_ENABLED_GROUPS, [])
            if not selected:
                errors["base"] = "no_groups_selected"
            else:
                interval = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                if interval < MIN_UPDATE_INTERVAL:
                    interval = MIN_UPDATE_INTERVAL
                self._new_data[CONF_UPDATE_INTERVAL] = interval
                self._new_data[CONF_ENABLED_GROUPS] = selected
                self._new_data[CONF_BATTERY_CAPACITY] = user_input.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)
                self._new_data[CONF_BATTERY_RESERVE_SOC] = user_input.get(CONF_BATTERY_RESERVE_SOC, DEFAULT_BATTERY_RESERVE_SOC)
                return await self.async_step_control()

        current_interval = cur.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        current_groups = cur.get(CONF_ENABLED_GROUPS, ALL_GROUPS)

        labels = _get_group_labels(self.hass)
        group_options = [
            selector.SelectOptionDict(value=g, label=labels.get(g, g))
            for g in ALL_GROUPS
        ]

        return self.async_show_form(
            step_id="groups",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_UPDATE_INTERVAL, max=60)),
                    vol.Required(
                        CONF_ENABLED_GROUPS, default=list(current_groups)
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=group_options,
                            mode=selector.SelectSelectorMode.LIST,
                            multiple=True,
                        )
                    ),
                    vol.Required(
                        CONF_BATTERY_CAPACITY,
                        default=cur.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=1000, step=0.01, unit_of_measurement="kWh",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_BATTERY_RESERVE_SOC,
                        default=cur.get(CONF_BATTERY_RESERVE_SOC, DEFAULT_BATTERY_RESERVE_SOC),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=90, step=1, unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_control(self, user_input: dict[str, Any] | None = None):
        """Step 3/3: BESS control credentials (optional)."""
        cur = self._config_entry.data
        errors: dict[str, str] = {}

        if user_input is not None:
            account = user_input.get(CONF_ACCOUNT, "").strip()
            password = user_input.get(CONF_PASSWORD, "").strip()
            use_portal = bool(user_input.get(CONF_USE_PORTAL))

            if account:
                self._new_data[CONF_ACCOUNT] = account
            if password:
                self._new_data[CONF_PASSWORD] = hashlib.md5(
                    password.encode()
                ).hexdigest()
            self._new_data[CONF_USE_PORTAL] = use_portal

            if use_portal:
                if not (self._new_data.get(CONF_ACCOUNT) and self._new_data.get(CONF_PASSWORD)):
                    errors["base"] = "portal_needs_account"
                elif error := await _check_portal(
                    self.hass,
                    self._new_data[CONF_SERVER_TYPE],
                    self._new_data[CONF_ACCOUNT],
                    self._new_data[CONF_PASSWORD],
                ):
                    errors["base"] = error

        if user_input is not None and not errors:
            # Save all changes to entry.data and reload
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=self._new_data
            )

            # Reload the entire integration to apply changes
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="control",
            data_schema=_control_schema(
                {"suggested_value": cur.get(CONF_ACCOUNT, "")}, bool(cur.get(CONF_USE_PORTAL))
            ),
            errors=errors,
        )
