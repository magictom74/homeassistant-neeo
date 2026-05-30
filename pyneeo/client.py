"""Async HTTP client for the NEEO Brain REST API.

Auth-less - the Brain has no auth layer on the LAN. All endpoints
verified against firmware 0.53.9 (Brain 192.168.40.10) on 2026-05-17;
see ``docs/NEEO_API_NOTES.md`` for the protocol reference.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

import httpx

from .exceptions import (
    NeeoConnectionError,
    NeeoNotFoundError,
    NeeoProtocolError,
    NeeoTimeoutError,
)
from .models import Brain, Recipe, SystemInfo

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 3000
DEFAULT_TIMEOUT = 10.0


class NeeoBrainClient:
    """Async HTTP client for one NEEO Brain.

    Usage::

        async with NeeoBrainClient("192.168.40.10") as client:
            info = await client.get_system_info()
            brain = await client.get_project()
            await client.execute_recipe(room_key, recipe_key)

    The client does no caching; callers that want a snapshot of the
    Brain's state should call :meth:`get_project` once and hold onto
    the :class:`~pyneeo.models.Brain` instance.
    """

    def __init__(
        self,
        host: str,
        *,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._base_url = f"http://{host}:{port}"
        self._timeout = timeout
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout)

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        return self._base_url

    async def __aenter__(self) -> NeeoBrainClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    # ------------------------------------------------------------------
    # low-level transport
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        _LOGGER.debug("[neeo.client] %s %s body=%s", method, url, json_body)
        try:
            response = await self._http.request(method, url, json=json_body)
        except httpx.TimeoutException as exc:
            raise NeeoTimeoutError(f"Timeout calling {method} {url}") from exc
        except httpx.HTTPError as exc:
            raise NeeoConnectionError(
                f"Connection error calling {method} {url}: {exc}"
            ) from exc

        if response.status_code == 404:
            raise NeeoNotFoundError(f"{method} {url} returned 404")
        if response.status_code >= 400:
            raise NeeoProtocolError(
                f"{method} {url} returned {response.status_code}: {response.text!r}"
            )

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise NeeoProtocolError(
                f"{method} {url} returned non-JSON: {response.text!r}"
            ) from exc

    # ------------------------------------------------------------------
    # read endpoints
    # ------------------------------------------------------------------

    async def get_system_info(self) -> SystemInfo:
        """``GET /systeminfo`` - Brain hardware / firmware metadata."""
        raw = await self._request("GET", "/systeminfo")
        if not isinstance(raw, dict):
            raise NeeoProtocolError(f"/systeminfo returned non-dict: {raw!r}")
        return SystemInfo.from_raw(raw)

    async def get_project(self) -> Brain:
        """``GET /v1/projects/home`` - the full Brain inventory.

        Single round-trip that returns rooms + nested devices + recipes.
        Use this for initial-fetch; afterwards subscribe to forward
        actions instead of re-polling.
        """
        raw = await self._request("GET", "/v1/projects/home")
        if not isinstance(raw, dict):
            raise NeeoProtocolError(
                f"/v1/projects/home returned non-dict: {raw!r}"
            )
        return Brain.from_raw(raw)

    async def get_recipes(self) -> tuple[Recipe, ...]:
        """``GET /v1/projects/home/recipes`` - flat list of all recipes."""
        raw = await self._request("GET", "/v1/projects/home/recipes")
        if isinstance(raw, dict):
            raw_list = list(raw.values())
        elif isinstance(raw, list):
            raw_list = raw
        else:
            raise NeeoProtocolError(
                f"/v1/projects/home/recipes returned non-iterable: {raw!r}"
            )
        return tuple(
            Recipe.from_raw(r) for r in raw_list if isinstance(r, dict)
        )

    # ------------------------------------------------------------------
    # trigger endpoints (GET, per ioBroker.neeo convention)
    # ------------------------------------------------------------------

    async def execute_recipe(self, room_key: str, recipe_key: str) -> None:
        """Trigger a recipe.

        Endpoint:
        ``GET /v1/projects/home/rooms/<room_key>/recipes/<recipe_key>/execute``

        Whether this launches or powers off depends on the recipe's
        own ``type`` field - the Brain figures that out, the URL is
        the same. We don't return the Brain's response body because
        in practice it's an empty 200.
        """
        path = (
            f"/v1/projects/home/rooms/{room_key}"
            f"/recipes/{recipe_key}/execute"
        )
        await self._request("GET", path)

    async def trigger_macro(
        self, room_key: str, device_key: str, macro_key: str
    ) -> None:
        """Fire a device-level macro (e.g. ``POWER ON``, ``VOLUME UP``).

        Endpoint:
        ``GET /v1/projects/home/rooms/<room_key>/devices/<device_key>/macros/<macro_key>/trigger``
        """
        path = (
            f"/v1/projects/home/rooms/{room_key}"
            f"/devices/{device_key}/macros/{macro_key}/trigger"
        )
        await self._request("GET", path)

    # ------------------------------------------------------------------
    # forward-actions registration
    # ------------------------------------------------------------------

    async def register_forward_actions(
        self, host: str, port: int, path: str = "/"
    ) -> None:
        """Register *our* HTTP endpoint as the Brain's forward-actions sink.

        The Brain stores **one** registration at a time - any new POST
        overwrites the previous one. After registration the Brain will
        POST to ``http://<host>:<port><path>`` on every action.

        See :meth:`unregister_forward_actions` for the (peculiar)
        unregister mechanism - the Brain has no DELETE verb here.
        """
        body = {"host": host, "port": port, "path": path}
        result = await self._request("POST", "/v1/forwardactions", json_body=body)
        if isinstance(result, dict) and result.get("success") is False:
            raise NeeoProtocolError(
                f"Brain refused forward-actions registration: {result!r}"
            )

    async def unregister_forward_actions(self) -> None:
        """Clear the Brain's forward-actions registration.

        The Brain does not support ``DELETE /v1/forwardactions`` (404).
        The empirically-confirmed unregister path is a POST with
        empty host/port/path - this disables push without changing the
        endpoint URL.
        """
        await self._request(
            "POST",
            "/v1/forwardactions",
            json_body={"host": "", "port": 0, "path": ""},
        )

    async def get_forward_actions_registration(self) -> dict[str, Any]:
        """Read the Brain's current forward-actions registration."""
        raw = await self._request("GET", "/v1/forwardactions")
        if not isinstance(raw, dict):
            raise NeeoProtocolError(
                f"/v1/forwardactions returned non-dict: {raw!r}"
            )
        return raw
