"""Base entities for the Vercel integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import VercelProjectCoordinator


class VercelProjectEntity(CoordinatorEntity[VercelProjectCoordinator]):
    """Base entity for a Vercel project (device)."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VercelProjectCoordinator,
        project_id: str,
        project_name: str,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._project_id = project_id
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = (
            f"{entry_id}_{project_id}_{entity_description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{project_id}")},
            name=project_name,
            manufacturer="Vercel",
            model="Project",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://vercel.com/~/projects/{project_name}",
        )


class VercelAccountEntity(CoordinatorEntity[VercelProjectCoordinator]):
    """Base entity for the Vercel account (device)."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VercelProjectCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = (
            f"{entry_id}_account_{entity_description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_account")},
            name=coordinator.config_entry.title,
            manufacturer="Vercel",
            model="Account",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://vercel.com/dashboard",
        )
