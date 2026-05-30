"""Tests for ForwardActionsListener.

Real aiohttp server on a random local port, real HTTP roundtrips
in-process. No mocks.
"""

from __future__ import annotations

import asyncio

import aiohttp
import pytest

from pyneeo import (
    ForwardActionEvent,
    ForwardActionsListener,
    MacroEvent,
    RecipeLaunchedEvent,
)


async def _post(url: str, payload: object) -> tuple[int, dict[str, object]]:
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            try:
                body = await response.json()
            except aiohttp.ContentTypeError:
                body = {}
            return response.status, body


class TestLifecycle:
    async def test_start_stop(self) -> None:
        listener = ForwardActionsListener(host="127.0.0.1", port=0)
        await listener.start()
        try:
            assert listener.is_running
            assert listener.port > 0
        finally:
            await listener.stop()
        assert not listener.is_running

    async def test_async_context_manager(self) -> None:
        async with ForwardActionsListener(host="127.0.0.1", port=0) as listener:
            assert listener.is_running
            assert listener.port > 0
        assert not listener.is_running

    async def test_port_before_start_raises(self) -> None:
        listener = ForwardActionsListener(host="127.0.0.1", port=0)
        with pytest.raises(RuntimeError):
            _ = listener.port

    async def test_path_gets_leading_slash(self) -> None:
        listener = ForwardActionsListener(host="127.0.0.1", path="neeo")
        assert listener.path == "/neeo"


class TestDispatch:
    async def test_recipe_launch_dispatched(self) -> None:
        seen: list[ForwardActionEvent] = []

        async def handler(event: ForwardActionEvent) -> None:
            seen.append(event)

        async with ForwardActionsListener(host="127.0.0.1", port=0) as listener:
            listener.add_handler(handler)
            url = f"http://127.0.0.1:{listener.port}{listener.path}"
            status, body = await _post(url, {
                "action": "launch", "device": "TV", "room": "Living", "recipe": "TV",
            })
            assert status == 200
            assert body == {"status": "ok"}

        assert len(seen) == 1
        assert isinstance(seen[0], RecipeLaunchedEvent)
        assert seen[0].recipe == "TV"

    async def test_macro_dispatched(self) -> None:
        seen: list[ForwardActionEvent] = []

        async def handler(event: ForwardActionEvent) -> None:
            seen.append(event)

        async with ForwardActionsListener(host="127.0.0.1", port=0) as listener:
            listener.add_handler(handler)
            url = f"http://127.0.0.1:{listener.port}{listener.path}"
            await _post(url, {
                "action": "VOLUME UP", "device": "AVR", "room": "Living",
            })

        assert len(seen) == 1
        assert isinstance(seen[0], MacroEvent)
        assert seen[0].action == "VOLUME UP"

    async def test_multiple_handlers_all_called(self) -> None:
        a: list[ForwardActionEvent] = []
        b: list[ForwardActionEvent] = []

        async def h_a(ev: ForwardActionEvent) -> None:
            a.append(ev)

        async def h_b(ev: ForwardActionEvent) -> None:
            b.append(ev)

        async with ForwardActionsListener(host="127.0.0.1", port=0) as listener:
            listener.add_handler(h_a)
            listener.add_handler(h_b)
            url = f"http://127.0.0.1:{listener.port}{listener.path}"
            await _post(url, {"action": "launch", "device": "TV", "room": "L", "recipe": "TV"})

        assert len(a) == 1
        assert len(b) == 1

    async def test_failing_handler_does_not_block_others(self) -> None:
        good_seen: list[ForwardActionEvent] = []

        async def bad(ev: ForwardActionEvent) -> None:
            raise RuntimeError("boom")

        async def good(ev: ForwardActionEvent) -> None:
            good_seen.append(ev)

        async with ForwardActionsListener(host="127.0.0.1", port=0) as listener:
            listener.add_handler(bad)
            listener.add_handler(good)
            url = f"http://127.0.0.1:{listener.port}{listener.path}"
            status, _ = await _post(url, {"action": "launch", "device": "TV", "room": "L", "recipe": "TV"})

        assert status == 200
        assert len(good_seen) == 1

    async def test_remove_handler(self) -> None:
        seen: list[ForwardActionEvent] = []

        async def handler(ev: ForwardActionEvent) -> None:
            seen.append(ev)

        async with ForwardActionsListener(host="127.0.0.1", port=0) as listener:
            listener.add_handler(handler)
            listener.remove_handler(handler)
            url = f"http://127.0.0.1:{listener.port}{listener.path}"
            await _post(url, {"action": "launch", "device": "TV", "room": "L", "recipe": "TV"})

        assert seen == []


class TestInvalidPayloads:
    async def test_non_json_returns_400(self) -> None:
        async with ForwardActionsListener(host="127.0.0.1", port=0) as listener:
            url = f"http://127.0.0.1:{listener.port}{listener.path}"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data="not json at all") as response:
                    assert response.status == 400

    async def test_non_object_json_returns_400(self) -> None:
        async with ForwardActionsListener(host="127.0.0.1", port=0) as listener:
            url = f"http://127.0.0.1:{listener.port}{listener.path}"
            status, _ = await _post(url, ["not", "an", "object"])
        assert status == 400


class TestForwardChain:
    async def test_payload_forwarded_to_chain(self) -> None:
        # Spin up a second listener as the chain destination
        chain_seen: list[ForwardActionEvent] = []

        async def chain_handler(ev: ForwardActionEvent) -> None:
            chain_seen.append(ev)

        async with ForwardActionsListener(host="127.0.0.1", port=0) as chain:
            chain.add_handler(chain_handler)
            chain_url = f"http://127.0.0.1:{chain.port}{chain.path}"

            local_seen: list[ForwardActionEvent] = []

            async def local_handler(ev: ForwardActionEvent) -> None:
                local_seen.append(ev)

            async with ForwardActionsListener(
                host="127.0.0.1", port=0, forward_to=[chain_url]
            ) as primary:
                primary.add_handler(local_handler)
                url = f"http://127.0.0.1:{primary.port}{primary.path}"
                await _post(url, {
                    "action": "launch", "device": "TV", "room": "L", "recipe": "TV",
                })
                # Give the forward call a tick to complete
                await asyncio.sleep(0.05)

        assert len(local_seen) == 1
        assert len(chain_seen) == 1
        assert isinstance(chain_seen[0], RecipeLaunchedEvent)

    async def test_dead_forward_target_does_not_break_handlers(self) -> None:
        seen: list[ForwardActionEvent] = []

        async def handler(ev: ForwardActionEvent) -> None:
            seen.append(ev)

        # Port 1 is reserved-ish on most systems - connection will fail
        async with ForwardActionsListener(
            host="127.0.0.1",
            port=0,
            forward_to=["http://127.0.0.1:1/dead"],
            forward_timeout=0.5,
        ) as listener:
            listener.add_handler(handler)
            url = f"http://127.0.0.1:{listener.port}{listener.path}"
            status, _ = await _post(url, {
                "action": "launch", "device": "TV", "room": "L", "recipe": "TV",
            })
        assert status == 200
        assert len(seen) == 1
