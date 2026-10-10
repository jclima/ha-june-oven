"""Sensors for June Oven."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import JuneState
from .coordinator import JuneDataUpdateCoordinator
from .entity import JuneEntity
from .protocol import COOK_PHASES


@dataclass(frozen=True, kw_only=True)
class JuneSensorDescription(SensorEntityDescription):
    """Describe a June sensor."""

    value_fn: Callable[[JuneState], float | str | None]


SENSORS = (
    JuneSensorDescription(
        key="probe_temperature",
        translation_key="probe_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda state: state.probe_temp_c,
    ),
    JuneSensorDescription(
        key="progress",
        translation_key="progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda state: state.progress_percent,
    ),
    JuneSensorDescription(
        key="cook_phase",
        translation_key="cook_phase",
        device_class=SensorDeviceClass.ENUM,
        options=list(COOK_PHASES),
        value_fn=lambda state: state.cook_phase,
    ),
    JuneSensorDescription(
        key="cook_elapsed",
        translation_key="cook_elapsed",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        value_fn=lambda state: state.cook_elapsed_s,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up June sensors."""
    coordinator: JuneDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        JuneOvenSensor(coordinator, description) for description in SENSORS
    )


class JuneOvenSensor(JuneEntity, SensorEntity):
    """A sensor backed by retained June state."""

    entity_description: JuneSensorDescription

    def __init__(
        self,
        coordinator: JuneDataUpdateCoordinator,
        description: JuneSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator.data)
