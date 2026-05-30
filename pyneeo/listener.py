"""HTTP listener for NEEO Brain forward-action pushes.

The Brain posts JSON to a single registered URL on every action. This
module spins up a small aiohttp web server that accepts those posts,
parses them to typed :class:`~pyneeo.events.ForwardActionEvent`
instances, and dispatches them to user-supplied handlers.

The listener is independent from :class:`~pyneeo.client.NeeoBrainClient`
- you start it first, find out the port it's bound to, and then ask
the client to register that ``(host, port, path)`` with the Brain. On
shutdown, unregister first, then stop the listener.

Multiple handlers can be attached. A *forward chain* of upstream URLs
can be configured so that other consumers (openHAB, ioBroker, ...)
continue receiving the same pushes when only one Brain registration
slot is available.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout, web

from .events import ForwardActionEvent, parse_forward_action

_LOGGER = logging.getLogger(__name__)

EventHandler = Callable[[ForwardActionEvent], Awaitable[None]]

DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PATH = "/neeo-callback"
DEFAULT_FORWARD_TIMEOUT = 5.0


def _bound_port(site: web.TCPSite, *, fallback: int) -> int:
    """Resolve the actually-bound port of a started TCPSite.

    aiohttp does not expose this on a public attribute, but the
    underlying asyncio Server stores its sockets. We narrow on
    :class:`asyncio.Server` so mypy is happy and the access is safe.
    """
    server = site._server
    if isinstance(server, asyncio.Server) and server.sockets:
        port = server.sockets[0].getsockname()[1]
        if isinstance(port, int):
            return port
    return fallback


class ForwardActionsListener:
    """aiohttp web server that receives Brain forward-action pushes.

    Usage::

        listener = ForwardActionsListener(port=0, path="/neeo-callback")
        listener.add_handler(my_async_handler)
        await listener.start()
        # listener.port now holds the actually-bound port
        await client.register_forward_actions(
            host=local_ip, port=listener.port, path=listener.path
        )
        ...
        await client.unregister_forward_actions()
        await listener.stop()
    """

    def __init__(
        self,
        *,
        host: str = DEFAULT_LISTEN_HOST,
        port: int = 0,
        path: str = DEFAULT_LISTEN_PATH,
        forward_to: Sequence[str] = (),
        forward_timeout: float = DEFAULT_FORWARD_TIMEOUT,
    ) -> None:
        if not path.startswith("/"):
            path = "/" + path
        self._host = host
        self._configured_port = port
        self._path = path
        self._forward_to: list[str] = list(forward_to)
        self._forward_timeout = forward_timeout
        self._handlers: list[EventHandler] = []
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._actual_port: int | None = None
        self._forward_session: ClientSession | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def path(self) -> str:
        return self._path

    @property
    def port(self) -> int:
        """The actually-bound port (only valid after :meth:`start`)."""
        if self._actual_port is None:
            raise RuntimeError(
                "Listener is not started yet - call start() first"
            )
        return self._actual_port

    @property
    def is_running(self) -> bool:
        return self._site is not None

    def add_handler(self, handler: EventHandler) -> None:
        """Register an async callback to be invoked on every event."""
        if handler not in self._handlers:
            self._handlers.append(handler)

    def remove_handler(self, handler: EventHandler) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

    def add_forward_target(self, url: str) -> None:
        """Add a URL to the forward chain.

        Useful when another tool already expects forward-actions and
        the Brain only stores one registration slot - we receive,
        relay, and call the chain alongside our own handlers.
        """
        if url not in self._forward_to:
            self._forward_to.append(url)

    def remove_forward_target(self, url: str) -> None:
        if url in self._forward_to:
            self._forward_to.remove(url)

    async def start(self) -> None:
        if self._site is not None:
            return
        app = web.Application()
        app.router.add_post(self._path, self._handle_post)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._configured_port)
        await site.start()
        self._runner = runner
        self._site = site
        self._actual_port = _bound_port(site, fallback=self._configured_port)
        if self._forward_to:
            self._forward_session = ClientSession(
                timeout=ClientTimeout(total=self._forward_timeout)
            )
        _LOGGER.info(
            "[neeo.listener] Listening on http://%s:%s%s (handlers=%d, forward=%d)",
            self._host,
            self._actual_port,
            self._path,
            len(self._handlers),
            len(self._forward_to),
        )

    async def stop(self) -> None:
        if self._site is None:
            return
        await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()
        self._site = None
        self._runner = None
        self._actual_port = None
        if self._forward_session is not None:
            await self._forward_session.close()
            self._forward_session = None

    async def __aenter__(self) -> ForwardActionsListener:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # request handling
    # ------------------------------------------------------------------

    async def _handle_post(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except ValueError:
            _LOGGER.warning("[neeo.listener] Non-JSON POST from %s", request.remote)
            return web.json_response({"error": "invalid json"}, status=400)

        if not isinstance(payload, dict):
            _LOGGER.warning(
                "[neeo.listener] Non-dict payload from %s: %r",
                request.remote,
                payload,
            )
            return web.json_response({"error": "expected object"}, status=400)

        event = parse_forward_action(payload)
        _LOGGER.debug(
            "[neeo.listener] %s event from %s: action=%s device=%s room=%s",
            type(event).__name__,
            request.remote,
            event.action,
            event.device,
            event.room,
        )

        # Dispatch to local handlers and forward chain concurrently.
        # Handler failures are isolated - one broken handler doesn't
        # silence the others or the chain.
        await asyncio.gather(
            self._dispatch_handlers(event),
            self._forward_chain(payload),
        )
        return web.json_response({"status": "ok"})

    async def _dispatch_handlers(self, event: ForwardActionEvent) -> None:
        if not self._handlers:
            return
        results = await asyncio.gather(
            *(h(event) for h in self._handlers),
            return_exceptions=True,
        )
        for handler, result in zip(self._handlers, results, strict=False):
            if isinstance(result, Exception):
                _LOGGER.exception(
                    "[neeo.listener] Handler %r raised", handler, exc_info=result
                )

    async def _forward_chain(self, payload: dict[str, Any]) -> None:
        if not self._forward_to or self._forward_session is None:
            return
        await asyncio.gather(
            *(self._forward_one(url, payload) for url in self._forward_to),
            return_exceptions=True,
        )

    async def _forward_one(self, url: str, payload: dict[str, Any]) -> None:
        assert self._forward_session is not None
        try:
            async with self._forward_session.post(url, json=payload) as response:
                if response.status >= 400:
                    _LOGGER.warning(
                        "[neeo.listener] Forward to %s returned %s",
                        url,
                        response.status,
                    )
        except (ClientError, asyncio.TimeoutError) as exc:
            _LOGGER.warning("[neeo.listener] Forward to %s failed: %s", url, exc)
