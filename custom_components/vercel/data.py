"""Runtime data types for the Vercel integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .api import VercelApiClient
    from .coordinator import (
        VercelDeploymentCoordinator,
        VercelProjectCoordinator,
    )

type VercelConfigEntry = ConfigEntry[VercelData]


@dataclass
class VercelData:
    """Runtime data for the Vercel integration."""

    client: VercelApiClient
    deployment_coordinator: VercelDeploymentCoordinator
    project_coordinator: VercelProjectCoordinator
