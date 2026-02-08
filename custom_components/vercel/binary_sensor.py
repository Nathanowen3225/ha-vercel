"""Binary sensor platform for the Vercel integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import VercelProjectCoordinator
from .data import VercelConfigEntry


@dataclass(frozen=True, kw_only=True)
class VercelDomainBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Vercel domain binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]


DOMAIN_BINARY_SENSORS: tuple[VercelDomainBinarySensorDescription, ...] = (
    VercelDomainBinarySensorDescription(
        key="domain_healthy",
        translation_key="domain_healthy",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: (
            d.get("verified", False)
            and d.get("configuredBy") is not None
        ),
    ),
    VercelDomainBinarySensorDescription(
        key="ssl_valid",
        translation_key="ssl_valid",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("configuredBy") is not None,
    ),
    VercelDomainBinarySensorDescription(
        key="domain_misconfigured",
        translation_key="domain_misconfigured",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.get("misconfigured", False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VercelConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vercel binary sensor entities."""
    project_coord = entry.runtime_data.project_coordinator

    entities: list[BinarySensorEntity] = []

    for domain_name, _domain_data in project_coord.data.get("domains", {}).items():
        for description in DOMAIN_BINARY_SENSORS:
            entities.append(
                VercelDomainBinarySensor(
                    coordinator=project_coord,
                    domain_name=domain_name,
                    entity_description=description,
                    entry_id=entry.entry_id,
                )
            )

    async_add_entities(entities)


class VercelDomainBinarySensor(
    CoordinatorEntity[VercelProjectCoordinator],
    BinarySensorEntity,
):
    """Binary sensor for a Vercel domain."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    entity_description: VercelDomainBinarySensorDescription

    def __init__(
        self,
        coordinator: VercelProjectCoordinator,
        domain_name: str,
        entity_description: VercelDomainBinarySensorDescription,
        entry_id: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._domain_name = domain_name
        self._attr_unique_id = f"{entry_id}_{domain_name}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_domain_{domain_name}")},
            name=domain_name,
            manufacturer="Vercel",
            model="Domain",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the condition is met."""
        domains = self.coordinator.data.get("domains", {})
        domain_data = domains.get(self._domain_name, {})
        return self.entity_description.value_fn(domain_data)
