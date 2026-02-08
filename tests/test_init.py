"""Tests for the Vercel integration setup."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@contextmanager
def _mock_api_client():
    """Create a mock API client for integration setup."""
    with patch("custom_components.vercel.VercelApiClient") as mock_cls:
        client = mock_cls.return_value
        client.async_get_user = AsyncMock(return_value={"id": "user_abc"})
        client.async_get_projects = AsyncMock(return_value=[
            {
                "id": "prj_123",
                "name": "my-app",
                "framework": "nextjs",
                "nodeVersion": "20.x",
                "updatedAt": 1700000000000,
            },
        ])
        client.async_get_deployments = AsyncMock(return_value=[
            {
                "uid": "dpl_abc", "name": "my-app", "state": "READY",
                "target": "production", "created": 1700000000000,
                "ready": 1700000060000, "source": "git",
                "url": "my-app-abc.vercel.app",
                "inspectorUrl": "https://vercel.com/team/my-app/dpl_abc",
                "creator": {"username": "testuser"},
                "meta": {"githubCommitMessage": "fix: bug"},
                "isRollbackCandidate": True,
            },
        ])
        client.async_get_domains = AsyncMock(return_value=[
            {"name": "example.com", "verified": True, "expiresAt": None, "renew": True},
        ])
        client.async_get_domain_config = AsyncMock(return_value={
            "configuredBy": "CNAME", "misconfigured": False,
        })
        client.async_get_project_env_vars = AsyncMock(return_value=[
            {"key": "DB_URL", "type": "encrypted", "target": ["production"]},
        ])
        yield mock_cls


async def test_setup_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test successful setup of a config entry."""
    mock_config_entry.add_to_hass(hass)

    with _mock_api_client():
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_unload_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test unloading a config entry."""
    mock_config_entry.add_to_hass(hass)

    with _mock_api_client():
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.async_unload(mock_config_entry.entry_id)

    assert result is True
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
