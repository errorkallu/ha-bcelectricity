"""BC Hydro sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BCHydroConfigEntry
from .api import BCHydroData
from .const import DOMAIN
from .coordinator import BCHydroCoordinator

CAD = "CAD"


@dataclass(frozen=True, kw_only=True)
class BCHydroSensorDescription(SensorEntityDescription):
    """Describes a BC Hydro sensor."""

    value_fn: Callable[[BCHydroData], float | date | None]
    attrs_fn: Callable[[BCHydroData], dict[str, Any]] | None = None


def _latest_attrs(data: BCHydroData) -> dict[str, Any]:
    latest = data.latest
    return {
        "date": latest.day.isoformat() if latest else None,
        "last_7_days": [
            {"date": r.day.isoformat(), "kwh": r.kwh, "cost": r.cost}
            for r in data.daily[-7:]
        ],
    }


def _day(data: BCHydroData, days_back: int):
    """Reading for the Nth most recent day (1 = latest, normally yesterday)."""
    return data.daily[-days_back] if len(data.daily) >= days_back else None


def _past_day_sensors(days_back: int) -> tuple[BCHydroSensorDescription, ...]:
    label = f"days_ago_{days_back}"
    return (
        BCHydroSensorDescription(
            key=f"{label}_consumption",
            translation_key=f"{label}_consumption",
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            suggested_display_precision=2,
            value_fn=lambda d: r.kwh if (r := _day(d, days_back)) else None,
            attrs_fn=lambda d: {"date": r.day.isoformat() if (r := _day(d, days_back)) else None},
        ),
        BCHydroSensorDescription(
            key=f"{label}_cost",
            translation_key=f"{label}_cost",
            native_unit_of_measurement=CAD,
            device_class=SensorDeviceClass.MONETARY,
            suggested_display_precision=2,
            value_fn=lambda d: r.cost if (r := _day(d, days_back)) else None,
            attrs_fn=lambda d: {"date": r.day.isoformat() if (r := _day(d, days_back)) else None},
        ),
    )


SENSORS: tuple[BCHydroSensorDescription, ...] = (
    BCHydroSensorDescription(
        key="yesterday_consumption",
        translation_key="yesterday_consumption",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=2,
        value_fn=lambda d: d.latest.kwh if d.latest else None,
        attrs_fn=_latest_attrs,
    ),
    BCHydroSensorDescription(
        key="yesterday_cost",
        translation_key="yesterday_cost",
        native_unit_of_measurement=CAD,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=lambda d: d.latest.cost if d.latest else None,
        attrs_fn=lambda d: {"date": d.latest.day.isoformat() if d.latest else None},
    ),
    # One kWh and one cost sensor for each of the 6 days before yesterday.
    *(desc for n in range(2, 8) for desc in _past_day_sensors(n)),
    BCHydroSensorDescription(
        key="consumption_to_date",
        translation_key="consumption_to_date",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        # Resets at each new billing period; total_increasing handles that,
        # so this one can be used in the Energy dashboard.
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda d: d.consumption_to_date,
    ),
    BCHydroSensorDescription(
        key="cost_to_date",
        translation_key="cost_to_date",
        native_unit_of_measurement=CAD,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=lambda d: d.cost_to_date,
    ),
    BCHydroSensorDescription(
        key="projected_consumption",
        translation_key="projected_consumption",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=0,
        value_fn=lambda d: d.projected_consumption,
    ),
    BCHydroSensorDescription(
        key="projected_cost",
        translation_key="projected_cost",
        native_unit_of_measurement=CAD,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=lambda d: d.projected_cost,
    ),
    BCHydroSensorDescription(
        key="billing_period_start",
        translation_key="billing_period_start",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda d: d.billing_start,
    ),
    BCHydroSensorDescription(
        key="billing_period_end",
        translation_key="billing_period_end",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda d: d.billing_end,
    ),
    BCHydroSensorDescription(
        key="balance",
        translation_key="balance",
        native_unit_of_measurement=CAD,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=lambda d: d.balance,
    ),
    BCHydroSensorDescription(
        key="last_bill_amount",
        translation_key="last_bill_amount",
        native_unit_of_measurement=CAD,
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        value_fn=lambda d: d.last_bill_amount,
        attrs_fn=lambda d: {"bill_date": d.last_bill_date},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BCHydroConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create sensors for a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(BCHydroSensor(coordinator, desc) for desc in SENSORS)


class BCHydroSensor(CoordinatorEntity[BCHydroCoordinator], SensorEntity):
    """A single value from the daily BC Hydro scrape."""

    _attr_has_entity_name = True
    entity_description: BCHydroSensorDescription

    def __init__(
        self, coordinator: BCHydroCoordinator, description: BCHydroSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        account = coordinator.data.account_number if coordinator.data else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name="BC Hydro",
            manufacturer="BC Hydro",
            model=f"Account {account}" if account else "Customer account",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://app.bchydro.com/",
        )

    @property
    def native_value(self) -> float | date | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
