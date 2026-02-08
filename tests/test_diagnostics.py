"""Tests for the Vercel diagnostics platform."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vercel.const import DOMAIN
from custom_components.vercel.diagnostics import async_get_config_entry_diagnostics


@contextmanager
def _mock_api_client():
    """Create a mock API client for integration setup."""
    with patch("custom_components.vercel.VercelApiClient") as mock_cls:
        client = mock_cls.return_value
        client.async_get_projects = AsyncMock(return_value=[
            {"id": "prj_123", "name": "my-app", "framework": "nextjs", "nodeVersion": "20.x", "updatedAt": 1700000000000},
        ])
        client.async_get_deployments = AsyncMock(return_value=[])
        client.async_get_domains = AsyncMock(return_value=[])
        client.async_get_domain_config = AsyncMock(return_value={"misconfigured": False, "configuredBy": "CNAME"})
        client.async_get_project_env_vars = AsyncMock(return_value=[])
        yield mock_cls


async def test_diagnostics_redacts_token(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that diagnostics redacts the API token."""
    mock_config_entry.add_to_hass(hass)

    with _mock_api_client():
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert "entry_data" in diag
    assert diag["entry_data"]["api_token"] == "**REDACTED**"
    assert "project_data" in diag
    assert "deployment_data" in diag
