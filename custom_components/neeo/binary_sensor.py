"""Binary sensor platform - Brain reachability."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NeeoCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: NeeoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NeeoBrainOnlineSensor(coordinator)])


class NeeoBrainOnlineSensor(CoordinatorEntity[NeeoCoordinator], BinarySensorEntity):
    """Reflects whether the Brain has been reachable recently."""

    _attr_has_entity_name = True
    _attr_name = "Brain Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: NeeoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"neeo_brain_online_{coordinator.entry_id}"

    @property
    def is_on(self) -> bool:
        return self.coordinator.brain_online
