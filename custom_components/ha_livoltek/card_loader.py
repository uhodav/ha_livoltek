"""Load the integration's Lovelace cards so they are available right after Home Assistant starts.

The card is copied to config/www/<domain>/ (served under /local from the first seconds of startup) and registered
as a dashboard resource. Otherwise the card only appears once the integration has loaded, and a dashboard opened
during startup shows "Custom element doesn't exist". If dashboard resources are in YAML mode or /local is not
served yet (no www folder at startup), the card is loaded via add_extra_js_url as before.
"""
import logging
import shutil
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _copy_changed(src_dir: Path, dst_dir: Path, scripts: list[str]) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for script in scripts:
        src, dst = src_dir / script, dst_dir / script
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            shutil.copyfile(src, dst)


def _lovelace_resources(hass: HomeAssistant):
    """Dashboard resource collection (storage mode only), otherwise None. hass.data layout differs between HA versions."""
    data = hass.data.get("lovelace")
    if data is None:
        return None
    if isinstance(data, dict):
        resources, mode = data.get("resources"), data.get("resource_mode") or data.get("mode")
    else:
        resources, mode = getattr(data, "resources", None), getattr(data, "resource_mode", None)
    if mode == "yaml" or not hasattr(resources, "async_create_item"):
        return None
    return resources


async def _async_ensure_resource(resources, url: str) -> bool:
    """Create the resource or update the version of an existing one. True if it was just created."""
    # async_get_info loads the collection from storage (all HA versions)
    await resources.async_get_info()
    path = url.split("?")[0]
    for item in resources.async_items():
        if item["url"].split("?")[0] == path:
            if item["url"] != url:
                await resources.async_update_item(item["id"], {"res_type": "module", "url": url})
            return False
    await resources.async_create_item({"res_type": "module", "url": url})
    return True


async def async_register_cards(
    hass: HomeAssistant, domain: str, src_dir: Path, scripts: list[str], static_url: str, version: str
) -> None:
    """Load cards from src_dir (already served at static_url) via /local and a dashboard resource."""
    local_served = Path(hass.config.path("www")).is_dir()
    use_fallback = not local_served
    try:
        await hass.async_add_executor_job(_copy_changed, src_dir, Path(hass.config.path("www", domain)), scripts)
        resources = _lovelace_resources(hass)
        if resources is None:
            use_fallback = True
        else:
            for script in scripts:
                # Open pages pick up a freshly created resource only after reload, so also use extra_js this run
                if await _async_ensure_resource(resources, f"/local/{domain}/{script}?v={version}"):
                    use_fallback = True
    except Exception:  # noqa: BLE001 - the card must not break integration setup
        _LOGGER.warning("%s: could not register card as a dashboard resource, using extra_js", domain, exc_info=True)
        use_fallback = True

    if use_fallback:
        for script in scripts:
            add_extra_js_url(hass, f"{static_url}/{script}?v={version}")
