"""Vercel API client."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import VERCEL_API_BASE


class VercelApiError(Exception):
    """Base exception for Vercel API errors."""


class VercelAuthenticationError(VercelApiError):
    """Raised when authentication fails."""


class VercelConnectionError(VercelApiError):
    """Raised when a connection error occurs."""


class VercelApiClient:
    """Async client for the Vercel REST API."""

    def __init__(
        self,
        token: str,
        session: ClientSession,
        team_id: str | None = None,
    ) -> None:
        """Initialize the client."""
        self._token = token
        self._session = session
        self._team_id = team_id

    def _headers(self) -> dict[str, str]:
        """Return auth headers."""
        return {"Authorization": f"Bearer {self._token}"}

    def _team_params(self) -> dict[str, str]:
        """Return team query params if team_id is set."""
        if self._team_id:
            return {"teamId": self._team_id}
        return {}

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Make an API request."""
        url = f"{VERCEL_API_BASE}{path}"
        merged_params = {**self._team_params(), **(params or {})}
        try:
            async with self._session.request(
                method, url, headers=self._headers(), params=merged_params or None
            ) as resp:
                if resp.status in (401, 403):
                    raise VercelAuthenticationError(
                        f"Authentication failed: {resp.status}"
                    )
                resp.raise_for_status()
                return await resp.json()
        except VercelAuthenticationError:
            raise
        except ClientResponseError as err:
            raise VercelConnectionError(
                f"API error: {err.status} {err.message}"
            ) from err
        except (ClientError, TimeoutError) as err:
            raise VercelConnectionError(
                f"Connection error: {err}"
            ) from err

    async def async_get_user(self) -> dict[str, Any]:
        """Get the authenticated user. Used for token validation."""
        data = await self._request("GET", "/v2/user")
        return data["user"]

    async def async_get_teams(self) -> list[dict[str, Any]]:
        """Get all teams for the authenticated user."""
        data = await self._request("GET", "/v2/teams")
        return data["teams"]

    async def async_get_projects(self) -> list[dict[str, Any]]:
        """Get all projects. Paginates automatically."""
        all_projects: list[dict[str, Any]] = []
        params: dict[str, Any] = {"limit": "100"}
        while True:
            data = await self._request("GET", "/v10/projects", params=params)
            all_projects.extend(data["projects"])
            pagination = data.get("pagination", {})
            next_cursor = pagination.get("next")
            if not next_cursor:
                break
            params["from"] = str(next_cursor)
        return all_projects

    async def async_get_project(self, project_id: str) -> dict[str, Any]:
        """Get a single project by ID."""
        return await self._request("GET", f"/v9/projects/{project_id}")

    async def async_get_deployments(
        self,
        project_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get recent deployments for a project."""
        data = await self._request(
            "GET",
            "/v6/deployments",
            params={"projectId": project_id, "limit": str(limit)},
        )
        return data["deployments"]

    async def async_get_domains(self) -> list[dict[str, Any]]:
        """Get all domains."""
        all_domains: list[dict[str, Any]] = []
        params: dict[str, Any] = {"limit": "100"}
        while True:
            data = await self._request("GET", "/v5/domains", params=params)
            all_domains.extend(data["domains"])
            pagination = data.get("pagination", {})
            next_cursor = pagination.get("next")
            if not next_cursor:
                break
            params["until"] = str(next_cursor)
        return all_domains

    async def async_get_domain_config(self, domain: str) -> dict[str, Any]:
        """Get domain configuration/health."""
        return await self._request("GET", f"/v6/domains/{domain}/config")

    async def async_get_project_env_vars(
        self, project_id: str
    ) -> list[dict[str, Any]]:
        """Get environment variables for a project (keys only, not values)."""
        data = await self._request("GET", f"/v9/projects/{project_id}/env")
        return data["envs"]
