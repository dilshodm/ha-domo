"""DOMO (Hududgaz) utilities integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry, DeviceEntryType, DeviceInfo

from .api import DomoClient
from .const import (
    CONF_ACCESS,
    CONF_CLIENT_SECRET,
    CONF_DEVICE_ID,
    CONF_LANGUAGE,
    CONF_REFRESH,
    DOMAIN,
    FALLBACK_LANGUAGE,
    LANGUAGES,
    PLATFORMS,
)
from .coordinator import DomoCoordinator

type DomoConfigEntry = ConfigEntry[DomoCoordinator]


def entry_language(hass: HomeAssistant, entry: ConfigEntry | None) -> str:
    """The configured language, else Home Assistant's own if DOMO supports it."""
    if entry is not None and entry.options.get(CONF_LANGUAGE) in LANGUAGES:
        return entry.options[CONF_LANGUAGE]
    return hass.config.language if hass.config.language in LANGUAGES else FALLBACK_LANGUAGE


def hub_device_info(entry: ConfigEntry) -> DeviceInfo:
    """The DOMO login itself: holds the refresh button and parents the accounts."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
        name=entry.title,
        manufacturer="DOMO",
        model="DOMO account",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://domo.uz",
    )


async def async_setup_entry(hass: HomeAssistant, entry: DomoConfigEntry) -> bool:
    """Set up DOMO from a config entry."""

    @callback
    def save_tokens(access: str, refresh: str) -> None:
        # The refresh token rotates on every refresh, so persist it right away.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_ACCESS: access, CONF_REFRESH: refresh}
        )

    language = entry_language(hass, entry)
    client = DomoClient(
        async_get_clientsession(hass),
        device_id=entry.data[CONF_DEVICE_ID],
        client_secret=entry.data[CONF_CLIENT_SECRET],
        access=entry.data[CONF_ACCESS],
        refresh=entry.data[CONF_REFRESH],
        on_tokens=save_tokens,
        lang=language,
    )
    coordinator = DomoCoordinator(hass, entry, client, language)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    # Account devices link to the hub through its registry id, so create it first.
    hub = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **hub_device_info(entry)
    )
    coordinator.hub_device_id = hub.id
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DomoConfigEntry) -> bool:
    """Unload DOMO."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: DomoConfigEntry, device: DeviceEntry
) -> bool:
    """Allow deleting a device only once its account is gone from DOMO."""
    keep = set(entry.runtime_data.data or {}) | {entry.unique_id or entry.entry_id}
    return not any(ident[0] == DOMAIN and ident[1] in keep for ident in device.identifiers)
