# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Power-toggle switches** in the HA integration:
  - `switch.<room>_power` per populated room. ON triggers the user-picked
    default recipe; OFF triggers the poweroff partner of whatever
    recipe is currently active in the room (matched via
    ``scenario_key``).
  - `switch.power_global` per Brain. ON triggers default recipes only
    in rooms the user opted into the global toggle; OFF affects every
    populated room with an active recipe, opt-in or not - "off is
    always off".
  - OptionsFlow exposes the per-room default-recipe dropdown plus the
    global-on opt-in checkbox.
  - Active recipes without a poweroff partner (e.g. CUSTOM
    `TV Play` one-shots) are logged-and-skipped on turn_off instead
    of triggering the wrong recipe.

### Added

- **HA custom integration** (`custom_components/neeo/`):
  - `manifest.json` with zeroconf discovery on `_neeo._tcp.local.`,
    `iot_class: local_push`, requires `pyneeo==0.1.0`.
  - `config_flow.py` - user step (manual host/port) and zeroconf
    step. Brain `hostname` is used as the stable `unique_id` so the
    integration survives DHCP changes.
  - `coordinator.py` - push-driven state container. Initial inventory
    fetch via `get_project()`, then per-event updates from the
    forward-actions view. No polling.
  - `__init__.py` - sets up the `HomeAssistantView` at
    `/api/neeo/forward/<entry_id>` and registers it with the Brain.
    On teardown, unregisters and tears down platforms.
  - **Scenes** for each launch-typed recipe (hidden recipes excluded).
  - **Sensors** for active-recipe-per-room plus a diagnostics
    "Last Brain Push" sensor.
  - **Binary sensor** for Brain online status.
  - **Services** `neeo.execute_recipe` and `neeo.trigger_macro`.
  - **HA bus events** `neeo_recipe_launched`, `neeo_recipe_poweroff`,
    `neeo_macro_triggered` carrying the Brain payload.
- `hacs.json` so the integration is installable via HACS.

## [0.1.0] - 2026-05-30

### Added

- Initial release of the `pyneeo` async Python library for the NEEO
  Brain REST API.
- **REST client** (`NeeoBrainClient`) with the verified endpoints:
  `get_system_info`, `get_project`, `get_recipes`, `execute_recipe`,
  `trigger_macro`, plus forward-actions register / unregister / read.
- **Typed domain model** — frozen dataclasses for `Brain` / `Room` /
  `Device` / `Macro` / `Recipe` / `RecipeStep` / `SystemInfo`.
  Defensive parsers, all keys stringified (the Brain uses 64-bit ints
  that JavaScript downstream would otherwise corrupt).
- **mDNS discovery** — `discover_brains()` returns every
  `_neeo._tcp.local.` Brain visible on the LAN.
- **Forward-actions listener** — aiohttp web server that receives
  Brain pushes, parses them, dispatches to user handlers, and
  optionally relays the raw payload to a configurable forward chain
  for coexistence with other consumers (openHAB, ioBroker, ...).
- **Typed forward-action events** — `parse_forward_action()` dispatches
  Brain pushes to `RecipeLaunchedEvent`, `RecipePoweroffEvent`, or
  `MacroEvent`. Payload schemas captured from a real Brain.
- **Strict typing** — passes `mypy --strict`. PEP 561 `py.typed`
  marker, so downstream consumers get full type inference.
- **Documentation** — verified protocol notes in `docs/NEEO_API_NOTES.md`,
  architecture in `docs/ARCHITECTURE.md`.

[Unreleased]: https://github.com/magictom74/homeassistant-neeo/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/magictom74/homeassistant-neeo/releases/tag/v0.1.0
