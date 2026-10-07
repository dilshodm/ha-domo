"""Update coordinator for DOMO."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
import math
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    DomoAuthError,
    DomoClient,
    DomoError,
    home_label,
    iter_accounts,
    latest_day,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DAILY_USAGE_SERVICES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PULL_COOLDOWN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class DomoAccount:
    """One utility account of one home."""

    service: str
    home_id: str
    home_label: str
    account: dict[str, Any]
    analytics: dict[str, Any] | None
    last_day: dict[str, Any] | None = field(default=None)


type DomoData = dict[str, DomoAccount]  # keyed by account id


class DomoCoordinator(DataUpdateCoordinator[DomoData]):
    """Polls HomeList, plus daily usage for metered services."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: DomoClient, language: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                hours=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.language = language
        self._last_pull: float | None = None
        self.pulling = False
        self.hub_device_id: str | None = None

    async def _async_update_data(self) -> DomoData:
        try:
            homes = await self.client.homes()
            data: DomoData = {}
            for home, service, account in iter_accounts(homes):
                data[account["id"]] = DomoAccount(
                    service=service,
                    home_id=home["id"],
                    home_label=home_label(home, self.language),
                    account=account,
                    analytics=home[service].get("analytics"),
                )
            today = dt_util.now()
            for acc in data.values():
                if acc.service in DAILY_USAGE_SERVICES:
                    acc.last_day = await self._last_day(acc, today.year, today.month)
            return data
        except DomoAuthError as err:
            raise ConfigEntryAuthFailed(f"DOMO session expired: {err}") from err
        except DomoError as err:
            raise UpdateFailed(f"Error communicating with DOMO: {err}") from err

    def pull_cooldown_left(self) -> int:
        """Seconds until the next manual refresh is allowed."""
        if self._last_pull is None:
            return 0
        return max(0, math.ceil(self._last_pull + PULL_COOLDOWN - time.monotonic()))

    async def async_pull(self) -> None:
        """Make DOMO re-sync every account with its provider, then fetch the result."""
        self.pulling = True
        try:
            for acc in list((self.data or {}).values()):
                try:
                    await self.client.refresh_account(acc.service, acc.account["id"])
                except DomoAuthError:
                    break  # the refresh below raises the reauth
                except DomoError as err:
                    # Some services can't be re-synced; the regular fetch still covers them.
                    _LOGGER.debug(
                        "DOMO refresh of %s %s failed: %s", acc.service, acc.account["id"], err
                    )
            await self.async_refresh()
            if self.last_update_success:
                self._last_pull = time.monotonic()
        finally:
            self.pulling = False

    async def _last_day(self, acc: DomoAccount, year: int, month: int) -> dict[str, Any] | None:
        usage = await self.client.daily_usage(acc.service, acc.account["id"], year, month)
        day = latest_day(usage)
        if day is None:
            # Early in the month the current month can still be empty.
            prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
            day = latest_day(
                await self.client.daily_usage(acc.service, acc.account["id"], prev_year, prev_month)
            )
        return day
