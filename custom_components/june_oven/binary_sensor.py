"""Binary sensors for June Oven."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import JuneState
from .coordinator import JuneDataUpdateCoordinator
from .entity import JuneEntity


@dataclass(frozen=True, kw_only=True)
class JuneBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a June binary sensor."""

    value_fn: Callable[[JuneState], bool]


BINARY_SENSORS = (
    JuneBinarySensorDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.online,
    ),
    JuneBinarySensorDescription(
        key="ready",
        translation_key="ready",
        value_fn=lambda state: state.ready,
    ),
    JuneBinarySensorDescription(
        key="done",
        translation_key="done",
        value_fn=lambda state: state.done,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up June binary sensors."""
    coordinator: JuneDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        JuneOvenBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class JuneOvenBinarySensor(JuneEntity, BinarySensorEntity):
    """A binary sensor backed by retained June state."""

    entity_description: JuneBinarySensorDescription

    def __init__(
        self,
        coordinator: JuneDataUpdateCoordinator,
        description: JuneBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the current binary state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Keep connectivity visible while the oven is offline."""
        if self.entity_description.key == "connected":
            return self.coordinator.last_update_success
        return super().available
