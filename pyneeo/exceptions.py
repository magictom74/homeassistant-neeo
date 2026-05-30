"""Exceptions raised by pyneeo."""

from __future__ import annotations


class NeeoError(Exception):
    """Base class for all pyneeo errors."""


class NeeoConnectionError(NeeoError):
    """Brain is unreachable or refused the connection."""


class NeeoTimeoutError(NeeoError):
    """A request to the Brain timed out."""


class NeeoNotFoundError(NeeoError):
    """The requested resource (recipe, room, device, macro) does not exist."""


class NeeoProtocolError(NeeoError):
    """The Brain returned an unexpected response shape."""
