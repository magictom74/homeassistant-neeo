"""Sensor platform - active-recipe-per-room and Brain metadata."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NeeoCoordinator
from .entity import NeeoBrainEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: NeeoCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.data is None:
        return

    entities: list[SensorEntity] = []
    # Only expose rooms the user has actually populated. The Brain
    # ships with a fixed catalogue and returns all the unused ones too.
    for room in coordinator.data.user_rooms:
        entities.append(NeeoActiveRecipeSensor(coordinator, room.key, room.name))
    entities.append(NeeoLastEventSensor(coordinator))
    async_add_entities(entities)


class NeeoActiveRecipeSensor(NeeoBrainEntity, SensorEntity):
    """Active recipe name in a room, or 'off' if none is running."""

    def __init__(
        self, coordinator: NeeoCoordinator, room_key: str, room_name: str
    ) -> None:
        super().__init__(coordinator)
        self._room_key = room_key
        self._room_name = room_name
        self._attr_unique_id = f"{coordinator.entry_id}_active_recipe_{room_key}"
        self._attr_name = f"{room_name} Active Recipe"

    @property
    def native_value(self) -> str:
        recipe = self.coordinator.active_recipe_name(self._room_key)
        return recipe if recipe else "off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"room_key": self._room_key, "room_name": self._room_name}


class NeeoLastEventSensor(NeeoBrainEntity, SensorEntity):
    """Wall-clock of the last Brain push, exposed for diagnostics."""

    _attr_name = "Last Brain Push"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: NeeoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_last_event"

    @property
    def native_value(self) -> str:
        when = self.coordinator.last_event_at
        return when.isoformat() if when is not None else "never"

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
