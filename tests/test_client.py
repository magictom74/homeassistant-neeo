"""Tests for NeeoBrainClient against a mocked Brain.

Uses respx to intercept httpx calls. No real network traffic.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from pyneeo import (
    NeeoBrainClient,
    NeeoConnectionError,
    NeeoNotFoundError,
    NeeoProtocolError,
    NeeoTimeoutError,
)

BRAIN_HOST = "192.168.40.10"
BASE_URL = f"http://{BRAIN_HOST}:3000"


@pytest.fixture
async def client() -> NeeoBrainClient:
    return NeeoBrainClient(BRAIN_HOST)


class TestSystemInfo:
    @respx.mock
    async def test_returns_typed_systeminfo(self, client: NeeoBrainClient) -> None:
        respx.get(f"{BASE_URL}/systeminfo").mock(
            return_value=httpx.Response(200, json={
                "hostname": "NEEO-x",
                "firmware": "0.53.9",
                "hardware": "EU",
                "ip": "192.168.40.10",
                "uptime": 100,
            })
        )
        info = await client.get_system_info()
        assert info.hostname == "NEEO-x"
        assert info.firmware == "0.53.9"
        assert info.uptime_seconds == 100
        await client.aclose()


class TestGetProject:
    @respx.mock
    async def test_returns_brain_model(self, client: NeeoBrainClient) -> None:
        respx.get(f"{BASE_URL}/v1/projects/home").mock(
            return_value=httpx.Response(200, json={
                "rooms": {
                    "r1": {
                        "key": "r1", "name": "Living",
                        "devices": [{"key": "d1", "name": "TV"}],
                        "recipes": [
                            {"key": "rec1", "type": "launch", "name": "TV", "roomKey": "r1"},
                        ],
                    }
                }
            })
        )
        brain = await client.get_project()
        assert len(brain.rooms) == 1
        assert brain.rooms[0].name == "Living"
        assert len(brain.all_recipes) == 1
        await client.aclose()


class TestGetRecipes:
    @respx.mock
    async def test_list_payload(self, client: NeeoBrainClient) -> None:
        respx.get(f"{BASE_URL}/v1/projects/home/recipes").mock(
            return_value=httpx.Response(200, json=[
                {"key": "k1", "type": "launch", "name": "TV", "roomKey": "r"},
                {"key": "k2", "type": "poweroff", "name": "TV Off", "roomKey": "r"},
            ])
        )
        recipes = await client.get_recipes()
        assert len(recipes) == 2
        assert recipes[0].is_launch
        assert recipes[1].is_poweroff
        await client.aclose()

    @respx.mock
    async def test_dict_payload(self, client: NeeoBrainClient) -> None:
        respx.get(f"{BASE_URL}/v1/projects/home/recipes").mock(
            return_value=httpx.Response(200, json={
                "k1": {"key": "k1", "type": "launch", "name": "TV", "roomKey": "r"},
            })
        )
        recipes = await client.get_recipes()
        assert len(recipes) == 1
        await client.aclose()


class TestExecuteRecipe:
    @respx.mock
    async def test_uses_get_with_correct_path(self, client: NeeoBrainClient) -> None:
        # ioBroker.neeo convention: GET, /rooms/<rk>/recipes/<rk>/execute
        route = respx.get(
            f"{BASE_URL}/v1/projects/home/rooms/r1/recipes/rec1/execute"
        ).mock(return_value=httpx.Response(200))
        await client.execute_recipe("r1", "rec1")
        assert route.called
        assert route.calls[0].request.method == "GET"
        await client.aclose()


class TestTriggerMacro:
    @respx.mock
    async def test_uses_get_with_correct_path(self, client: NeeoBrainClient) -> None:
        route = respx.get(
            f"{BASE_URL}/v1/projects/home/rooms/r1/devices/d1/macros/m1/trigger"
        ).mock(return_value=httpx.Response(200))
        await client.trigger_macro("r1", "d1", "m1")
        assert route.called
        await client.aclose()


class TestForwardActions:
    @respx.mock
    async def test_register(self, client: NeeoBrainClient) -> None:
        route = respx.post(f"{BASE_URL}/v1/forwardactions").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        await client.register_forward_actions("192.168.40.30", 8124, "/api/neeo/x")
        assert route.called
        body = route.calls[0].request.read()
        assert b"192.168.40.30" in body
        assert b"8124" in body
        assert b"/api/neeo/x" in body
        await client.aclose()

    @respx.mock
    async def test_unregister(self, client: NeeoBrainClient) -> None:
        route = respx.post(f"{BASE_URL}/v1/forwardactions").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        await client.unregister_forward_actions()
        # Unregister payload: empty host, port=0
        body = route.calls[0].request.read()
        assert b'"host": ""' in body or b'"host":""' in body
        assert b'"port": 0' in body or b'"port":0' in body
        await client.aclose()

    @respx.mock
    async def test_register_refused_raises(self, client: NeeoBrainClient) -> None:
        respx.post(f"{BASE_URL}/v1/forwardactions").mock(
            return_value=httpx.Response(200, json={"success": False})
        )
        with pytest.raises(NeeoProtocolError):
            await client.register_forward_actions("h", 1, "/p")
        await client.aclose()

    @respx.mock
    async def test_get_registration(self, client: NeeoBrainClient) -> None:
        respx.get(f"{BASE_URL}/v1/forwardactions").mock(
            return_value=httpx.Response(200, json={
                "host": "192.168.40.30", "port": 8999, "path": "/cb",
            })
        )
        reg = await client.get_forward_actions_registration()
        assert reg["host"] == "192.168.40.30"
        await client.aclose()


class TestErrorHandling:
    @respx.mock
    async def test_404_raises_not_found(self, client: NeeoBrainClient) -> None:
        respx.get(f"{BASE_URL}/v1/projects/home").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        with pytest.raises(NeeoNotFoundError):
            await client.get_project()
        await client.aclose()

    @respx.mock
    async def test_5xx_raises_protocol_error(self, client: NeeoBrainClient) -> None:
        respx.get(f"{BASE_URL}/v1/projects/home").mock(
            return_value=httpx.Response(500, text="boom")
        )
        with pytest.raises(NeeoProtocolError):
            await client.get_project()
        await client.aclose()

    @respx.mock
    async def test_timeout_raises_timeout_error(self, client: NeeoBrainClient) -> None:
        respx.get(f"{BASE_URL}/v1/projects/home").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        with pytest.raises(NeeoTimeoutError):
            await client.get_project()
        await client.aclose()

    @respx.mock
    async def test_network_error_raises_connection_error(
        self, client: NeeoBrainClient
    ) -> None:
        respx.get(f"{BASE_URL}/v1/projects/home").mock(
            side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(NeeoConnectionError):
            await client.get_project()
        await client.aclose()


class TestContextManager:
    async def test_aenter_aexit(self) -> None:
        async with NeeoBrainClient(BRAIN_HOST) as client:
            assert client.host == BRAIN_HOST
            assert client.port == 3000
            assert client.base_url == BASE_URL
