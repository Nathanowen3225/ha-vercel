"""Diagnostics for the Vercel integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .data import VercelConfigEntry

TO_REDACT = {"api_token", "token", "api_key", "email"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: VercelConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "project_data": data.project_coordinator.data,
        "deployment_data": data.deployment_coordinator.data,
    }
