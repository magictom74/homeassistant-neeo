"""mDNS discovery for NEEO Brains.

Brains announce themselves on the local network as ``_neeo._tcp.local.``.
This module provides a single coroutine, :func:`discover_brains`, that
returns a snapshot of currently-visible Brains. It is HA-agnostic - the
HA custom_component layer is responsible for translating discoveries
into a config-flow.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass

from zeroconf import IPVersion, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

_LOGGER = logging.getLogger(__name__)

NEEO_SERVICE_TYPE = "_neeo._tcp.local."
DEFAULT_DISCOVERY_TIMEOUT = 5.0


@dataclass(frozen=True, slots=True)
class DiscoveredBrain:
    """One Brain seen on the local network."""

    name: str
    host: str
    port: int

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


async def discover_brains(
    timeout: float = DEFAULT_DISCOVERY_TIMEOUT,
    *,
    aiozc: AsyncZeroconf | None = None,
) -> tuple[DiscoveredBrain, ...]:
    """Scan the LAN for NEEO Brains.

    Returns whatever was visible during the *timeout* window. Pass an
    existing :class:`AsyncZeroconf` to share with other discovery code
    in the same process; otherwise a temporary one is created and torn
    down on exit.
    """
    own_aiozc = aiozc is None
    aiozc = aiozc or AsyncZeroconf(ip_version=IPVersion.V4Only)
    found: dict[str, DiscoveredBrain] = {}
    pending: set[asyncio.Task[None]] = set()

    def _on_change(
        zc: object,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change is not ServiceStateChange.Added:
            return
        task = asyncio.ensure_future(_resolve(name))
        pending.add(task)
        task.add_done_callback(pending.discard)

    async def _resolve(name: str) -> None:
        info = AsyncServiceInfo(NEEO_SERVICE_TYPE, name)
        if not await info.async_request(aiozc.zeroconf, timeout=2000):
            return
        for addr_bytes in info.addresses or ():
            try:
                host = socket.inet_ntoa(addr_bytes)
            except OSError:
                continue
            label = name.removesuffix(f".{NEEO_SERVICE_TYPE}")
            found[name] = DiscoveredBrain(
                name=label, host=host, port=info.port or 3000
            )
            _LOGGER.info("[neeo.discovery] Found Brain %s at %s:%s", label, host, info.port)
            break

    browser = AsyncServiceBrowser(
        aiozc.zeroconf,
        NEEO_SERVICE_TYPE,
        handlers=[_on_change],
    )
    try:
        await asyncio.sleep(timeout)
    finally:
        await browser.async_cancel()
        if own_aiozc:
            await aiozc.async_close()

    return tuple(found.values())
