"""DataUpdateCoordinators for the Vercel integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    VercelApiClient,
    VercelAuthenticationError,
    VercelConnectionError,
    VercelRateLimitError,
)
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

            # Fetch domain configs in parallel
            async def _fetch_domain(
                domain: dict[str, Any],
            ) -> tuple[str, dict[str, Any]]:
                name = domain["name"]
                try:
                    config = await self.client.async_get_domain_config(name)
                except (VercelConnectionError, VercelRateLimitError):
                    config = {"misconfigured": None, "configuredBy": None}
                return name, {**domain, **config}

            domain_results = await asyncio.gather(
                *(_fetch_domain(d) for d in raw_domains)
            )
            domains = dict(domain_results)

            # Fetch env vars per project in parallel
            async def _fetch_env_vars(
                project_id: str,
            ) -> tuple[str, list[dict[str, Any]]]:
                try:
                    envs = await self.client.async_get_project_env_vars(project_id)
                except (VercelConnectionError, VercelRateLimitError):
                    envs = []
                return project_id, envs

            env_results = await asyncio.gather(
                *(_fetch_env_vars(pid) for pid in projects)
            )
            env_vars = dict(env_results)

            return {
                "projects": projects,
                "domains": domains,
                "env_vars": env_vars,
            }
        except VercelAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except (VercelConnectionError, VercelRateLimitError) as err:
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

            async def _fetch_deployments(
                project_id: str,
            ) -> tuple[str, list[dict[str, Any]]]:
                try:
                    deployments = await self.client.async_get_deployments(
                        project_id, limit=5
                    )
                except (VercelConnectionError, VercelRateLimitError):
                    deployments = []
                return project_id, deployments

            results = await asyncio.gather(
                *(_fetch_deployments(pid) for pid in project_data["projects"])
            )
            return dict(results)
        except VercelAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except (VercelConnectionError, VercelRateLimitError) as err:
            raise UpdateFailed(f"Error fetching deployments: {err}") from err
