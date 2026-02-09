"""Tests for the Vercel binary sensor platform."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@contextmanager
def _mock_api_client():
    """Create a mock API client for integration setup."""
    with patch("custom_components.vercel.VercelApiClient") as mock_cls:
        client = mock_cls.return_value
        client.async_get_projects = AsyncMock(
            return_value=[
                {
                    "id": "prj_123",
                    "name": "my-app",
                    "framework": "nextjs",
                    "nodeVersion": "20.x",
                    "updatedAt": 1700000000000,
                },
            ]
        )
        client.async_get_deployments = AsyncMock(return_value=[])
        client.async_get_domains = AsyncMock(
            return_value=[
                {
                    "name": "example.com",
                    "verified": True,
                    "expiresAt": None,
                    "renew": True,
                },
            ]
        )
        client.async_get_domain_config = AsyncMock(
            return_value={"configuredBy": "CNAME", "misconfigured": False}
        )
        client.async_get_project_env_vars = AsyncMock(return_value=[])
        yield mock_cls


async def test_domain_binary_sensors_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that binary sensor entities are created for each domain."""
    mock_config_entry.add_to_hass(hass)

    with _mock_api_client():
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.example_com_domain_healthy")
    assert state is not None
    assert state.state == "on"

    state = hass.states.get("binary_sensor.example_com_ssl_valid")
    assert state is not None
    assert state.state == "on"

    state = hass.states.get("binary_sensor.example_com_domain_misconfigured")
    assert state is not None
    assert state.state == "off"


async def test_misconfigured_domain(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test binary sensors when domain is misconfigured."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.vercel.VercelApiClient") as mock_cls:
        client = mock_cls.return_value
        client.async_get_projects = AsyncMock(
            return_value=[
                {
                    "id": "prj_123",
                    "name": "my-app",
                    "framework": "nextjs",
                    "nodeVersion": "20.x",
                    "updatedAt": 1700000000000,
                },
            ]
        )
        client.async_get_deployments = AsyncMock(return_value=[])
        client.async_get_domains = AsyncMock(
            return_value=[
                {
                    "name": "broken.com",
                    "verified": False,
                    "expiresAt": None,
                    "renew": True,
                },
            ]
        )
        client.async_get_domain_config = AsyncMock(
            return_value={"configuredBy": None, "misconfigured": True}
        )
        client.async_get_project_env_vars = AsyncMock(return_value=[])

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.broken_com_domain_healthy")
    assert state is not None
    assert state.state == "off"

    state = hass.states.get("binary_sensor.broken_com_domain_misconfigured")
    assert state is not None
    assert state.state == "on"
