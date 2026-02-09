"""Tests for the Vercel sensor platform."""

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
        client.async_get_deployments = AsyncMock(
            return_value=[
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
                }
            ]
        )
        client.async_get_domains = AsyncMock(return_value=[])
        client.async_get_domain_config = AsyncMock(
            return_value={"misconfigured": False, "configuredBy": "CNAME"}
        )
        client.async_get_project_env_vars = AsyncMock(
            return_value=[
                {"key": "DATABASE_URL", "type": "encrypted", "target": ["production"]},
            ]
        )
        yield mock_cls


async def test_sensor_entities_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that sensor entities are created for each project."""
    mock_config_entry.add_to_hass(hass)

    with _mock_api_client():
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Check project-level sensors exist
    state = hass.states.get("sensor.my_app_deployment_status")
    assert state is not None
    assert state.state == "ready"

    state = hass.states.get("sensor.my_app_build_duration")
    assert state is not None
    assert state.state == "60"

    state = hass.states.get("sensor.my_app_framework")
    assert state is not None
    assert state.state == "nextjs"

    state = hass.states.get("sensor.my_app_node_version")
    assert state is not None
    assert state.state == "20.x"


async def test_account_sensors_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that account-level sensor entities are created."""
    mock_config_entry.add_to_hass(hass)

    with _mock_api_client():
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.vercel_personal_total_projects")
    assert state is not None
    assert state.state == "1"


async def test_best_practices_score(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test best practices score sensor returns expected value."""
    mock_config_entry.add_to_hass(hass)

    with _mock_api_client():
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.my_app_best_practices_score")
    assert state is not None
    # Score should be numeric
    assert int(state.state) >= 0
    assert int(state.state) <= 100


async def test_deployment_status_attributes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test deployment status sensor has correct extra attributes."""
    mock_config_entry.add_to_hass(hass)

    with _mock_api_client():
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.my_app_deployment_status")
    assert state is not None
    assert state.attributes.get("deployment_id") == "dpl_abc"
    assert state.attributes.get("commit_message") == "fix: bug"
