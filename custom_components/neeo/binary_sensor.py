"""Binary sensor platform - Brain reachability."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NeeoCoordinator
from .entity import NeeoBrainEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: NeeoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NeeoBrainOnlineSensor(coordinator)])


class NeeoBrainOnlineSensor(NeeoBrainEntity, BinarySensorEntity):
    """Reflects whether the Brain has been reachable recently."""

    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: NeeoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_brain_online"

    @property
    def is_on(self) -> bool:
        return self.coordinator.brain_online
