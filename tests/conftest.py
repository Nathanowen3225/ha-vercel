"""Fixtures for Vercel integration tests."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vercel.const import DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable custom integrations in all tests."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry for personal account."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Vercel (Personal)",
        data={
            "api_token": "test_token_abc123",
        },
        unique_id="vercel_user_abc123",
    )


@pytest.fixture
def mock_team_config_entry() -> MockConfigEntry:
    """Return a mock config entry for a team."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Vercel (My Team)",
        data={
            "api_token": "test_token_abc123",
            "team_id": "team_abc123",
            "team_name": "My Team",
        },
        unique_id="vercel_team_abc123",
    )
