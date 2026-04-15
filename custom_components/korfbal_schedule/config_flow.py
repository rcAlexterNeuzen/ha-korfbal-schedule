"""Config flow for Korfbal Schedule integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from . import DOMAIN

CONF_TEAM_CODE = "team_code"
CONF_CLUB_CODE = "club_code"
CONF_TEAM_NAME = "team_name"
CONF_SPORTLINK_CLIENT_ID = "sportlink_client_id"

# Default values extracted from your URL:
# https://mijn.korfbal.nl/team/details/NCX35C2/T1200100098/programma
DEFAULT_CLUB_CODE = "NCX35C2"
DEFAULT_TEAM_CODE = "T1200100098"


class KorfbalScheduleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Korfbal Schedule."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_CLUB_CODE]}_{user_input[CONF_TEAM_CODE]}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input.get(CONF_TEAM_NAME) or user_input[CONF_TEAM_CODE],
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_CLUB_CODE, default=DEFAULT_CLUB_CODE): str,
                vol.Required(CONF_TEAM_CODE, default=DEFAULT_TEAM_CODE): str,
                vol.Optional(CONF_TEAM_NAME, default="Korfbal Team"): str,
                # Optional: Sportlink Club.Dataservice client ID for the official API.
                # Leave blank to use the public scraper fallback.
                vol.Optional(CONF_SPORTLINK_CLIENT_ID, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "url": "https://mijn.korfbal.nl/team/details/NCX35C2/T1200100098/programma"
            },
        )
