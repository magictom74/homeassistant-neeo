"""Scene platform - one Scene entity per NEEO recipe.

The Brain's ``execute`` endpoint is idempotent and decides itself
whether it launches or powers off based on the recipe's ``type``.
We expose only ``launch``-typed recipes as Scenes; matching
``poweroff`` recipes are addressed via the
``neeo.execute_recipe`` service or via the launch recipe naturally
toggling.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyneeo import Recipe

from .const import DOMAIN
from .coordinator import NeeoCoordinator
from .entity import room_identifier, brain_identifier

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: NeeoCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.data is None:
        return
    entities = [
        NeeoRecipeScene(coordinator, recipe)
        for recipe in coordinator.data.all_recipes
        if recipe.is_launch and not recipe.is_hidden
    ]
    async_add_entities(entities)


class NeeoRecipeScene(Scene):
    """Activates a NEEO recipe."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NeeoCoordinator, recipe: Recipe) -> None:
        self._coordinator = coordinator
        self._recipe = recipe
        self._attr_unique_id = f"{coordinator.entry_id}_recipe_{recipe.key}"
        self._attr_name = recipe.name
        self._attr_extra_state_attributes = {
            "recipe_key": recipe.key,
            "room_key": recipe.room_key,
            "room_name": recipe.room_name,
            "main_device_type": recipe.main_device_type,
            "scenario_key": recipe.scenario_key,
        }
        # Each recipe lives under its room device, which itself hangs
        # off the Brain via via_device.
        if recipe.room_key:
            identifier = room_identifier(coordinator.entry_id, recipe.room_key)
            via = brain_identifier(coordinator.entry_id)
            self._attr_device_info = DeviceInfo(
                identifiers={identifier},
                manufacturer="NEEO",
                model="NEEO Room",
                name=f"NEEO {recipe.room_name}" if recipe.room_name else "NEEO Room",
                via_device=via,
            )
        else:
            # Custom recipes with no room key fall back to the Brain
            self._attr_device_info = DeviceInfo(
                identifiers={brain_identifier(coordinator.entry_id)},
                manufacturer="NEEO",
                model="NEEO Brain",
                name=coordinator.entry.title or "NEEO Brain",
            )

    async def async_activate(self, **kwargs: Any) -> None:
        _LOGGER.debug(
            "[neeo.scene] Activating recipe %s (%s) in room %s",
            self._recipe.name,
            self._recipe.key,
            self._recipe.room_key,
        )
        await self._coordinator.execute_recipe(
            self._recipe.room_key, self._recipe.key
        )
