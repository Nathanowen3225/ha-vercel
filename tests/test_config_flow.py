"""Tests for the Vercel config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vercel.const import DOMAIN


async def test_user_flow_personal_account(hass: HomeAssistant) -> None:
    """Test config flow for a personal account (no team)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.vercel.config_flow.VercelApiClient"
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.async_get_user = AsyncMock(
            return_value={"id": "user_abc", "username": "testuser", "name": "Test"}
        )
        client.async_get_teams = AsyncMock(return_value=[])

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"api_token": "test_token_123"},
        )

    # No teams -> skip team selection, create entry directly
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Vercel (testuser)"
    assert result["data"]["api_token"] == "test_token_123"
    assert "team_id" not in result["data"]


async def test_user_flow_with_team_selection(hass: HomeAssistant) -> None:
    """Test config flow with team selection step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.vercel.config_flow.VercelApiClient"
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.async_get_user = AsyncMock(
            return_value={"id": "user_abc", "username": "testuser", "name": "Test"}
        )
        client.async_get_teams = AsyncMock(
            return_value=[
                {"id": "team_abc", "slug": "my-team", "name": "My Team"},
                {"id": "team_def", "slug": "other-team", "name": "Other Team"},
            ]
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"api_token": "test_token_123"},
        )

    # Has teams -> show team selection
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "team"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"team": "team_abc"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Vercel (My Team)"
    assert result["data"]["team_id"] == "team_abc"
    assert result["data"]["team_name"] == "My Team"


async def test_user_flow_personal_with_teams(hass: HomeAssistant) -> None:
    """Test selecting personal account when teams are available."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.vercel.config_flow.VercelApiClient"
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.async_get_user = AsyncMock(
            return_value={"id": "user_abc", "username": "testuser", "name": "Test"}
        )
        client.async_get_teams = AsyncMock(
            return_value=[
                {"id": "team_abc", "slug": "my-team", "name": "My Team"},
            ]
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"api_token": "test_token_123"},
        )

    # Select personal account (empty string)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"team": ""},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Vercel (testuser)"
    assert "team_id" not in result["data"]


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    """Test config flow with invalid token."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.vercel.config_flow.VercelApiClient"
    ) as mock_client_cls:
        from custom_components.vercel.api import VercelAuthenticationError

        client = mock_client_cls.return_value
        client.async_get_user = AsyncMock(
            side_effect=VercelAuthenticationError("forbidden")
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"api_token": "bad_token"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_connection_error(hass: HomeAssistant) -> None:
    """Test config flow with connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.vercel.config_flow.VercelApiClient"
    ) as mock_client_cls:
        from custom_components.vercel.api import VercelConnectionError

        client = mock_client_cls.return_value
        client.async_get_user = AsyncMock(
            side_effect=VercelConnectionError("timeout")
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"api_token": "test_token"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(hass: HomeAssistant) -> None:
    """Test config flow aborts if already configured."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        unique_id="vercel_user_abc",
        data={"api_token": "existing_token"},
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.vercel.config_flow.VercelApiClient"
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.async_get_user = AsyncMock(
            return_value={"id": "user_abc", "username": "testuser", "name": "Test"}
        )
        client.async_get_teams = AsyncMock(return_value=[])

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"api_token": "test_token"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(hass: HomeAssistant) -> None:
    """Test reauth flow updates the token."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="vercel_user_abc",
        data={"api_token": "old_token"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.vercel.config_flow.VercelApiClient"
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.async_get_user = AsyncMock(
            return_value={"id": "user_abc", "username": "testuser", "name": "Test"}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"api_token": "new_token"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["api_token"] == "new_token"
