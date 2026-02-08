"""DataUpdateCoordinators for the Vercel integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VercelApiClient, VercelAuthenticationError, VercelConnectionError
from .const import (
    DEFAULT_DEPLOYMENT_SCAN_INTERVAL,
    DEFAULT_PROJECT_SCAN_INTERVAL,
    LOGGER,
)


class VercelProjectCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for projects, domains, and env vars."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: VercelApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="vercel_projects",
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_PROJECT_SCAN_INTERVAL),
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch projects, domains, domain configs, and env vars."""
        try:
            raw_projects = await self.client.async_get_projects()
            raw_domains = await self.client.async_get_domains()

            # Index projects by ID
            projects: dict[str, Any] = {}
            for proj in raw_projects:
                projects[proj["id"]] = proj

            # Fetch domain configs and index by domain name
            domains: dict[str, Any] = {}
            for domain in raw_domains:
                name = domain["name"]
                try:
                    config = await self.client.async_get_domain_config(name)
                except VercelConnectionError:
                    config = {"misconfigured": None, "configuredBy": None}
                domains[name] = {**domain, **config}

            # Fetch env vars per project (for best practices audit)
            env_vars: dict[str, list[dict[str, Any]]] = {}
            for project_id in projects:
                try:
                    envs = await self.client.async_get_project_env_vars(project_id)
                except VercelConnectionError:
                    envs = []
                env_vars[project_id] = envs

            return {
                "projects": projects,
                "domains": domains,
                "env_vars": env_vars,
            }
        except VercelAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except VercelConnectionError as err:
            raise UpdateFailed(f"Error fetching Vercel data: {err}") from err


class VercelDeploymentCoordinator(
    DataUpdateCoordinator[dict[str, list[dict[str, Any]]]],
):
    """Coordinator for deployments (higher frequency)."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: VercelApiClient,
        project_coordinator: VercelProjectCoordinator,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="vercel_deployments",
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_DEPLOYMENT_SCAN_INTERVAL),
            always_update=False,
        )
        self.client = client
        self._project_coordinator = project_coordinator

    async def _async_update_data(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch recent deployments for each known project."""
        try:
            project_data = self._project_coordinator.data
            if not project_data:
                return {}

            result: dict[str, list[dict[str, Any]]] = {}
            for project_id in project_data["projects"]:
                try:
                    deployments = await self.client.async_get_deployments(
                        project_id, limit=5
                    )
                except VercelConnectionError:
                    deployments = []
                result[project_id] = deployments

            return result
        except VercelAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except VercelConnectionError as err:
            raise UpdateFailed(f"Error fetching deployments: {err}") from err
