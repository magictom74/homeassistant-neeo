"""Unit tests for forward-action event parsing.

All payloads here are real - captured from a NEEO Brain firmware
0.53.9 during the 2026-05-17 discovery run.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pyneeo import (
    ForwardActionEvent,
    MacroEvent,
    RecipeLaunchedEvent,
    RecipePoweroffEvent,
    parse_forward_action,
)


class TestParseForwardAction:
    def test_launch(self) -> None:
        ev = parse_forward_action({
            "action": "launch",
            "device": "TV",
            "room": "Living",
            "recipe": "TV",
        })
        assert isinstance(ev, RecipeLaunchedEvent)
        assert ev.action == "launch"
        assert ev.device == "TV"
        assert ev.room == "Living"
        assert ev.recipe == "TV"

    def test_poweroff(self) -> None:
        ev = parse_forward_action({
            "action": "poweroff",
            "device": "AV Receiver",
            "room": "Living",
            "recipe": "FM Radio",
        })
        assert isinstance(ev, RecipePoweroffEvent)
        assert ev.recipe == "FM Radio"

    def test_macro_volume_up(self) -> None:
        ev = parse_forward_action({
            "action": "VOLUME UP",
            "device": "AV Receiver",
            "room": "Living",
        })
        assert isinstance(ev, MacroEvent)
        assert ev.action == "VOLUME UP"
        # No recipe field on the dataclass - this is what distinguishes
        # MacroEvent from Recipe events
        assert not hasattr(ev, "recipe")

    def test_macro_channel_button(self) -> None:
        ev = parse_forward_action({
            "action": "CHANNEL_01",
            "device": "FM Radio",
            "room": "Living",
        })
        assert isinstance(ev, MacroEvent)
        assert ev.action == "CHANNEL_01"

    def test_received_at_is_utc_now(self) -> None:
        before = datetime.now(timezone.utc)
        ev = parse_forward_action({"action": "launch", "device": "TV", "room": "L", "recipe": "TV"})
        after = datetime.now(timezone.utc)
        assert before <= ev.received_at <= after

    def test_raw_preserved(self) -> None:
        payload = {
            "action": "VOLUME UP",
            "device": "AVR",
            "room": "Living",
            "unknown_future_field": "preserved",
        }
        ev = parse_forward_action(payload)
        assert ev.raw["unknown_future_field"] == "preserved"

    def test_non_dict_payload_falls_back(self) -> None:
        ev = parse_forward_action(None)  # type: ignore[arg-type]
        assert type(ev) is ForwardActionEvent
        assert ev.action == ""

    def test_empty_payload(self) -> None:
        ev = parse_forward_action({})
        # Unknown action -> macro by convention
        assert isinstance(ev, MacroEvent)
        assert ev.action == ""
