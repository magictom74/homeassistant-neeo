"""Constants for the NEEO Smart Remote integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "neeo"

# ConfigEntry data keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"

DEFAULT_PORT: Final = 3000

# HomeAssistantView URL slug for the Brain's forward-actions callback.
# Final URL: /api/neeo/forward/<entry_id>
FORWARD_ACTIONS_URL_BASE: Final = "/api/neeo/forward"

# HA bus events fired for every Brain push. User automations subscribe
# to these by event_type and filter on the payload (recipe name, macro
# name, room, ...).
EVENT_RECIPE_LAUNCHED: Final = "neeo_recipe_launched"
EVENT_RECIPE_POWEROFF: Final = "neeo_recipe_poweroff"
EVENT_MACRO_TRIGGERED: Final = "neeo_macro_triggered"

# Service names
SERVICE_EXECUTE_RECIPE: Final = "execute_recipe"
SERVICE_TRIGGER_MACRO: Final = "trigger_macro"

# Options-flow keys
CONF_ROOMS: Final = "rooms"
CONF_DEFAULT_RECIPE_KEY: Final = "default_recipe_key"
CONF_IN_GLOBAL_TOGGLE: Final = "in_global_toggle"
