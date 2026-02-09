"""Tests for the Vercel API client."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.vercel.api import (
    VercelApiClient,
    VercelAuthenticationError,
    VercelConnectionError,
    VercelRateLimitError,
)


async def test_get_user(hass: HomeAssistant, aioclient_mock) -> None:
    """Test fetching the authenticated user."""
    aioclient_mock.get(
        "https://api.vercel.com/v2/user",
        json={
            "user": {
                "id": "user_abc123",
                "email": "test@example.com",
                "username": "testuser",
                "name": "Test User",
            }
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    user = await client.async_get_user()
    assert user["id"] == "user_abc123"
    assert user["username"] == "testuser"


async def test_get_user_auth_failure(hass: HomeAssistant, aioclient_mock) -> None:
    """Test that 403 raises VercelAuthenticationError."""
    aioclient_mock.get(
        "https://api.vercel.com/v2/user",
        status=403,
        json={"error": {"code": "forbidden", "message": "Forbidden"}},
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="bad_token", session=session)
    with pytest.raises(VercelAuthenticationError):
        await client.async_get_user()


async def test_get_teams(hass: HomeAssistant, aioclient_mock) -> None:
    """Test fetching teams."""
    aioclient_mock.get(
        "https://api.vercel.com/v2/teams",
        json={
            "teams": [
                {
                    "id": "team_abc",
                    "slug": "my-team",
                    "name": "My Team",
                }
            ],
            "pagination": {
                "count": 1,
                "next": None,
                "prev": None,
            },
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    teams = await client.async_get_teams()
    assert len(teams) == 1
    assert teams[0]["slug"] == "my-team"


async def test_get_projects(hass: HomeAssistant, aioclient_mock) -> None:
    """Test fetching projects."""
    aioclient_mock.get(
        "https://api.vercel.com/v10/projects",
        json={
            "projects": [
                {
                    "id": "prj_123",
                    "name": "my-app",
                    "framework": "nextjs",
                    "nodeVersion": "20.x",
                    "updatedAt": 1700000000000,
                }
            ],
            "pagination": {"count": 1, "next": None},
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    projects = await client.async_get_projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "my-app"


async def test_get_projects_with_team(hass: HomeAssistant, aioclient_mock) -> None:
    """Test fetching projects scoped to a team."""
    aioclient_mock.get(
        "https://api.vercel.com/v10/projects?teamId=team_abc",
        json={
            "projects": [
                {
                    "id": "prj_456",
                    "name": "team-app",
                    "framework": "remix",
                }
            ],
            "pagination": {"count": 1, "next": None},
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session, team_id="team_abc")
    projects = await client.async_get_projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "team-app"


async def test_get_deployments(hass: HomeAssistant, aioclient_mock) -> None:
    """Test fetching deployments for a project."""
    aioclient_mock.get(
        "https://api.vercel.com/v6/deployments?projectId=prj_123&limit=5",
        json={
            "deployments": [
                {
                    "uid": "dpl_abc",
                    "name": "my-app",
                    "state": "READY",
                    "target": "production",
                    "created": 1700000000000,
                    "ready": 1700000060000,
                    "source": "git",
                    "url": "my-app-abc.vercel.app",
                    "inspectorUrl": (
                        "https://vercel.com/team/my-app/dpl_abc"
                    ),
                    "creator": {"username": "testuser"},
                    "meta": {
                        "githubCommitMessage": "fix: bug",
                    },
                    "isRollbackCandidate": True,
                }
            ],
            "pagination": {"count": 1, "next": None},
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    deployments = await client.async_get_deployments("prj_123", limit=5)
    assert len(deployments) == 1
    assert deployments[0]["state"] == "READY"


async def test_get_domains(hass: HomeAssistant, aioclient_mock) -> None:
    """Test fetching domains."""
    aioclient_mock.get(
        "https://api.vercel.com/v5/domains",
        json={
            "domains": [
                {
                    "name": "example.com",
                    "verified": True,
                    "expiresAt": 1800000000000,
                    "renew": True,
                }
            ],
            "pagination": {"count": 1, "next": None},
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    domains = await client.async_get_domains()
    assert len(domains) == 1
    assert domains[0]["name"] == "example.com"


async def test_get_domain_config(hass: HomeAssistant, aioclient_mock) -> None:
    """Test fetching domain configuration."""
    aioclient_mock.get(
        "https://api.vercel.com/v6/domains/example.com/config",
        json={"configuredBy": "CNAME", "misconfigured": False},
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    config = await client.async_get_domain_config("example.com")
    assert config["misconfigured"] is False
    assert config["configuredBy"] == "CNAME"


async def test_get_project_env_vars(hass: HomeAssistant, aioclient_mock) -> None:
    """Test fetching project environment variables."""
    aioclient_mock.get(
        "https://api.vercel.com/v9/projects/prj_123/env",
        json={
            "envs": [
                {
                    "key": "DATABASE_URL",
                    "type": "encrypted",
                    "target": ["production"],
                },
                {
                    "key": "API_KEY",
                    "type": "plain",
                    "target": ["production", "preview"],
                },
            ]
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    envs = await client.async_get_project_env_vars("prj_123")
    assert len(envs) == 2
    assert envs[0]["key"] == "DATABASE_URL"


async def test_connection_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test that connection errors raise VercelConnectionError."""
    aioclient_mock.get("https://api.vercel.com/v2/user", exc=TimeoutError())
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    with pytest.raises(VercelConnectionError):
        await client.async_get_user()


async def test_rate_limit_error(hass: HomeAssistant, aioclient_mock) -> None:
    """Test that 429 raises VercelRateLimitError."""
    aioclient_mock.get(
        "https://api.vercel.com/v2/user",
        status=429,
        headers={"Retry-After": "60"},
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    with pytest.raises(VercelRateLimitError):
        await client.async_get_user()
