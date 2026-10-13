"""Fetches BC Hydro data daily at 1 am and 8 am."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BCHydroApi, BCHydroAuthError, BCHydroData, BCHydroError
from .const import DOMAIN, MAX_RETRIES, RETRY_DELAY_MINUTES, UPDATE_HOURS, UPDATE_MINUTE

_LOGGER = logging.getLogger(__name__)


class BCHydroCoordinator(DataUpdateCoordinator[BCHydroData]):
    """Scrapes on setup, then every day at 1 am and 8 am (no interval polling)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: BCHydroApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None,
        )
        self.api = api
        self._retries = 0

    async def _async_update_data(self) -> BCHydroData:
        try:
            return await self.api.async_fetch()
        except BCHydroAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BCHydroError as err:
            raise UpdateFailed(str(err)) from err

    @callback
    def start_daily_schedule(self) -> None:
        """Register the daily triggers; they are removed when the entry unloads."""
        self.config_entry.async_on_unload(
            async_track_time_change(
                self.hass,
                self._scheduled_refresh,
                hour=UPDATE_HOURS,
                minute=UPDATE_MINUTE,
                second=0,
            )
        )

    async def _scheduled_refresh(self, _now: datetime | None = None) -> None:
        await self.async_refresh()
        if self.last_update_success:
            self._retries = 0
            return
        if self._retries < MAX_RETRIES:
            self._retries += 1
            _LOGGER.warning(
                "BC Hydro refresh failed, retry %s/%s in %s min",
                self._retries,
                MAX_RETRIES,
                RETRY_DELAY_MINUTES,
            )
            self.config_entry.async_on_unload(
                async_call_later(
                    self.hass,
                    timedelta(minutes=RETRY_DELAY_MINUTES),
                    self._scheduled_refresh,
                )
            )
        else:
            self._retries = 0
