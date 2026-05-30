"""Shared entity base for the NEEO integration.

Every NEEO entity belongs to one logical device: the Brain itself.
Grouping everything under that device makes HA's UI render the
device-card with the standard Controls / Sensors / Diagnostic
sections (rather than an ungrouped flat list).
"""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NeeoCoordinator


class NeeoBrainEntity(CoordinatorEntity[NeeoCoordinator]):
    """Base for everything that lives under one NEEO Brain."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NeeoCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        entry = self.coordinator.entry
        host = entry.data.get(CONF_HOST, "")
        port = entry.data.get(CONF_PORT, 3000)
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry_id)},
            manufacturer="NEEO",
            model="NEEO Brain",
            name=entry.title or "NEEO Brain",
            configuration_url=f"http://{host}:{port}" if host else None,
        )
