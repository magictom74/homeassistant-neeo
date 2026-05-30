"""Unit tests for the pyneeo dataclass models."""

from __future__ import annotations

import pytest

from pyneeo import Brain, Device, Macro, Recipe, RecipeStep, Room, SystemInfo


def make_macro(key: str = "m1", name: str = "POWER ON") -> Macro:
    return Macro.from_raw({"key": key, "name": name, "label": name.title()})


class TestMacro:
    def test_from_raw_full(self) -> None:
        m = make_macro()
        assert m.key == "m1"
        assert m.name == "POWER ON"
        assert m.label == "Power On"

    def test_label_defaults_to_name(self) -> None:
        m = Macro.from_raw({"key": "k", "name": "VOLUME UP"})
        assert m.label == "VOLUME UP"

    def test_stringifies_int_key(self) -> None:
        # NEEO Brain returns large int keys in some endpoints
        m = Macro.from_raw({"key": 6332958388544077824, "name": "X"})
        assert m.key == "6332958388544077824"
        assert isinstance(m.key, str)


class TestDevice:
    def test_from_raw_with_macros(self) -> None:
        d = Device.from_raw({
            "key": "d1",
            "name": "AV Receiver",
            "roomKey": "r1",
            "roomName": "Living",
            "manufacturer": "Denon",
            "model": "AVR-4520",
            "type": "AVRECEIVER",
            "macros": [
                {"key": "m1", "name": "POWER ON"},
                {"key": "m2", "name": "VOLUME UP"},
            ],
        })
        assert d.key == "d1"
        assert d.name == "AV Receiver"
        assert d.manufacturer == "Denon"
        assert d.model == "AVR-4520"
        assert d.device_type == "AVRECEIVER"
        assert len(d.macros) == 2
        assert d.macros[0].name == "POWER ON"

    def test_get_macro_lookup(self) -> None:
        d = Device.from_raw({
            "key": "d", "name": "X", "roomKey": "r",
            "macros": [{"key": "m1", "name": "VOLUME UP"}],
        })
        assert d.get_macro("m1") is not None
        assert d.get_macro("nope") is None

    def test_find_macro_by_name_case_insensitive(self) -> None:
        d = Device.from_raw({
            "key": "d", "name": "X", "roomKey": "r",
            "macros": [{"key": "m1", "name": "VOLUME UP"}],
        })
        m = d.find_macro_by_name("volume up")
        assert m is not None
        assert m.key == "m1"

    def test_room_key_fallback_to_kwarg(self) -> None:
        # roomKey missing from raw, comes from enclosing context
        d = Device.from_raw({"key": "d", "name": "X"}, room_key="r99", room_name="Kitchen")
        assert d.room_key == "r99"
        assert d.room_name == "Kitchen"

    def test_devicetype_alias(self) -> None:
        # Some endpoints use "devicetype" instead of "type"
        d = Device.from_raw({"key": "d", "name": "X", "roomKey": "r", "devicetype": "DVD"})
        assert d.device_type == "DVD"

    def test_details_subobject_real_brain_shape(self) -> None:
        # Captured shape from a real Brain (firmware 0.53.9):
        # manufacturer/type/model live under a `details` sub-object,
        # the top-level `name` is the user-given device name.
        d = Device.from_raw({
            "key": "6332958388544077824",
            "name": "AV Receiver",
            "roomKey": "r1",
            "roomName": "Living",
            "details": {
                "manufacturer": "Denon",
                "type": "AVRECEIVER",
                "name": "AVR-4520 AVR",
                "adapterName": "avreceiver",
            },
        })
        assert d.name == "AV Receiver"
        assert d.manufacturer == "Denon"
        assert d.device_type == "AVRECEIVER"
        assert d.model == "AVR-4520 AVR"

    def test_details_does_not_override_top_level(self) -> None:
        # Top-level fields win over details (convenience endpoint case).
        d = Device.from_raw({
            "key": "d", "name": "X", "roomKey": "r",
            "manufacturer": "TopLevel",
            "details": {"manufacturer": "Nested"},
        })
        assert d.manufacturer == "TopLevel"

    def test_macros_as_dict_payload(self) -> None:
        # Some responses use a dict-of-macros instead of a list
        d = Device.from_raw({
            "key": "d", "name": "X", "roomKey": "r",
            "macros": {"m1": {"key": "m1", "name": "VOLUME UP"}},
        })
        assert len(d.macros) == 1
        assert d.macros[0].name == "VOLUME UP"


