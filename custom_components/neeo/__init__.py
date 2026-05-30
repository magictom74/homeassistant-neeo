"""The NEEO Smart Remote integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.network import get_url

from pyneeo import (
    NeeoBrainClient,
    NeeoConnectionError,
    NeeoTimeoutError,
    parse_forward_action,
)

from .const import (
    DEFAULT_PORT,
    DOMAIN,
    EVENT_MACRO_TRIGGERED,
    EVENT_RECIPE_LAUNCHED,
    EVENT_RECIPE_POWEROFF,
    FORWARD_ACTIONS_URL_BASE,
    SERVICE_EXECUTE_RECIPE,
    SERVICE_TRIGGER_MACRO,
)
from . import config_flow  # noqa: F401 - pre-import to avoid sync import_module in event loop
from .coordinator import NeeoCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SCENE,
    Platform.SENSOR,
    Platform.SWITCH,
]

EXECUTE_RECIPE_SCHEMA = vol.Schema(
    {
        vol.Required("room_key"): cv.string,
        vol.Required("recipe_key"): cv.string,
    }
)

TRIGGER_MACRO_SCHEMA = vol.Schema(
    {
        vol.Required("room_key"): cv.string,
        vol.Required("device_key"): cv.string,
        vol.Required("macro_key"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a NEEO Brain from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    client = NeeoBrainClient(host, port=port)

    coordinator = NeeoCoordinator(hass, client, entry=entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except (NeeoConnectionError, NeeoTimeoutError) as exc:
        await client.aclose()
        raise ConfigEntryNotReady(f"Cannot reach NEEO Brain at {host}:{port}: {exc}") from exc

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Register the HTTP view that receives the Brain's forward-action
    # pushes. URL is unique per entry so multiple Brains can coexist.
    view = NeeoForwardActionsView(entry.entry_id, coordinator, hass)
    hass.http.register_view(view)

    # Tell the Brain where to push. The Brain reaches *us* via the
    # HA-instance's primary URL.
    try:
        await _register_with_brain(hass, client, entry.entry_id)
    except (NeeoConnectionError, NeeoTimeoutError) as exc:
        _LOGGER.warning(
            "[neeo] Could not register forward actions with Brain: %s. "
            "Recipe state will not auto-update until the next reload.",
            exc,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear down a config entry."""
    coordinator: NeeoCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Best-effort unregister. Failing to unregister leaves a dangling
    # subscriber on the Brain but doesn't break HA.
    try:
        await coordinator.client.unregister_forward_actions()
    except (NeeoConnectionError, NeeoTimeoutError) as exc:
        _LOGGER.debug("[neeo] Brain unregister failed (ignored): %s", exc)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await coordinator.client.aclose()
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_EXECUTE_RECIPE)
            hass.services.async_remove(DOMAIN, SERVICE_TRIGGER_MACRO)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload on options change."""
    await hass.config_entries.async_reload(entry.entry_id)


# ---------------------------------------------------------------------------
# Forward-actions HTTP view
# ---------------------------------------------------------------------------


class NeeoForwardActionsView(HomeAssistantView):
    """Receives the Brain's forward-action POSTs.

    The Brain has no auth concept on the LAN, so this view runs without
    HA's bearer-token auth (``requires_auth = False``). Anyone with
    LAN access could in principle POST to this URL - that's the same
    threat model as the Brain itself, and HA's firewalling is the
    line of defence.
    """

    requires_auth = False
    cors_allowed = False

    def __init__(
        self,
        entry_id: str,
        coordinator: NeeoCoordinator,
        hass: HomeAssistant,
    ) -> None:
        self.url = f"{FORWARD_ACTIONS_URL_BASE}/{entry_id}"
        self.name = f"api:neeo:{entry_id}"
        self.entry_id = entry_id
        self.coordinator = coordinator
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except ValueError:
            return self.json({"error": "invalid json"}, status_code=400)
        if not isinstance(payload, dict):
            return self.json({"error": "expected object"}, status_code=400)

        event = parse_forward_action(payload)

        # Update the coordinator's cached state...
        self.coordinator.handle_event(event)

        # ...and surface the event on the HA bus so automations can
        # trigger off button presses, recipe activations, etc.
        bus_event_type = _bus_event_type_for(event)
        bus_payload = {
            "entry_id": self.entry_id,
            "action": event.action,
            "device": event.device,
            "room": event.room,
        }
        if hasattr(event, "recipe"):
            bus_payload["recipe"] = getattr(event, "recipe", "")
        self.hass.bus.async_fire(bus_event_type, bus_payload)

        _LOGGER.debug(
            "[neeo] Brain push: %s action=%s device=%s room=%s",
            type(event).__name__,
            event.action,
            event.device,
            event.room,
        )
        return self.json({"status": "ok"})


def _bus_event_type_for(event: Any) -> str:
    from pyneeo import MacroEvent, RecipeLaunchedEvent, RecipePoweroffEvent

    if isinstance(event, RecipeLaunchedEvent):
        return EVENT_RECIPE_LAUNCHED
    if isinstance(event, RecipePoweroffEvent):
        return EVENT_RECIPE_POWEROFF
    if isinstance(event, MacroEvent):
        return EVENT_MACRO_TRIGGERED
    return EVENT_MACRO_TRIGGERED


# ---------------------------------------------------------------------------
# Brain registration
# ---------------------------------------------------------------------------


async def _register_with_brain(
    hass: HomeAssistant,
    client: NeeoBrainClient,
    entry_id: str,
) -> None:
    """Tell the Brain to POST forward actions to our HTTP view.

    Uses HA's internal URL helper to figure out a LAN-routable URL
    for this HA instance. The Brain can't reach an external HTTPS URL
    (no TLS support on outbound), so we always use the internal one.
    """
    ha_url = get_url(hass, prefer_external=False, allow_internal=True)
    # ha_url is e.g. "http://192.168.40.20:8123" - we need host+port
    parsed = _parse_url(ha_url)
    path = f"{FORWARD_ACTIONS_URL_BASE}/{entry_id}"
    await client.register_forward_actions(
        host=parsed["host"], port=parsed["port"], path=path
    )
    _LOGGER.info(
        "[neeo] Registered forward-actions callback %s:%s%s with Brain",
        parsed["host"],
        parsed["port"],
        path,
    )


def _parse_url(url: str) -> dict[str, Any]:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "",
        "port": parsed.port or (443 if parsed.scheme == "https" else 80),
    }


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_EXECUTE_RECIPE):
        return

    async def _execute_recipe(call: ServiceCall) -> None:
        room_key: str = call.data["room_key"]
        recipe_key: str = call.data["recipe_key"]
        # Apply to all configured Brains - we don't currently target a
        # specific entry from the service call. If a recipe key
        # doesn't exist on a Brain, that Brain just 404s.
        for coordinator in _all_coordinators(hass):
            try:
                await coordinator.execute_recipe(room_key, recipe_key)
            except (NeeoConnectionError, NeeoTimeoutError) as exc:
                _LOGGER.warning("[neeo] execute_recipe failed: %s", exc)

    async def _trigger_macro(call: ServiceCall) -> None:
        room_key: str = call.data["room_key"]
        device_key: str = call.data["device_key"]
        macro_key: str = call.data["macro_key"]
        for coordinator in _all_coordinators(hass):
            try:
                await coordinator.trigger_macro(room_key, device_key, macro_key)
            except (NeeoConnectionError, NeeoTimeoutError) as exc:
                _LOGGER.warning("[neeo] trigger_macro failed: %s", exc)

    hass.services.async_register(
        DOMAIN, SERVICE_EXECUTE_RECIPE, _execute_recipe, schema=EXECUTE_RECIPE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TRIGGER_MACRO, _trigger_macro, schema=TRIGGER_MACRO_SCHEMA
    )


def _all_coordinators(hass: HomeAssistant) -> list[NeeoCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())
