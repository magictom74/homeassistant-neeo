"""pyneeo - async Python library for the NEEO Brain REST API."""

from __future__ import annotations

from .client import DEFAULT_PORT, DEFAULT_TIMEOUT, NeeoBrainClient
from .discovery import DEFAULT_DISCOVERY_TIMEOUT, NEEO_SERVICE_TYPE, DiscoveredBrain, discover_brains
from .events import (
    ForwardActionEvent,
    MacroEvent,
    RecipeLaunchedEvent,
    RecipePoweroffEvent,
    parse_forward_action,
)
from .exceptions import (
    NeeoConnectionError,
    NeeoError,
    NeeoNotFoundError,
    NeeoProtocolError,
    NeeoTimeoutError,
)
from .listener import (
    DEFAULT_FORWARD_TIMEOUT,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PATH,
    EventHandler,
    ForwardActionsListener,
)
from .models import (
    Brain,
    Device,
    Macro,
    Recipe,
    RecipeStep,
    Room,
    SystemInfo,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_DISCOVERY_TIMEOUT",
    "DEFAULT_FORWARD_TIMEOUT",
    "DEFAULT_LISTEN_HOST",
    "DEFAULT_LISTEN_PATH",
    "DEFAULT_PORT",
    "DEFAULT_TIMEOUT",
    "NEEO_SERVICE_TYPE",
    "Brain",
    "Device",
    "DiscoveredBrain",
    "EventHandler",
    "ForwardActionEvent",
    "ForwardActionsListener",
    "Macro",
    "MacroEvent",
    "NeeoBrainClient",
    "NeeoConnectionError",
    "NeeoError",
    "NeeoNotFoundError",
    "NeeoProtocolError",
    "NeeoTimeoutError",
    "Recipe",
    "RecipeLaunchedEvent",
    "RecipePoweroffEvent",
    "RecipeStep",
    "Room",
    "SystemInfo",
    "discover_brains",
    "parse_forward_action",
]
