"""The Vercel integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .api import VercelApiClient
from .const import CONF_TEAM_ID, DOMAIN, LOGGER
from .coordinator import VercelDeploymentCoordinator, VercelProjectCoordinator
from .data import VercelConfigEntry, VercelData

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VercelConfigEntry,
) -> bool:
    """Set up Vercel from a config entry."""
    session = async_get_clientsession(hass)
    client = VercelApiClient(
        token=entry.data["api_token"],
        session=session,
        team_id=entry.data.get(CONF_TEAM_ID),
    )

    project_coordinator = VercelProjectCoordinator(hass, entry, client)
    await project_coordinator.async_config_entry_first_refresh()

    deployment_coordinator = VercelDeploymentCoordinator(
        hass, entry, client, project_coordinator
    )
    await deployment_coordinator.async_config_entry_first_refresh()

    entry.runtime_data = VercelData(
        client=client,
        project_coordinator=project_coordinator,
        deployment_coordinator=deployment_coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: VercelConfigEntry,
) -> bool:
    """Unload a Vercel config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