class TestRecipe:
    def test_launch_recipe(self) -> None:
        r = Recipe.from_raw({
            "key": "6332958412279644160",
            "type": "launch",
            "name": "AV Receiver",
            "roomKey": "6232364701641080832",
            "roomName": "Living",
            "scenarioKey": "6332958412103483392",
            "mainDeviceType": "AVRECEIVER",
            "isHiddenRecipe": True,
            "isCustom": False,
            "enabled": False,
            "steps": [
                {
                    "type": "action",
                    "label": "Send POWER ON",
                    "deviceKey": "d1",
                    "deviceName": "AV Receiver",
                    "componentName": "POWER ON",
                },
                {"type": "delay", "label": "Wait", "delay": 5000},
            ],
        })
        assert r.is_launch
        assert not r.is_poweroff
        assert r.name == "AV Receiver"
        assert r.is_hidden
        assert not r.enabled
        assert len(r.steps) == 2
        assert r.steps[0].type == "action"
        assert r.steps[0].component_name == "POWER ON"
        assert r.steps[1].type == "delay"
        assert r.steps[1].delay_ms == 5000

    def test_poweroff_recipe(self) -> None:
        r = Recipe.from_raw({
            "key": "k", "type": "poweroff", "name": "TV Off", "roomKey": "r",
        })
        assert r.is_poweroff
        assert not r.is_launch

    def test_enabled_defaults_true(self) -> None:
        r = Recipe.from_raw({"key": "k", "type": "launch", "name": "X", "roomKey": "r"})
        assert r.enabled

    def test_step_without_delay(self) -> None:
        s = RecipeStep.from_raw({"type": "action", "label": "x"})
        assert s.delay_ms is None


class TestRoom:
    def test_full_room(self) -> None:
        r = Room.from_raw({
            "key": "r1", "name": "Living",
            "devices": [
                {"key": "d1", "name": "AV Receiver"},
                {"key": "d2", "name": "TV"},
            ],
            "recipes": [
                {"key": "rec1", "type": "launch", "name": "Watch TV"},
            ],
        })
        assert r.name == "Living"
        assert len(r.devices) == 2
        # Room context propagates to devices
        assert r.devices[0].room_key == "r1"
        assert r.devices[0].room_name == "Living"
        assert len(r.recipes) == 1

    def test_get_device(self) -> None:
        r = Room.from_raw({
            "key": "r", "name": "X",
            "devices": [{"key": "d1", "name": "AV"}],
        })
        assert r.get_device("d1") is not None
        assert r.get_device("nope") is None
        assert r.find_device_by_name("av") is not None

    def test_get_recipe(self) -> None:
        r = Room.from_raw({
            "key": "r", "name": "X",
            "recipes": [{"key": "rec1", "type": "launch", "name": "TV"}],
        })
        assert r.get_recipe("rec1") is not None
        assert r.find_recipe_by_name("tv") is not None
        assert r.find_recipe_by_name("nope") is None

    def test_devices_as_dict(self) -> None:
        r = Room.from_raw({
            "key": "r", "name": "X",
            "devices": {"d1": {"key": "d1", "name": "TV"}},
        })
        assert len(r.devices) == 1


