"""Sensor platform for the Vercel integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .best_practices import audit_project
from .coordinator import VercelDeploymentCoordinator, VercelProjectCoordinator
from .data import VercelConfigEntry
from .entity import VercelAccountEntity, VercelProjectEntity


@dataclass(frozen=True, kw_only=True)
class VercelProjectSensorDescription(SensorEntityDescription):
    """Describes a Vercel project sensor."""

    value_fn: Callable[[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]], StateType]
    attr_fn: Callable[[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any] | None] = (
        lambda p, d, e: None
    )


@dataclass(frozen=True, kw_only=True)
class VercelAccountSensorDescription(SensorEntityDescription):
    """Describes a Vercel account sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]


def _latest_deployment(deployments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Get the latest deployment from a list."""
    if not deployments:
        return None
    return deployments[0]


def _build_duration_seconds(deployment: dict[str, Any] | None) -> int | None:
    """Calculate build duration in seconds."""
    if not deployment:
        return None
    created = deployment.get("created")
    ready = deployment.get("ready")
    if created and ready:
        return round((ready - created) / 1000)
    return None


PROJECT_SENSORS: tuple[VercelProjectSensorDescription, ...] = (
    VercelProjectSensorDescription(
        key="deployment_status",
        translation_key="deployment_status",
        device_class=SensorDeviceClass.ENUM,
        options=["ready", "building", "error", "queued", "canceled", "initializing"],
        value_fn=lambda p, d, e: (
            _latest_deployment(d)["state"].lower()
            if _latest_deployment(d)
            else None
        ),
        attr_fn=lambda p, d, e: (
            {
                "deployment_id": dep["uid"],
                "commit_message": dep.get("meta", {}).get("githubCommitMessage", ""),
                "inspector_url": dep.get("inspectorUrl", ""),
            }
            if (dep := _latest_deployment(d))
            else None
        ),
    ),
    VercelProjectSensorDescription(
        key="deployment_url",
        translation_key="deployment_url",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda p, d, e: (
            _latest_deployment(d).get("url")
            if _latest_deployment(d)
            else None
        ),
    ),
    VercelProjectSensorDescription(
        key="build_duration",
        translation_key="build_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p, d, e: _build_duration_seconds(_latest_deployment(d)),
    ),
    VercelProjectSensorDescription(
        key="deployment_source",
        translation_key="deployment_source",
        device_class=SensorDeviceClass.ENUM,
        options=["git", "cli", "redeploy", "import"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda p, d, e: (
            _latest_deployment(d).get("source", "").lower()
            if _latest_deployment(d) and _latest_deployment(d).get("source", "").lower() in ("git", "cli", "redeploy", "import")
            else None
        ),
    ),
    VercelProjectSensorDescription(
        key="active_deployments",
        translation_key="active_deployments",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p, d, e: len(d),
    ),
    VercelProjectSensorDescription(
        key="failed_deployments_24h",
        translation_key="failed_deployments_24h",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p, d, e: sum(1 for dep in d if dep.get("state") == "ERROR"),
    ),
    VercelProjectSensorDescription(
        key="framework",
        translation_key="framework",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda p, d, e: p.get("framework"),
    ),
    VercelProjectSensorDescription(
        key="node_version",
        translation_key="node_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda p, d, e: p.get("nodeVersion"),
    ),
    VercelProjectSensorDescription(
        key="best_practices_score",
        translation_key="best_practices_score",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda p, d, e: audit_project(p, d, e).score,
        attr_fn=lambda p, d, e: {"issues": audit_project(p, d, e).issues},
    ),
    VercelProjectSensorDescription(
        key="best_practices_issues",
        translation_key="best_practices_issues",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda p, d, e: len(audit_project(p, d, e).issues),
        attr_fn=lambda p, d, e: {"details": audit_project(p, d, e).issues},
    ),
)

ACCOUNT_SENSORS: tuple[VercelAccountSensorDescription, ...] = (
    VercelAccountSensorDescription(
        key="total_projects",
        translation_key="total_projects",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.get("projects", {})),
    ),
    VercelAccountSensorDescription(
        key="total_domains",
        translation_key="total_domains",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(data.get("domains", {})),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VercelConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vercel sensor entities."""
    data = entry.runtime_data
    project_coord = data.project_coordinator
    deploy_coord = data.deployment_coordinator

    entities: list[SensorEntity] = []

    # Project-level sensors
    for project_id, project in project_coord.data["projects"].items():
        for description in PROJECT_SENSORS:
            entities.append(
                VercelProjectSensor(
                    project_coordinator=project_coord,
                    deployment_coordinator=deploy_coord,
                    project_id=project_id,
                    project_name=project["name"],
                    entity_description=description,
                )
            )

    # Account-level sensors
    for description in ACCOUNT_SENSORS:
        entities.append(
            VercelAccountSensor(
                coordinator=project_coord,
                entity_description=description,
            )
        )

    async_add_entities(entities)


class VercelProjectSensor(VercelProjectEntity, SensorEntity):
    """Sensor for a Vercel project."""

    entity_description: VercelProjectSensorDescription

    def __init__(
        self,
        project_coordinator: VercelProjectCoordinator,
        deployment_coordinator: VercelDeploymentCoordinator,
        project_id: str,
        project_name: str,
        entity_description: VercelProjectSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(project_coordinator, project_id, project_name, entity_description)
        self._deployment_coordinator = deployment_coordinator

    def _get_data(self) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """Get project, deployments, and env vars for this project."""
        project = self.coordinator.data["projects"].get(self._project_id, {})
        deployments = self._deployment_coordinator.data.get(self._project_id, [])
        env_vars = self.coordinator.data.get("env_vars", {}).get(self._project_id, [])
        return project, deployments, env_vars

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        project, deployments, env_vars = self._get_data()
        return self.entity_description.value_fn(project, deployments, env_vars)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        project, deployments, env_vars = self._get_data()
        return self.entity_description.attr_fn(project, deployments, env_vars)


class VercelAccountSensor(VercelAccountEntity, SensorEntity):
    """Sensor for the Vercel account."""

    entity_description: VercelAccountSensorDescription

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
