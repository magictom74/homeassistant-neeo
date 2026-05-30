"""Config flow for the NEEO Smart Remote integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from pyneeo import (
    DEFAULT_PORT,
    NeeoBrainClient,
    NeeoConnectionError,
    NeeoTimeoutError,
)

from .const import (
    CONF_DEFAULT_RECIPE_KEY,
    CONF_IN_GLOBAL_TOGGLE,
    CONF_ROOMS,
    DOMAIN,
)
from .const import DEFAULT_PORT as INTEGRATION_DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=INTEGRATION_DEFAULT_PORT): cv.port,
    }
)


class NeeoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Brain config flow.

    Two entry points:

    * **User flow** - manual host/port entry. Verified by calling
      ``GET /systeminfo`` on the Brain.
    * **Zeroconf flow** - automatic discovery on the LAN via the
      ``_neeo._tcp.local.`` service type. Pre-fills host and port.
    """

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> NeeoOptionsFlow:
        return NeeoOptionsFlow(entry)

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT
        self._discovered_name: str | None = None

    # ------------------------------------------------------------------
    # user flow
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, INTEGRATION_DEFAULT_PORT)
            unique_id = await self._probe(host, port, errors)
            if unique_id is not None:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=self._discovered_name or f"NEEO Brain ({host})",
                    data={CONF_HOST: host, CONF_PORT: port},
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    # ------------------------------------------------------------------
    # zeroconf flow
    # ------------------------------------------------------------------

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        host = discovery_info.host
        port = discovery_info.port or DEFAULT_PORT
        name = discovery_info.name.removesuffix("._neeo._tcp.local.")

        self._discovered_host = host
        self._discovered_port = port
        self._discovered_name = name

        # Probe once to confirm this is a reachable Brain (and to grab
        # a stable unique_id from the systeminfo).
        unique_id = await self._probe(host, port, errors={})
        if unique_id is None:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})

        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered_name or "NEEO Brain",
                data={
                    CONF_HOST: self._discovered_host,
                    CONF_PORT: self._discovered_port,
                },
            )
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovered_name or "NEEO Brain",
                "host": self._discovered_host or "",
            },
        )

    # ------------------------------------------------------------------
    # shared probe
    # ------------------------------------------------------------------

    async def _probe(
        self, host: str, port: int, errors: dict[str, str]
    ) -> str | None:
        """Hit ``/systeminfo`` and return a stable unique_id, or None on failure."""
        client = NeeoBrainClient(host, port=port)
        try:
            info = await client.get_system_info()
        except (NeeoConnectionError, NeeoTimeoutError) as exc:
            _LOGGER.debug("[neeo.config_flow] Probe of %s:%s failed: %s", host, port, exc)
            errors["base"] = "cannot_connect"
            return None
        except Exception:
            _LOGGER.exception("[neeo.config_flow] Unexpected probe failure")
            errors["base"] = "unknown"
            return None
        finally:
            await client.aclose()

        # Use hostname (NEEO-XXXXXXXX) as the stable unique_id - it
        # survives IP changes and is the only Brain-side stable
        # identifier we have without an auth token.
        if info.hostname:
            self._discovered_name = info.hostname
            return info.hostname

        # Fallback: use host:port. Less ideal across DHCP changes.
        return f"{host}:{port}"


class NeeoOptionsFlow(OptionsFlow):
    """Per-room default recipe + global-on opt-in.

    The form is built dynamically from the Brain's inventory so that
    each room only offers its own launch-typed, non-hidden recipes
    in the dropdown. Stored shape::

        options = {
          "rooms": {
            "<room_key>": {
              "default_recipe_key": "<recipe_key>",  # empty = no default
              "in_global_toggle": True/False,
            }
          }
        }
    """

    def __init__(self, entry: ConfigEntry) -> None:
        self.config_entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        brain = coordinator.data
        if brain is None:
            return self.async_abort(reason="brain_not_ready")

        user_rooms = brain.user_rooms

        if user_input is not None:
            rooms_options: dict[str, dict[str, Any]] = {}
            for room in user_rooms:
                rooms_options[room.key] = {
                    CONF_DEFAULT_RECIPE_KEY: user_input.get(
                        f"default_{room.key}", ""
                    ),
                    CONF_IN_GLOBAL_TOGGLE: bool(
                        user_input.get(f"global_{room.key}", False)
                    ),
                }
            return self.async_create_entry(
                title="", data={CONF_ROOMS: rooms_options}
            )

        current = self.config_entry.options.get(CONF_ROOMS, {})
        if not isinstance(current, dict):
            current = {}

        schema_dict: dict[Any, Any] = {}
        for room in user_rooms:
            current_room = current.get(room.key, {}) if isinstance(current, dict) else {}
            current_default = (
                current_room.get(CONF_DEFAULT_RECIPE_KEY, "")
                if isinstance(current_room, dict)
                else ""
            )
            current_in_global = bool(
                current_room.get(CONF_IN_GLOBAL_TOGGLE, False)
                if isinstance(current_room, dict)
                else False
            )

            recipe_choices: list[SelectOptionDict] = [
                SelectOptionDict(value="", label="(none)"),
            ]
            for r in room.recipes:
                if r.is_launch and not r.is_hidden:
                    recipe_choices.append(
                        SelectOptionDict(value=r.key, label=r.name)
                    )

            schema_dict[
                vol.Optional(f"default_{room.key}", default=current_default)
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=recipe_choices,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
            schema_dict[
                vol.Optional(f"global_{room.key}", default=current_in_global)
            ] = BooleanSelector()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "room_count": str(len(user_rooms)),
            },
        )
