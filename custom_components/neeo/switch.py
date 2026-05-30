"""Switch platform - per-room power toggle plus a global one.

Per-room toggle:

* ``turn_on`` triggers the room's configured *default recipe*.
* ``turn_off`` triggers the poweroff paired (via ``scenario_key``) with
  whatever recipe is currently active in that room. If the active
  recipe is a one-shot custom recipe (e.g. ``TV Play``) with no
  poweroff partner, we log a warning and no-op.
* ``is_on`` mirrors whether the room has any active recipe.

Global toggle:

* ``turn_on`` triggers the default recipe in every room the user
  opted into Global-Power-ON in the OptionsFlow. Already-on rooms
  are skipped.
* ``turn_off`` shuts down every room with an active recipe,
  regardless of opt-in. The mental model is: "off is always off".
* ``is_on`` is *any* user_room having an active recipe (not just
  opt-in rooms) so the visible state matches what turn_off would do.

Switches are always exposed for every populated room; if the user
hasn't picked a default recipe, turn_on logs a warning and no-ops.
That keeps Discoverability obvious without forcing the OptionsFlow
to be completed before any Switch entity is registered.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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

    entities: list[SwitchEntity] = [
        NeeoRoomPowerSwitch(coordinator, room.key, room.name)
        for room in coordinator.data.user_rooms
    ]
    entities.append(NeeoGlobalPowerSwitch(coordinator))
    async_add_entities(entities)


class NeeoRoomPowerSwitch(CoordinatorEntity[NeeoCoordinator], SwitchEntity):
    """ON = launch default recipe. OFF = poweroff active recipe."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: NeeoCoordinator, room_key: str, room_name: str
    ) -> None:
        super().__init__(coordinator)
        self._room_key = room_key
        self._room_name = room_name
        self._attr_unique_id = f"neeo_room_power_{room_key}"
        self._attr_name = f"{room_name} Power"

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_room_on(self._room_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        active = self.coordinator.active_recipe_name(self._room_key)
        default = self.coordinator.default_recipe_for(self._room_key)
        return {
            "active_recipe": active or "",
            "default_recipe": default.name if default is not None else "",
            "in_global_toggle": self.coordinator.is_room_in_global_on(
                self._room_key
            ),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        recipe = self.coordinator.default_recipe_for(self._room_key)
        if recipe is None:
            _LOGGER.warning(
                "[neeo.switch] %s: no default recipe configured - skipping turn_on",
                self._room_name,
            )
            return
        _LOGGER.debug(
            "[neeo.switch] %s: turning on via default recipe %s",
            self._room_name,
            recipe.name,
        )
        await self.coordinator.execute_recipe(recipe.room_key, recipe.key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        active = self.coordinator.active_launch_recipe_for(self._room_key)
        if active is None:
            _LOGGER.debug(
                "[neeo.switch] %s: nothing active - turn_off is a no-op",
                self._room_name,
            )
            return
        poweroff = self.coordinator.paired_poweroff_for(active)
        if poweroff is None:
            _LOGGER.warning(
                "[neeo.switch] %s: active recipe %r has no poweroff pair"
                " (likely a custom one-shot) - skipping turn_off",
                self._room_name,
                active.name,
            )
            return
        _LOGGER.debug(
            "[neeo.switch] %s: turning off active recipe %s via poweroff %s",
            self._room_name,
            active.name,
            poweroff.name,
        )
        await self.coordinator.execute_recipe(poweroff.room_key, poweroff.key)


class NeeoGlobalPowerSwitch(CoordinatorEntity[NeeoCoordinator], SwitchEntity):
    """Global power: ON only opt-in rooms, OFF every room with active state."""

    _attr_has_entity_name = True
    _attr_name = "Global Power"

    def __init__(self, coordinator: NeeoCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"neeo_global_power_{coordinator.entry_id}"

    @property
    def is_on(self) -> bool:
        if self.coordinator.data is None:
            return False
        return any(
            self.coordinator.is_room_on(r.key)
            for r in self.coordinator.data.user_rooms
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        active_rooms: list[str] = []
        if self.coordinator.data is not None:
            for r in self.coordinator.data.user_rooms:
                if self.coordinator.is_room_on(r.key):
                    active_rooms.append(r.name)
        return {
            "active_rooms": active_rooms,
            "opt_in_rooms_for_on": list(
                self._opt_in_room_names()
            ),
        }

    def _opt_in_room_names(self) -> tuple[str, ...]:
        if self.coordinator.data is None:
            return ()
        names = []
        for r in self.coordinator.data.user_rooms:
            if self.coordinator.is_room_in_global_on(r.key):
                names.append(r.name)
        return tuple(names)

    async def async_turn_on(self, **kwargs: Any) -> None:
        # ON: only opt-in rooms, and only if they aren't already on.
        for room_key in self.coordinator.room_keys_for_global_on():
            if self.coordinator.is_room_on(room_key):
                continue
            recipe = self.coordinator.default_recipe_for(room_key)
            if recipe is None:
                _LOGGER.warning(
                    "[neeo.switch] Global ON: skipping room %s - no default recipe",
                    room_key,
                )
                continue
            _LOGGER.debug(
                "[neeo.switch] Global ON: launching %s in room %s",
                recipe.name,
                room_key,
            )
            await self.coordinator.execute_recipe(recipe.room_key, recipe.key)

    async def async_turn_off(self, **kwargs: Any) -> None:
        # OFF: affects every populated room with an active recipe,
        # regardless of opt-in. "Off is always off."
        if self.coordinator.data is None:
            return
        for room in self.coordinator.data.user_rooms:
            active = self.coordinator.active_launch_recipe_for(room.key)
            if active is None:
                continue
            poweroff = self.coordinator.paired_poweroff_for(active)
            if poweroff is None:
                _LOGGER.warning(
                    "[neeo.switch] Global OFF: room %s has active %r with no"
                    " poweroff pair - skipping",
                    room.name,
                    active.name,
                )
                continue
            _LOGGER.debug(
                "[neeo.switch] Global OFF: powering off %s in room %s",
                active.name,
                room.name,
            )
            await self.coordinator.execute_recipe(poweroff.room_key, poweroff.key)
