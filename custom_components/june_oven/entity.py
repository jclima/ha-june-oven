"""Base entity for June Oven."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JuneDataUpdateCoordinator


class JuneEntity(CoordinatorEntity[JuneDataUpdateCoordinator]):
    """Common June Oven entity behavior."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: JuneDataUpdateCoordinator, key: str) -> None:
        super().__init__(coordinator)
        identity = coordinator.client.identity
        self._attr_unique_id = f"{identity.oven_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity.oven_id)},
            manufacturer="June",
            model="June Oven",
            name=identity.device_name,
        )

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.coordinator.data.connection_state != "offline"
        )
