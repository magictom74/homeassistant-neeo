# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
