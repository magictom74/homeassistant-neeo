"""State container for one NEEO Brain.

This is intentionally not a ``DataUpdateCoordinator`` in the polling
sense - the Brain pushes state to us via forward actions, and we
update the coordinator's data on every push. The initial inventory
snapshot is fetched once at setup time; after that, we only re-fetch
on explicit user request (service call) or after a long network
outage that broke the forward-actions registration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from pyneeo import (
    Brain,
    ForwardActionEvent,
    MacroEvent,
    NeeoBrainClient,
    Recipe,
    RecipeLaunchedEvent,
    RecipePoweroffEvent,
    Room,
)

from .const import (
    CONF_DEFAULT_RECIPE_KEY,
    CONF_IN_GLOBAL_TOGGLE,
    CONF_ROOMS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class NeeoCoordinator(DataUpdateCoordinator[Brain]):
    """Holds the Brain inventory and the room-by-room active-recipe map."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: NeeoBrainClient,
        *,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.entry_id}",
            # update_interval=None - we are push-driven, see module docstring
            update_interval=None,
        )
        self.client = client
        self.entry = entry
        self.entry_id = entry.entry_id
        # room_key -> recipe name currently considered active
        self._active_recipes: dict[str, str] = {}
        self._last_event_at: datetime | None = None
        self._brain_online = False

    # ------------------------------------------------------------------
    # initial fetch
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> Brain:
        """Initial inventory fetch.

        Called once by :meth:`DataUpdateCoordinator.async_config_entry_first_refresh`.
        After that, push handlers update the cached data in place.
        """
        _LOGGER.debug("[neeo.coordinator] Fetching Brain inventory")
        brain = await self.client.get_project()
        self._brain_online = True
        return brain

    # ------------------------------------------------------------------
    # state inspection (used by entities)
    # ------------------------------------------------------------------

    @property
    def brain_online(self) -> bool:
        return self._brain_online

    @property
    def last_event_at(self) -> datetime | None:
        return self._last_event_at

    def active_recipe_name(self, room_key: str) -> str | None:
        return self._active_recipes.get(room_key)

    def get_room(self, room_key: str) -> Room | None:
        if self.data is None:
            return None
        return self.data.get_room(room_key)

    def get_recipe(self, recipe_key: str) -> Recipe | None:
        if self.data is None:
            return None
        return self.data.get_recipe(recipe_key)

    # ------------------------------------------------------------------
    # push hook
    # ------------------------------------------------------------------

    def handle_event(self, event: ForwardActionEvent) -> None:
        """Apply a parsed forward-action event to our cached state.

        Called from the HomeAssistantView that receives the Brain's
        POSTs. Updates the active-recipe map and triggers a listener
        refresh so entities pick up the new state.
        """
        self._last_event_at = datetime.now(timezone.utc)
        self._brain_online = True

        # Forward-actions carry room *names*, not keys. To update our
        # per-key state map we resolve the name once against the
        # inventory.
        room = self._resolve_room_name(event.room)
        room_key = room.key if room is not None else event.room

        if isinstance(event, RecipeLaunchedEvent):
            self._active_recipes[room_key] = event.recipe
        elif isinstance(event, RecipePoweroffEvent):
            current = self._active_recipes.get(room_key)
            if current == event.recipe or current is None:
                self._active_recipes.pop(room_key, None)
        elif isinstance(event, MacroEvent):
            # Macros don't change recipe state, but they prove the
            # Brain is alive and reachable.
            pass

        # Notify entities even when no recipe field changed - the
        # last_event_at / brain_online attributes still moved.
        self.async_update_listeners()

    def _resolve_room_name(self, name: str) -> Room | None:
        if not name or self.data is None:
            return None
        return self.data.find_room_by_name(name)

    def mark_offline(self) -> None:
        """Called when the Brain hasn't been reachable for a while."""
        if self._brain_online:
            self._brain_online = False
            self.async_update_listeners()

    # ------------------------------------------------------------------
    # power-toggle helpers
    # ------------------------------------------------------------------

    def _room_options(self, room_key: str) -> dict[str, Any]:
        rooms_opts = self.entry.options.get(CONF_ROOMS, {})
        if isinstance(rooms_opts, dict):
            value = rooms_opts.get(room_key)
            if isinstance(value, dict):
                return value
        return {}

    def default_recipe_for(self, room_key: str) -> Recipe | None:
        """The recipe a Power-Switch turn_on triggers for this room.

        Returns ``None`` if the user hasn't picked one yet, or if the
        key they picked no longer exists on the Brain (recipe was
        deleted in the NEEO app).
        """
        key = self._room_options(room_key).get(CONF_DEFAULT_RECIPE_KEY) or ""
        if not key or self.data is None:
            return None
        recipe = self.data.get_recipe(key)
        return recipe if recipe is not None and recipe.is_launch else None

    def is_room_in_global_on(self, room_key: str) -> bool:
        """Whether Global-Power-ON should also start this room."""
        return bool(self._room_options(room_key).get(CONF_IN_GLOBAL_TOGGLE, False))

    def room_keys_for_global_on(self) -> tuple[str, ...]:
        if self.data is None:
            return ()
        return tuple(
            r.key for r in self.data.user_rooms if self.is_room_in_global_on(r.key)
        )

    def active_launch_recipe_for(self, room_key: str) -> Recipe | None:
        """Find the launch-Recipe corresponding to the currently-active recipe.

        We only track the active recipe by *name* (that's what the
        Brain pushes in forward actions). To act on it we need to
        look up the full Recipe so we can chain to its poweroff pair.
        """
        name = self._active_recipes.get(room_key)
        if not name:
            return None
        room = self.get_room(room_key)
        if room is None:
            return None
        for r in room.recipes:
            if r.is_launch and r.name == name:
                return r
        return None

    def paired_poweroff_for(self, launch: Recipe) -> Recipe | None:
        """Find the poweroff-Recipe paired with *launch* via ``scenario_key``.

        Returns ``None`` for custom one-shot launches (e.g. ``TV Play``)
        that have no poweroff counterpart. Callers should warn and no-op
        in that case.
        """
        if not launch.scenario_key:
            return None
        room = self.get_room(launch.room_key)
        if room is None:
            return None
        for r in room.recipes:
            if r.is_poweroff and r.scenario_key == launch.scenario_key:
                return r
        return None

    def is_room_on(self, room_key: str) -> bool:
        return self._active_recipes.get(room_key) is not None

    # ------------------------------------------------------------------
    # service helpers
    # ------------------------------------------------------------------

    async def execute_recipe(self, room_key: str, recipe_key: str) -> None:
        await self.client.execute_recipe(room_key, recipe_key)

    async def trigger_macro(
        self, room_key: str, device_key: str, macro_key: str
    ) -> None:
        await self.client.trigger_macro(room_key, device_key, macro_key)

    async def refresh_inventory(self) -> None:
        """Re-fetch the Brain inventory on demand.

        We don't poll, but the user can ask for a refresh via service
        call after editing recipes in the NEEO app. Not exposed on the
        scheduled update path.
        """
        self.data = await self.client.get_project()
        self.async_update_listeners()

    # ------------------------------------------------------------------
    # diagnostics
    # ------------------------------------------------------------------

    def diagnostics(self) -> dict[str, Any]:
        return {
            "brain_online": self._brain_online,
            "last_event_at": (
                self._last_event_at.isoformat()
                if self._last_event_at is not None
                else None
            ),
            "active_recipes": dict(self._active_recipes),
            "room_count": len(self.data.rooms) if self.data is not None else 0,
            "recipe_count": (
                len(self.data.all_recipes) if self.data is not None else 0
            ),
        }
