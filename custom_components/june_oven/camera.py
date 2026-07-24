"""Interior camera for June Oven."""

from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import JuneDataUpdateCoordinator
from .entity import JuneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the June interior camera."""
    coordinator: JuneDataUpdateCoordinator = entry.runtime_data
    async_add_entities([JuneOvenCamera(coordinator)])


class JuneOvenCamera(JuneEntity, Camera):
    """Expose the latest native June interior still."""

    _attr_translation_key = "interior"
    _attr_brand = "June"
    _attr_model = "June Oven"
    _attr_frame_interval = 1.0

    def __init__(self, coordinator: JuneDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "camera")
        Camera.__init__(self)

    @property
    def is_on(self) -> bool:
        """Return whether the oven is actively producing camera frames."""
        return self.coordinator.data.active

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the latest oven image."""
        return await self.coordinator.client.async_fetch_camera_image()
