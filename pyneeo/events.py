"""Typed Forward-Action events pushed by the NEEO Brain.

The Brain calls a registered URL (POST, JSON body) on every action -
recipe launch/poweroff, macro press, button on the Remote. Payload
shapes verified empirically against firmware 0.53.9 (April 2018):

Recipe launch::

    {"action": "launch", "device": "TV", "room": "Living", "recipe": "TV"}

Recipe poweroff::

    {"action": "poweroff", "device": "AV Receiver", "room": "Living",
     "recipe": "FM Radio"}

Macro / Remote-button press::

    {"action": "VOLUME UP", "device": "AV Receiver", "room": "Living"}
    {"action": "CHANNEL_01", "device": "FM Radio", "room": "Living"}

The factory function :func:`parse_forward_action` dispatches on
``action`` and returns a typed dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _str(raw: Any, default: str = "") -> str:
    if raw is None:
        return default
    if isinstance(raw, str):
        return raw
    return str(raw)


@dataclass(frozen=True, slots=True)
class ForwardActionEvent:
    """Base for all Brain forward-action pushes.

    ``raw`` retains the original payload so consumers can inspect
    Brain-version-specific fields we don't yet model.
    """

    action: str
    device: str
    room: str
    received_at: datetime = field(default_factory=_utc_now)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecipeLaunchedEvent(ForwardActionEvent):
    """A recipe was started (``action == "launch"``).

    ``recipe`` is the activity name, e.g. ``"TV"`` or ``"FM Radio"``.
    The Brain pushes one of these whether the launch came from the
    NEEO Remote, the NEEO app, the EUI, or our own API call.
    """

    recipe: str = ""


@dataclass(frozen=True, slots=True)
class RecipePoweroffEvent(ForwardActionEvent):
    """A recipe was powered off (``action == "poweroff"``)."""

    recipe: str = ""


@dataclass(frozen=True, slots=True)
class MacroEvent(ForwardActionEvent):
    """A device-level macro fired (volume, channel, cursor, custom).

    ``action`` carries the macro name in upper-case
    (``"VOLUME UP"``, ``"CURSOR ENTER"``, ``"CHANNEL_01"``). No
    ``recipe`` field. Holding a key on the Remote produces several of
    these per second - consumers should debounce if needed.
    """


def parse_forward_action(payload: dict[str, Any]) -> ForwardActionEvent:
    """Dispatch a forward-action payload to a typed event.

    Unknown ``action`` values (anything other than ``launch`` or
    ``poweroff``) are treated as macros, since that's what the Brain
    does in practice - any non-recipe push has the macro name in
    ``action``. Missing/non-dict input falls back to a generic
    :class:`ForwardActionEvent` with empty fields rather than raising.
    """
    if not isinstance(payload, dict):
        return ForwardActionEvent(action="", device="", room="", raw={})

    action = _str(payload.get("action"))
    device = _str(payload.get("device"))
    room = _str(payload.get("room"))
    recipe = _str(payload.get("recipe"))

    if action == "launch":
        return RecipeLaunchedEvent(
            action=action,
            device=device,
            room=room,
            recipe=recipe,
            raw=payload,
        )
    if action == "poweroff":
        return RecipePoweroffEvent(
            action=action,
            device=device,
            room=room,
            recipe=recipe,
            raw=payload,
        )
    return MacroEvent(action=action, device=device, room=room, raw=payload)
