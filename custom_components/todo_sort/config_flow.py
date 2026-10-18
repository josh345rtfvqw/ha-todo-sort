"""Config flow for To-do Sort. Nothing to configure, it just needs adding once."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class TodoSortConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance setup with a confirm step."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title="To-do Sort", data={})
