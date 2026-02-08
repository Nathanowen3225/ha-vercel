"""Tests for the Vercel coordinators."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.vercel.api import (
    VercelApiClient,
    VercelAuthenticationError,
    VercelConnectionError,
)
from custom_components.vercel.coordinator import (
    VercelDeploymentCoordinator,
    VercelProjectCoordinator,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vercel.const import DOMAIN


def _make_mock_client() -> AsyncMock:
    """Create a mock API client with default responses."""
    client = AsyncMock(spec=VercelApiClient)
    client.async_get_projects.return_value = [
        {
            "id": "prj_123",
            "name": "my-app",
            "framework": "nextjs",
            "nodeVersion": "20.x",
            "updatedAt": 1700000000000,
        },
    ]
    client.async_get_deployments.return_value = [
        {
            "uid": "dpl_abc",
            "name": "my-app",
            "state": "READY",
            "target": "production",
            "created": 1700000000000,
            "ready": 1700000060000,
            "source": "git",
            "url": "my-app-abc.vercel.app",
            "inspectorUrl": "https://vercel.com/team/my-app/dpl_abc",
            "creator": {"username": "testuser"},
            "meta": {"githubCommitMessage": "fix: bug"},
            "isRollbackCandidate": True,
        },
    ]
    client.async_get_domains.return_value = [
        {"name": "example.com", "verified": True, "expiresAt": None, "renew": True},
    ]
    client.async_get_domain_config.return_value = {
        "configuredBy": "CNAME",
        "misconfigured": False,
    }
    client.async_get_project_env_vars.return_value = [
        {"key": "DATABASE_URL", "type": "encrypted", "target": ["production"]},
    ]
    return client


def _set_entry_setup_in_progress(entry: MockConfigEntry) -> None:
    """Set the config entry state to SETUP_IN_PROGRESS for coordinator tests."""
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_IN_PROGRESS)


async def test_project_coordinator_update(hass: HomeAssistant) -> None:
    """Test project coordinator fetches projects, domains, and env vars."""
    entry = MockConfigEntry(domain=DOMAIN, data={"api_token": "test"})
    entry.add_to_hass(hass)
    _set_entry_setup_in_progress(entry)

    client = _make_mock_client()
    coordinator = VercelProjectCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    data = coordinator.data
    assert "prj_123" in data["projects"]
    assert data["projects"]["prj_123"]["name"] == "my-app"
    assert "example.com" in data["domains"]
    assert data["domains"]["example.com"]["misconfigured"] is False
    assert len(data["env_vars"]["prj_123"]) == 1


async def test_deployment_coordinator_update(hass: HomeAssistant) -> None:
    """Test deployment coordinator fetches deployments per project."""
    entry = MockConfigEntry(domain=DOMAIN, data={"api_token": "test"})
    entry.add_to_hass(hass)
    _set_entry_setup_in_progress(entry)

    client = _make_mock_client()
    project_coordinator = VercelProjectCoordinator(hass, entry, client)
    await project_coordinator.async_config_entry_first_refresh()

    deployment_coordinator = VercelDeploymentCoordinator(
        hass, entry, client, project_coordinator
    )
    await deployment_coordinator.async_config_entry_first_refresh()

    data = deployment_coordinator.data
    assert "prj_123" in data
    assert len(data["prj_123"]) == 1
    assert data["prj_123"][0]["state"] == "READY"


async def test_project_coordinator_auth_failure(hass: HomeAssistant) -> None:
    """Test that auth failures raise ConfigEntryAuthFailed."""
    entry = MockConfigEntry(domain=DOMAIN, data={"api_token": "bad"})
    entry.add_to_hass(hass)
    _set_entry_setup_in_progress(entry)

    client = _make_mock_client()
    client.async_get_projects.side_effect = VercelAuthenticationError("forbidden")

    coordinator = VercelProjectCoordinator(hass, entry, client)

    try:
        await coordinator.async_config_entry_first_refresh()
        assert False, "Should have raised ConfigEntryAuthFailed"
    except ConfigEntryAuthFailed:
        pass


async def test_project_coordinator_connection_error(hass: HomeAssistant) -> None:
    """Test that connection errors raise ConfigEntryNotReady on first refresh.

    When async_config_entry_first_refresh encounters an UpdateFailed from the
    coordinator, it wraps it into ConfigEntryNotReady so HA retries setup.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={"api_token": "test"})
    entry.add_to_hass(hass)
    _set_entry_setup_in_progress(entry)

    client = _make_mock_client()
    client.async_get_projects.side_effect = VercelConnectionError("timeout")

    coordinator = VercelProjectCoordinator(hass, entry, client)

    try:
        await coordinator.async_config_entry_first_refresh()
        assert False, "Should have raised ConfigEntryNotReady"
    except ConfigEntryNotReady:
        pass
