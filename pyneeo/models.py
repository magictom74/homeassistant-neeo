"""Frozen-dataclass models for the NEEO Brain domain.

The NEEO Brain returns large nested JSON trees rooted at
``/v1/projects/home``. The classes here cover only the fields the
library cares about; unknown fields are silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _str(raw: Any, default: str = "") -> str:
    """Coerce *raw* to ``str`` defensively.

    NEEO Brain returns recipe/room/device keys as large integers in
    some endpoints and as strings in others; we always stringify so
    that JSON round-tripping in JavaScript (>2^53 precision loss) is
    never a problem on the consumer side.
    """
    if raw is None:
        return default
    if isinstance(raw, str):
        return raw
    return str(raw)


def _bool(raw: Any, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.lower() in ("true", "1", "yes")
    if isinstance(raw, (int, float)):
        return bool(raw)
    return default


@dataclass(frozen=True, slots=True)
class Macro:
    """A device-level action that can be triggered on the Brain.

    Examples: ``POWER ON``, ``VOLUME UP``, ``CHANNEL_01``. Trigger URL:
    ``/v1/projects/home/rooms/<room_key>/devices/<device_key>/macros/<key>/trigger``.
    """

    key: str
    name: str
    label: str = ""

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Macro:
        return cls(
            key=_str(raw.get("key")),
            name=_str(raw.get("name")),
            label=_str(raw.get("label"), default=_str(raw.get("name"))),
        )


@dataclass(frozen=True, slots=True)
class Device:
    """A NEEO device attached to a room (TV, AVR, Hue bridge, ...).

    ``macros`` are the per-device actions. We don't currently model
    capabilities or sliders because v0.1 only needs trigger semantics.
    """

    key: str
    name: str
    room_key: str
    room_name: str = ""
    manufacturer: str = ""
    model: str = ""
    device_type: str = ""
    macros: tuple[Macro, ...] = ()

    @classmethod
    def from_raw(
        cls,
        raw: dict[str, Any],
        *,
        room_key: str = "",
        room_name: str = "",
    ) -> Device:
        macros_raw = raw.get("macros") or []
        if isinstance(macros_raw, dict):
            macros_raw = list(macros_raw.values())
        macros = tuple(
            Macro.from_raw(m) for m in macros_raw if isinstance(m, dict)
        )
        # Real Brain (firmware 0.53.9) nests manufacturer / type / model
        # under `details`. The flat-shape lookups remain as a fallback
        # for the `/v1/api/Recipes` convenience endpoint which uses
        # different field names ("manufacturer", "model", "devicetype").
        details_raw = raw.get("details")
        details: dict[str, Any] = details_raw if isinstance(details_raw, dict) else {}
        manufacturer = (
            _str(raw.get("manufacturer"))
            or _str(details.get("manufacturer"))
        )
        # `details.name` is the manufacturer's model designation
        # (e.g. "AVR-4520 AVR"); top-level `model` from the
        # convenience endpoint also works.
        model = _str(raw.get("model")) or _str(details.get("name"))
        device_type = (
            _str(raw.get("type"))
            or _str(raw.get("devicetype"))
            or _str(details.get("type"))
        )
        return cls(
            key=_str(raw.get("key")),
            name=_str(raw.get("name")),
            room_key=_str(raw.get("roomKey"), default=room_key),
            room_name=_str(raw.get("roomName"), default=room_name),
            manufacturer=manufacturer,
            model=model,
            device_type=device_type,
            macros=macros,
        )

    def get_macro(self, key: str) -> Macro | None:
        for m in self.macros:
            if m.key == key:
                return m
        return None

    def find_macro_by_name(self, name: str) -> Macro | None:
        """Case-insensitive lookup. ``"volume up"`` matches ``VOLUME UP``."""
        target = name.lower()
        for m in self.macros:
            if m.name.lower() == target:
                return m
        return None


@dataclass(frozen=True, slots=True)
class RecipeStep:
    """One step in a recipe's playback list.

    The NEEO Brain distinguishes step ``type`` (``action``, ``delay``,
    ``volume``, etc.). We keep this loose; consumers that only care
    about top-level recipe triggering can ignore steps entirely.
    """

    type: str
    label: str = ""
    device_key: str = ""
    device_name: str = ""
    component_name: str = ""
    delay_ms: int | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> RecipeStep:
        delay = raw.get("delay")
        delay_ms: int | None
        if isinstance(delay, (int, float)):
            delay_ms = int(delay)
        else:
            delay_ms = None
        return cls(
            type=_str(raw.get("type")),
            label=_str(raw.get("label")),
            device_key=_str(raw.get("deviceKey")),
            device_name=_str(raw.get("deviceName")),
            component_name=_str(raw.get("componentName")),
            delay_ms=delay_ms,
        )


@dataclass(frozen=True, slots=True)
class Recipe:
    """A NEEO recipe (activity) - the user-facing automation unit.

    Two flavours exist on the Brain:

    * ``type="launch"`` - power-on side of an activity (e.g. ``TV``).
    * ``type="poweroff"`` - power-off side, usually paired with a launch
      via ``scenarioKey``.

    Recipes are triggered via
    ``/v1/projects/home/rooms/<room_key>/recipes/<key>/execute``
    (always GET, regardless of launch/poweroff).
    """

    key: str
    name: str
    type: str
    room_key: str
    room_name: str = ""
    scenario_key: str = ""
    main_device_type: str = ""
    enabled: bool = True
    is_hidden: bool = False
    is_custom: bool = False
    steps: tuple[RecipeStep, ...] = ()

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Recipe:
        steps_raw = raw.get("steps") or []
        steps = tuple(
            RecipeStep.from_raw(s) for s in steps_raw if isinstance(s, dict)
        )
        return cls(
            key=_str(raw.get("key")),
            name=_str(raw.get("name")),
            type=_str(raw.get("type")),
            room_key=_str(raw.get("roomKey")),
            room_name=_str(raw.get("roomName")),
            scenario_key=_str(raw.get("scenarioKey")),
            main_device_type=_str(raw.get("mainDeviceType")),
            enabled=_bool(raw.get("enabled"), default=True),
            is_hidden=_bool(raw.get("isHiddenRecipe")),
            is_custom=_bool(raw.get("isCustom")),
            steps=steps,
        )

    @property
    def is_launch(self) -> bool:
        return self.type == "launch"

    @property
    def is_poweroff(self) -> bool:
        return self.type == "poweroff"


@dataclass(frozen=True, slots=True)
class Room:
    """A NEEO room (typically maps to one HA area).

    Holds nested devices and recipes as returned by
    ``/v1/projects/home/rooms``.
    """

    key: str
    name: str
    devices: tuple[Device, ...] = ()
    recipes: tuple[Recipe, ...] = ()

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Room:
        key = _str(raw.get("key"))
        name = _str(raw.get("name"))

        devices_raw = raw.get("devices") or {}
        if isinstance(devices_raw, dict):
            devices_list = list(devices_raw.values())
        else:
            devices_list = list(devices_raw)
        devices = tuple(
            Device.from_raw(d, room_key=key, room_name=name)
            for d in devices_list
            if isinstance(d, dict)
        )

        recipes_raw = raw.get("recipes") or {}
        if isinstance(recipes_raw, dict):
            recipes_list = list(recipes_raw.values())
        else:
            recipes_list = list(recipes_raw)
        recipes = tuple(
            Recipe.from_raw(r) for r in recipes_list if isinstance(r, dict)
        )

        return cls(key=key, name=name, devices=devices, recipes=recipes)

    def get_device(self, key: str) -> Device | None:
        for d in self.devices:
            if d.key == key:
                return d
        return None

    def find_device_by_name(self, name: str) -> Device | None:
        target = name.lower()
        for d in self.devices:
            if d.name.lower() == target:
                return d
        return None

    def get_recipe(self, key: str) -> Recipe | None:
        for r in self.recipes:
            if r.key == key:
                return r
        return None

    def find_recipe_by_name(self, name: str) -> Recipe | None:
        target = name.lower()
        for r in self.recipes:
            if r.name.lower() == target:
                return r
        return None


@dataclass(frozen=True, slots=True)
class Brain:
    """The Brain's full project tree - the top of the inventory.

    Built from ``GET /v1/projects/home``. Convenience helpers expose
    flat views (``all_recipes``, ``all_devices``) so consumers can
    iterate without traversing room-by-room.
    """

    rooms: tuple[Room, ...] = field(default_factory=tuple)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Brain:
        rooms_raw = raw.get("rooms") or {}
        if isinstance(rooms_raw, dict):
            rooms_list = list(rooms_raw.values())
        else:
            rooms_list = list(rooms_raw)
        rooms = tuple(
            Room.from_raw(r) for r in rooms_list if isinstance(r, dict)
        )
        return cls(rooms=rooms)

    @property
    def all_recipes(self) -> tuple[Recipe, ...]:
        return tuple(r for room in self.rooms for r in room.recipes)

    @property
    def all_devices(self) -> tuple[Device, ...]:
        return tuple(d for room in self.rooms for d in room.devices)

    @property
    def user_rooms(self) -> tuple[Room, ...]:
        """Only rooms the user has actually configured.

        The Brain ships with a fixed catalogue of room names
        (``Kitchen``, ``Bedroom``, ``Bathroom``, ..., ``Outdoor``) and
        returns *all* of them from ``/v1/projects/home``, whether the
        user has assigned anything to them or not. For UI purposes we
        only care about the ones with at least one device or recipe.
        """
        return tuple(r for r in self.rooms if r.devices or r.recipes)

    def get_room(self, key: str) -> Room | None:
        for r in self.rooms:
            if r.key == key:
                return r
        return None

    def find_room_by_name(self, name: str) -> Room | None:
        target = name.lower()
        for r in self.rooms:
            if r.name.lower() == target:
                return r
        return None

    def get_recipe(self, key: str) -> Recipe | None:
        for r in self.all_recipes:
            if r.key == key:
                return r
        return None

    def find_recipe_by_name(self, name: str) -> Recipe | None:
        target = name.lower()
        for r in self.all_recipes:
            if r.name.lower() == target:
                return r
        return None


@dataclass(frozen=True, slots=True)
class SystemInfo:
    """Reduced view of ``GET /systeminfo``."""

    hostname: str = ""
    firmware: str = ""
    hardware: str = ""
    ip_lan: str = ""
    ip_wlan: str = ""
    uptime_seconds: int | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SystemInfo:
        uptime = raw.get("uptime")
        uptime_seconds: int | None
        if isinstance(uptime, (int, float)):
            uptime_seconds = int(uptime)
        else:
            uptime_seconds = None
        # ``hardware`` isn't a single field on the Brain - assemble it
        # from the three hardware* fields the real firmware actually
        # emits, with the older single-key shape as a fallback.
        hardware = _str(raw.get("hardware") or raw.get("hardwareName"))
        if not hardware:
            parts = [
                _str(raw.get("hardwareType")),
                _str(raw.get("hardwareRegion")),
            ]
            rev = raw.get("hardwareRevision")
            if rev is not None:
                parts.append(f"Rev {rev}")
            hardware = " ".join(p for p in parts if p)
        return cls(
            hostname=_str(raw.get("hostname") or raw.get("airkey")),
            firmware=_str(raw.get("firmwareVersion") or raw.get("firmware")),
            hardware=hardware,
            ip_lan=_str(raw.get("lanip") or raw.get("ipLan") or raw.get("ip")),
            ip_wlan=_str(raw.get("wlanip") or raw.get("ipWlan")),
            uptime_seconds=uptime_seconds,
        )
