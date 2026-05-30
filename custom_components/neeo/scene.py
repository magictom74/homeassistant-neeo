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
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pyneeo import Recipe

from .const import DOMAIN
from .coordinator import NeeoCoordinator

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
        entry = coordinator.entry
        host = entry.data.get(CONF_HOST, "")
        port = entry.data.get(CONF_PORT, 3000)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            manufacturer="NEEO",
            model="NEEO Brain",
            name=entry.title or "NEEO Brain",
            configuration_url=f"http://{host}:{port}" if host else None,
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
