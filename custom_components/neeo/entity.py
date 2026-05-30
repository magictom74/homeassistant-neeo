"""Shared entity bases for the NEEO integration.

The device registry layout is two-tier:

* **Brain** - one device per ConfigEntry. Holds global controls
  (Online / Last Push / Global Power).
* **Room** - one device per populated room, linked to the Brain via
  ``via_device``. Holds that room's Power switch, Active-Recipe
  sensor, and all of its Recipe scenes.

HA's auto-card-layout (Controls / Sensors / Diagnostic) operates per
device, so this split is what makes each room get its own card with
just *its* entities - instead of one giant Brain card with everything
mashed together.
"""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NeeoCoordinator


def brain_identifier(entry_id: str) -> tuple[str, str]:
    """Stable identifier tuple for the Brain device."""
    return (DOMAIN, entry_id)


def room_identifier(entry_id: str, room_key: str) -> tuple[str, str]:
    """Stable identifier tuple for one room device."""
    return (DOMAIN, f"{entry_id}_room_{room_key}")


def _brain_device_info(entry: ConfigEntry) -> DeviceInfo:
    host = entry.data.get(CONF_HOST, "")
    port = entry.data.get(CONF_PORT, 3000)
    return DeviceInfo(
        identifiers={brain_identifier(entry.entry_id)},
        manufacturer="NEEO",
        model="NEEO Brain",
        name=entry.title or "NEEO Brain",
        configuration_url=f"http://{host}:{port}" if host else None,
    )


def _room_device_info(entry: ConfigEntry, room_key: str, room_name: str) -> DeviceInfo:
    display = room_name if room_name else f"Room {room_key}"
    return DeviceInfo(
        identifiers={room_identifier(entry.entry_id, room_key)},
        manufacturer="NEEO",
        # Model carries the room name so HA's Device-info detail panel
        # (which shows model prominently) makes each room distinct
        # instead of all looking like "NEEO Room".
        model=f"NEEO Room - {display}",
        name=f"NEEO {display}",
        via_device=brain_identifier(entry.entry_id),
    )


class NeeoBrainEntity(CoordinatorEntity[NeeoCoordinator]):
    """Base for entities that belong to the Brain itself."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NeeoCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        return _brain_device_info(self.coordinator.entry)


class NeeoRoomEntity(CoordinatorEntity[NeeoCoordinator]):
    """Base for entities that belong to one specific room."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NeeoCoordinator,
        room_key: str,
        room_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._room_key = room_key
        self._room_name = room_name

    @property
    def device_info(self) -> DeviceInfo:
        return _room_device_info(self.coordinator.entry, self._room_key, self._room_name)