class TestBrain:
    def test_full_brain(self) -> None:
        b = Brain.from_raw({
            "rooms": {
                "r1": {
                    "key": "r1", "name": "Living",
                    "devices": [{"key": "d1", "name": "TV"}],
                    "recipes": [
                        {"key": "rec1", "type": "launch", "name": "Watch TV", "roomKey": "r1"},
                    ],
                },
                "r2": {
                    "key": "r2", "name": "Bedroom",
                    "recipes": [
                        {"key": "rec2", "type": "launch", "name": "Sleep", "roomKey": "r2"},
                    ],
                },
            },
        })
        assert len(b.rooms) == 2
        assert len(b.all_recipes) == 2
        assert b.get_room("r1") is not None
        assert b.find_room_by_name("living") is not None
        assert b.get_recipe("rec2") is not None
        assert b.find_recipe_by_name("watch tv") is not None

    def test_empty_brain(self) -> None:
        b = Brain.from_raw({})
        assert b.rooms == ()
        assert b.all_recipes == ()
        assert b.all_devices == ()

    def test_user_rooms_filters_out_empties(self) -> None:
        # Brain ships with a default catalogue (Kitchen, Outdoor, ...)
        # that the user often doesn't populate. user_rooms drops those.
        b = Brain.from_raw({
            "rooms": [
                {"key": "r1", "name": "Living", "devices": [{"key": "d1", "name": "TV"}]},
                {"key": "r2", "name": "Kitchen"},  # empty default room
                {"key": "r3", "name": "Bedroom",
                 "recipes": [{"key": "rec", "type": "launch", "name": "Sleep", "roomKey": "r3"}]},
                {"key": "r4", "name": "Outdoor"},  # empty default room
            ],
        })
        assert len(b.rooms) == 4
        user = b.user_rooms
        assert len(user) == 2
        assert {r.name for r in user} == {"Living", "Bedroom"}


class TestSystemInfo:
    def test_parses_full(self) -> None:
        info = SystemInfo.from_raw({
            "hostname": "NEEO-abc12345",
            "firmware": "0.53.9-20180424",
            "hardware": "NEEO Region EU",
            "ip": "192.168.40.10",
            "uptime": 15466456,
        })
        assert info.hostname == "NEEO-abc12345"
        assert info.firmware.startswith("0.53.9")
        assert info.ip_lan == "192.168.40.10"
        assert info.uptime_seconds == 15466456

    def test_uptime_missing(self) -> None:
        info = SystemInfo.from_raw({"hostname": "x"})
        assert info.uptime_seconds is None

    def test_real_brain_shape(self) -> None:
        # Captured from a real Brain (firmware 0.53.9). Hardware is
        # assembled from hardwareType/Region/Revision; IPs come from
        # lanip/wlanip rather than ipLan/ipWlan.
        info = SystemInfo.from_raw({
            "hostname": "NEEO-abc12345",
            "firmwareVersion": "0.53.9-20180424-02ae61b",
            "hardwareType": "NEEO",
            "hardwareRegion": "EU",
            "hardwareRevision": 5,
            "lanip": "192.168.1.10",
            "wlanip": "192.168.1.11",
            "uptime": 16556701,
        })
        assert info.hostname == "NEEO-abc12345"
        assert info.firmware.startswith("0.53.9")
        assert "NEEO" in info.hardware
        assert "EU" in info.hardware
        assert "Rev 5" in info.hardware
        assert info.ip_lan == "192.168.1.10"
        assert info.ip_wlan == "192.168.1.11"
        assert info.uptime_seconds == 16556701


class TestImmutability:
    def test_recipe_frozen(self) -> None:
        r = Recipe.from_raw({"key": "k", "type": "launch", "name": "X", "roomKey": "r"})
        with pytest.raises(Exception):
            r.name = "other"  # type: ignore[misc]

    def test_room_frozen(self) -> None:
        r = Room.from_raw({"key": "r", "name": "X"})
        with pytest.raises(Exception):
            r.name = "other"  # type: ignore[misc]
