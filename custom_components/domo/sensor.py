"""Sensors for DOMO utility accounts."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import DomoConfigEntry
from .const import CURRENCY, DAILY_USAGE_SERVICES, DOMAIN, METERS, service_name
from .coordinator import DomoAccount, DomoCoordinator

PARALLEL_UPDATES = 0


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _ts(value: Any) -> datetime | None:
    return dt_util.parse_datetime(value) if isinstance(value, str) else None


def _meter(acc: DomoAccount) -> tuple[str | None, SensorDeviceClass | None]:
    return METERS.get(acc.service, (None, None))


def _has_meter(acc: DomoAccount) -> bool:
    return _meter(acc)[0] is not None


@dataclass(frozen=True, kw_only=True)
class DomoSensorDescription(SensorEntityDescription):
    """Describe a DOMO sensor; `metered` ones take unit and class from the service."""

    exists_fn: Callable[[DomoAccount], bool]
    value_fn: Callable[[DomoAccount], Any]
    metered: bool = False
    attrs_fn: Callable[[DomoAccount], dict[str, Any] | None] | None = None


SENSORS: tuple[DomoSensorDescription, ...] = (
    DomoSensorDescription(
        key="balance",
        translation_key="balance",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        suggested_display_precision=2,
        exists_fn=lambda a: "balance" in a.account,
        value_fn=lambda a: _num(a.account.get("balance")),
    ),
    DomoSensorDescription(
        key="meter_reading",
        translation_key="meter_reading",
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        metered=True,
        exists_fn=lambda a: "last_readings_value" in a.account and _has_meter(a),
        value_fn=lambda a: _num(a.account.get("last_readings_value")),
    ),
    DomoSensorDescription(
        key="reading_date",
        translation_key="reading_date",
        device_class=SensorDeviceClass.TIMESTAMP,
        exists_fn=lambda a: "last_readings_date" in a.account,
        value_fn=lambda a: _ts(a.account.get("last_readings_date")),
    ),
    DomoSensorDescription(
        key="month_usage",
        translation_key="month_usage",
        suggested_display_precision=2,
        metered=True,
        exists_fn=lambda a: "usage_this_month" in a.account and _has_meter(a),
        value_fn=lambda a: _num(a.account.get("usage_this_month")),
    ),
    DomoSensorDescription(
        key="month_charge",
        translation_key="month_charge",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        suggested_display_precision=2,
        exists_fn=lambda a: isinstance(a.analytics, dict),
        value_fn=lambda a: _num((a.analytics or {}).get("this_month")),
        attrs_fn=lambda a: {"previous_month": _num((a.analytics or {}).get("previous_month"))},
    ),
    DomoSensorDescription(
        key="last_day_usage",
        translation_key="last_day_usage",
        suggested_display_precision=2,
        metered=True,
        exists_fn=lambda a: a.service in DAILY_USAGE_SERVICES and _has_meter(a),
        value_fn=lambda a: _num((a.last_day or {}).get("usage")),
        attrs_fn=lambda a: {
            "date": (a.last_day or {}).get("date"),
            "charge": _num((a.last_day or {}).get("paid_amount")),
        },
    ),
    DomoSensorDescription(
        key="last_day_charge",
        translation_key="last_day_charge",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        suggested_display_precision=2,
        exists_fn=lambda a: a.service in DAILY_USAGE_SERVICES,
        value_fn=lambda a: _num((a.last_day or {}).get("paid_amount")),
        attrs_fn=lambda a: {"date": (a.last_day or {}).get("date")},
    ),
    DomoSensorDescription(
        key="updated_at",
        translation_key="updated_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda a: "updated_at" in a.account,
        value_fn=lambda a: _ts(a.account.get("updated_at")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: DomoConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create sensors per account, and for accounts added in DOMO later on."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [acc_id for acc_id in (coordinator.data or {}) if acc_id not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            DomoSensor(coordinator, acc_id, description)
            for acc_id in new
            for description in SENSORS
            if description.exists_fn(coordinator.data[acc_id])
        )

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class DomoSensor(CoordinatorEntity[DomoCoordinator], SensorEntity):
    """One value of one DOMO utility account."""

    entity_description: DomoSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DomoCoordinator,
        account_id: str,
        description: DomoSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._account_id = account_id
        acc = coordinator.data[account_id]
        if description.metered:
            unit, device_class = _meter(acc)
            self._attr_native_unit_of_measurement = unit
            self._attr_device_class = device_class
        number = acc.account.get("account_number") or account_id[:8]
        self._attr_unique_id = f"{account_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_id)},
            name=f"{service_name(acc.service, coordinator.language)} {number}",
            manufacturer="DOMO",
            model=acc.home_label,
            serial_number=number,
            configuration_url="https://domo.uz",
            via_device_id=coordinator.hub_device_id,
        )

    @property
    def _acc(self) -> DomoAccount | None:
        return (self.coordinator.data or {}).get(self._account_id)

    @property
    def available(self) -> bool:
        return super().available and self._acc is not None

    @property
    def native_value(self) -> float | datetime | date | None:
        acc = self._acc
        return self.entity_description.value_fn(acc) if acc else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        acc = self._acc
        if acc is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(acc)
