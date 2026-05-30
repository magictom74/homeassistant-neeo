# homeassistant-neeo

Home Assistant custom integration for the [NEEO](https://en.wikipedia.org/wiki/Neeo)
Smart Remote system, plus the async Python library `pyneeo` that powers
it. The library is HA-agnostic and usable from any Python codebase.

Reverse-engineered against NEEO Brain firmware `0.53.9` (April 2018, the
last firmware before NEEO was discontinued). All documented endpoints
have been verified live against a real Brain.

**Status:** Alpha. The library is the first thing in place; the HA
custom-component layer lands next. The public API may still change
before 1.0.

## Why this exists

NEEO (the company) was acquired by Control4 in 2019 and the product was
discontinued shortly after. Brains keep running for years, but there's
no first-party path to integrate them with modern smart-home platforms.
The community options (`iobroker.neeo`, `mqtt-neeo-bridge`, openHAB's
binding) all rely on either polling or a maintainer who has moved on.
This project is a clean-room, push-driven alternative that follows
Home Assistant's modern integration patterns.

## Features (pyneeo, v0.1)

- **REST client** — `NeeoBrainClient` with the verified endpoints:
  `get_system_info`, `get_project`, `get_recipes`, `execute_recipe`,
  `trigger_macro`, plus forward-actions register/unregister/read.
- **Typed domain model** — frozen dataclasses for `Brain` / `Room` /
  `Device` / `Macro` / `Recipe` / `RecipeStep` / `SystemInfo`. Defensive
  parsers, all keys stringified (the Brain uses 64-bit ints that
  JavaScript would otherwise corrupt).
- **mDNS discovery** — `discover_brains()` returns every
  `_neeo._tcp.local.` Brain visible on the LAN.
- **Typed forward-action events** — `parse_forward_action()` dispatches
  Brain pushes to `RecipeLaunchedEvent`, `RecipePoweroffEvent`, or
  `MacroEvent`. Payloads are captured from a real Brain, not guessed.
- **Strict typing** — passes `mypy --strict`. PEP 561 `py.typed`
  marker, so downstream consumers get full type inference.

Coming next (v0.2+):

- HTTP listener that receives the Brain's forward-action pushes (the
  push half of the loop; v0.1 only registers / unregisters).
- HA `custom_components/neeo/` integration: config flow with mDNS
  auto-discovery, scenes for recipes, events for button presses.

## Installing

```bash
pip install pyneeo            # not yet on PyPI - use editable install
```

For local development:

```bash
git clone git@github.com:magictom74/homeassistant-neeo.git
cd homeassistant-neeo
pip install -e ".[dev]"
```

## Quickstart

```python
import asyncio
from pyneeo import NeeoBrainClient, discover_brains

async def main() -> None:
    # Either discover Brains via mDNS...
    brains = await discover_brains()
    if not brains:
        raise SystemExit("No NEEO Brain found on the LAN")
    host = brains[0].host

    # ...or use a known IP:
    # host = "192.168.40.10"

    async with NeeoBrainClient(host) as client:
        info = await client.get_system_info()
        print(f"Connected to {info.hostname} (firmware {info.firmware})")

        brain = await client.get_project()
        for recipe in brain.all_recipes:
            print(f"  recipe: {recipe.name} ({recipe.type}) in {recipe.room_name}")

        # Trigger the first launch-type recipe we see
        recipe = next((r for r in brain.all_recipes if r.is_launch), None)
        if recipe is not None:
            await client.execute_recipe(recipe.room_key, recipe.key)

asyncio.run(main())
```

## Forward-action events

The Brain pushes JSON to a registered HTTP endpoint on every action -
remote button presses, recipe launches, app interactions. v0.1 ships
the registration API and a typed parser; the HTTP listener that
receives the pushes lives in the next release (or in the HA
custom-component layer).

```python
from pyneeo import parse_forward_action, RecipeLaunchedEvent, MacroEvent

# Brain pushed this:
event = parse_forward_action({
    "action": "VOLUME UP",
    "device": "AV Receiver",
    "room": "Living",
})
assert isinstance(event, MacroEvent)
assert event.action == "VOLUME UP"
```

## Why not poll?

The NEEO Brain is from 2018 and never got a hardware refresh.
Hammering it with 60-second polling cycles - what some existing
integrations do - measurably slows it down. This library has one rule:
**no polling**. Use `get_project()` for the initial snapshot, then
subscribe to forward-actions and act on Brain pushes.

## License

MIT - see [LICENSE](LICENSE).
