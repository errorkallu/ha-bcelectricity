"""BC Hydro integration: daily electricity use and cost scraped from app.bchydro.com."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .api import BCHydroApi
from .coordinator import BCHydroCoordinator

PLATFORMS = [Platform.SENSOR]

type BCHydroConfigEntry = ConfigEntry[BCHydroCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: BCHydroConfigEntry) -> bool:
    """Set up BC Hydro from a config entry."""
    api = BCHydroApi(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = BCHydroCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    coordinator.start_daily_schedule()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BCHydroConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
