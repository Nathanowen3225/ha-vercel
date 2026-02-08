"""Config flow for the Vercel integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VercelApiClient, VercelAuthenticationError, VercelConnectionError
from .const import CONF_TEAM_ID, CONF_TEAM_NAME, DOMAIN


class VercelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vercel."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._token: str = ""
        self._user: dict[str, Any] = {}
        self._teams: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial token input step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._token = user_input["api_token"]
            session = async_get_clientsession(self.hass)
            client = VercelApiClient(token=self._token, session=session)

            try:
                self._user = await client.async_get_user()
                self._teams = await client.async_get_teams()
            except VercelAuthenticationError:
                errors["base"] = "invalid_auth"
            except VercelConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                if self._teams:
                    return await self.async_step_team()

                # No teams - personal account only
                unique_id = f"vercel_{self._user['id']}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Vercel ({self._user['username']})",
                    data={"api_token": self._token},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("api_token"): str}
            ),
            errors=errors,
        )

    async def async_step_team(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle team selection step."""
        if user_input is not None:
            team_id = user_input.get("team", "")

            if team_id:
                # Team selected
                team = next(t for t in self._teams if t["id"] == team_id)
                unique_id = f"vercel_{team_id}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Vercel ({team['name']})",
                    data={
                        "api_token": self._token,
                        CONF_TEAM_ID: team_id,
                        CONF_TEAM_NAME: team["name"],
                    },
                )

            # Personal account selected
            unique_id = f"vercel_{self._user['id']}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Vercel ({self._user['username']})",
                data={"api_token": self._token},
            )

        # Build team selection options
        team_options = {"": f"Personal ({self._user['username']})"}
        for team in self._teams:
            team_options[team["id"]] = team["name"]

        return self.async_show_form(
            step_id="team",
            data_schema=vol.Schema(
                {vol.Required("team"): vol.In(team_options)}
            ),
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth trigger."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth token input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = VercelApiClient(
                token=user_input["api_token"], session=session
            )

            try:
                await client.async_get_user()
            except VercelAuthenticationError:
                errors["base"] = "invalid_auth"
            except VercelConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={"api_token": user_input["api_token"]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required("api_token"): str}
            ),
            errors=errors,
        )
