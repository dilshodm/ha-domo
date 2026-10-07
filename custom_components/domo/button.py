"""Button to pull fresh data from DOMO on demand."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DomoConfigEntry, hub_device_info
from .const import DOMAIN
from .coordinator import DomoCoordinator

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: DomoConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the refresh button to the account's hub device."""
    async_add_entities([DomoRefreshButton(entry.runtime_data, entry)])


class DomoRefreshButton(CoordinatorEntity[DomoCoordinator], ButtonEntity):
    """Re-sync all accounts in DOMO and fetch them now."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh"

    def __init__(self, coordinator: DomoCoordinator, entry: DomoConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_refresh"
        self._attr_device_info = hub_device_info(entry)

    @property
    def available(self) -> bool:
        # Stay pressable after a failed poll: that's when a manual retry helps most.
        return True

    async def async_press(self) -> None:
        if self.coordinator.pulling:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="refresh_in_progress"
            )
        if left := self.coordinator.pull_cooldown_left():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="refresh_too_soon",
                translation_placeholders={"seconds": str(left)},
            )
        await self.coordinator.async_pull()
