# Home Assistant Vercel Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a HACS-compatible Home Assistant custom integration that monitors Vercel deployments, projects, domains, and billing — and audits each project against Vercel best practices.

**Architecture:** Three `DataUpdateCoordinator` instances poll the Vercel REST API at different intervals (deployments at 60s, projects+domains at 15min, billing at 1hr). Each Vercel project becomes an HA device with sensors underneath. A `best_practices` module scores each project 0–100. Auth is via user-created Bearer token, one config entry per team/personal account.

**Tech Stack:** Python 3.13+, aiohttp (via HA's `async_get_clientsession`), pytest + pytest-homeassistant-custom-component, HACS-compatible structure.

---

## File Tree (final state)

```
ha-vercel/
├── custom_components/
│   └── vercel/
│       ├── __init__.py
│       ├── api.py
│       ├── best_practices.py
│       ├── binary_sensor.py
│       ├── config_flow.py
│       ├── const.py
│       ├── coordinator.py
│       ├── data.py
│       ├── diagnostics.py
│       ├── entity.py
│       ├── icons.json
│       ├── manifest.json
│       ├── sensor.py
│       ├── strings.json
│       └── translations/
│           └── en.json
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_best_practices.py
│   ├── test_binary_sensor.py
│   ├── test_config_flow.py
│   ├── test_coordinator.py
│   ├── test_diagnostics.py
│   ├── test_init.py
│   └── test_sensor.py
├── .github/
│   └── workflows/
│       └── validate.yml
├── .gitignore
├── hacs.json
├── pyproject.toml
├── requirements_test.txt
└── LICENSE
```

---

## Vercel API Reference (for all tasks below)

**Base URL:** `https://api.vercel.com`
**Auth Header:** `Authorization: Bearer <TOKEN>`
**Team scoping:** append `?teamId=<TEAM_ID>` to any request.
**Error shape:** `{"error": {"code": "string", "message": "string"}}`
**Auth failures:** HTTP 401 or 403 → raise `ConfigEntryAuthFailed`
**Rate limit:** HTTP 429 → raise `UpdateFailed` (coordinator retries at next interval)
**Transient errors:** any other non-200 → raise `UpdateFailed`

| Endpoint | Purpose |
|----------|---------|
| `GET /v2/user` | Validate token, get user info |
| `GET /v2/teams` | List teams for team selection in config flow |
| `GET /v10/projects` | List all projects (pagination via `?from=`) |
| `GET /v9/projects/{id}` | Get single project detail (framework, analytics, settings) |
| `GET /v6/deployments?projectId=X&limit=5` | Recent deployments per project |
| `GET /v5/domains` | List all domains |
| `GET /v6/domains/{domain}/config` | Domain health check (`misconfigured`, `configuredBy`) |
| `GET /v9/projects/{id}/env` | List env vars (keys only, for best-practices audit) |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `custom_components/vercel/const.py`
- Create: `custom_components/vercel/manifest.json`
- Create: `custom_components/vercel/__init__.py` (empty placeholder)
- Create: `hacs.json`
- Create: `pyproject.toml`
- Create: `requirements_test.txt`
- Create: `.gitignore`
- Create: `.github/workflows/validate.yml`

**Step 1: Initialize git repo and create .gitignore**

```bash
cd /Users/nathanowen/projects/ha-vercel
git init
```

Create `.gitignore`:

```
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.eggs/
*.egg
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
.coverage
*.log
.DS_Store
.claude/
```

**Step 2: Create `custom_components/vercel/const.py`**

```python
"""Constants for the Vercel integration."""

from __future__ import annotations

import logging

DOMAIN = "vercel"
LOGGER = logging.getLogger(__package__)

CONF_TEAM_ID = "team_id"
CONF_TEAM_NAME = "team_name"

VERCEL_API_BASE = "https://api.vercel.com"

DEFAULT_DEPLOYMENT_SCAN_INTERVAL = 60  # seconds
DEFAULT_PROJECT_SCAN_INTERVAL = 900  # 15 minutes
DEFAULT_BILLING_SCAN_INTERVAL = 3600  # 1 hour

ATTRIBUTION = "Data provided by Vercel"
```

**Step 3: Create `custom_components/vercel/manifest.json`**

```json
{
  "domain": "vercel",
  "name": "Vercel",
  "codeowners": ["@nathanowen"],
  "config_flow": true,
  "documentation": "https://github.com/nathanowen/ha-vercel",
  "integration_type": "hub",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/nathanowen/ha-vercel/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

**Step 4: Create empty `custom_components/vercel/__init__.py`**

```python
"""The Vercel integration."""
```

**Step 5: Create `hacs.json`**

```json
{
  "name": "Vercel",
  "render_readme": true
}
```

**Step 6: Create `pyproject.toml`**

```toml
[project]
name = "ha-vercel"
version = "0.1.0"
requires-python = ">=3.13"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

**Step 7: Create `requirements_test.txt`**

```
pytest==8.*
pytest-asyncio==0.*
pytest-homeassistant-custom-component
```

**Step 8: Create `.github/workflows/validate.yml`**

```yaml
name: Validate

on:
  push:
  pull_request:

jobs:
  validate-hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration

  validate-hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master

  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -r requirements_test.txt
      - run: pytest tests/ -v --tb=short
```

**Step 9: Commit**

```bash
git add -A
git commit -m "chore: scaffold ha-vercel project structure"
```

---

## Task 2: Vercel API Client

**Files:**
- Create: `custom_components/vercel/api.py`
- Create: `tests/conftest.py`
- Create: `tests/test_api.py`

**Step 1: Create `tests/conftest.py`**

```python
"""Fixtures for Vercel integration tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientSession

from homeassistant.core import HomeAssistant

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
```

**Step 2: Write the failing test for the API client**

Create `tests/test_api.py`:

```python
"""Tests for the Vercel API client."""

from __future__ import annotations

from aiohttp import ClientResponseError, ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.vercel.api import (
    VercelApiClient,
    VercelAuthenticationError,
    VercelConnectionError,
)


async def test_get_user(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test fetching the authenticated user."""
    aioclient_mock.get(
        "https://api.vercel.com/v2/user",
        json={
            "user": {
                "id": "user_abc123",
                "email": "test@example.com",
                "username": "testuser",
                "name": "Test User",
            }
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    user = await client.async_get_user()
    assert user["id"] == "user_abc123"
    assert user["username"] == "testuser"


async def test_get_user_auth_failure(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that 403 raises VercelAuthenticationError."""
    aioclient_mock.get(
        "https://api.vercel.com/v2/user",
        status=403,
        json={"error": {"code": "forbidden", "message": "Forbidden"}},
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="bad_token", session=session)

    try:
        await client.async_get_user()
        assert False, "Should have raised VercelAuthenticationError"
    except VercelAuthenticationError:
        pass


async def test_get_teams(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test fetching teams."""
    aioclient_mock.get(
        "https://api.vercel.com/v2/teams",
        json={
            "teams": [
                {"id": "team_abc", "slug": "my-team", "name": "My Team"},
            ],
            "pagination": {"count": 1, "next": None, "prev": None},
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    teams = await client.async_get_teams()
    assert len(teams) == 1
    assert teams[0]["slug"] == "my-team"


async def test_get_projects(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test fetching projects."""
    aioclient_mock.get(
        "https://api.vercel.com/v10/projects",
        json={
            "projects": [
                {
                    "id": "prj_123",
                    "name": "my-app",
                    "framework": "nextjs",
                    "nodeVersion": "20.x",
                    "updatedAt": 1700000000000,
                },
            ],
            "pagination": {"count": 1, "next": None},
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    projects = await client.async_get_projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "my-app"


async def test_get_projects_with_team(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test fetching projects scoped to a team."""
    aioclient_mock.get(
        "https://api.vercel.com/v10/projects?teamId=team_abc",
        json={
            "projects": [
                {"id": "prj_456", "name": "team-app", "framework": "remix"},
            ],
            "pagination": {"count": 1, "next": None},
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session, team_id="team_abc")
    projects = await client.async_get_projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "team-app"


async def test_get_deployments(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test fetching deployments for a project."""
    aioclient_mock.get(
        "https://api.vercel.com/v6/deployments?projectId=prj_123&limit=5",
        json={
            "deployments": [
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
                },
            ],
            "pagination": {"count": 1, "next": None},
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    deployments = await client.async_get_deployments("prj_123", limit=5)
    assert len(deployments) == 1
    assert deployments[0]["state"] == "READY"


async def test_get_domains(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test fetching domains."""
    aioclient_mock.get(
        "https://api.vercel.com/v5/domains",
        json={
            "domains": [
                {
                    "name": "example.com",
                    "verified": True,
                    "expiresAt": 1800000000000,
                    "renew": True,
                },
            ],
            "pagination": {"count": 1, "next": None},
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    domains = await client.async_get_domains()
    assert len(domains) == 1
    assert domains[0]["name"] == "example.com"


async def test_get_domain_config(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test fetching domain configuration."""
    aioclient_mock.get(
        "https://api.vercel.com/v6/domains/example.com/config",
        json={
            "configuredBy": "CNAME",
            "misconfigured": False,
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    config = await client.async_get_domain_config("example.com")
    assert config["misconfigured"] is False
    assert config["configuredBy"] == "CNAME"


async def test_get_project_env_vars(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test fetching project environment variables."""
    aioclient_mock.get(
        "https://api.vercel.com/v9/projects/prj_123/env",
        json={
            "envs": [
                {"key": "DATABASE_URL", "type": "encrypted", "target": ["production"]},
                {"key": "API_KEY", "type": "plain", "target": ["production", "preview"]},
            ],
        },
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)
    envs = await client.async_get_project_env_vars("prj_123")
    assert len(envs) == 2
    assert envs[0]["key"] == "DATABASE_URL"


async def test_connection_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that connection errors raise VercelConnectionError."""
    aioclient_mock.get(
        "https://api.vercel.com/v2/user",
        exc=TimeoutError(),
    )
    session = async_get_clientsession(hass)
    client = VercelApiClient(token="test_token", session=session)

    try:
        await client.async_get_user()
        assert False, "Should have raised VercelConnectionError"
    except VercelConnectionError:
        pass
```

**Step 3: Run tests to verify they fail**

```bash
cd /Users/nathanowen/projects/ha-vercel
pip install -r requirements_test.txt
pytest tests/test_api.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.vercel.api'`

**Step 4: Implement the API client**

Create `custom_components/vercel/api.py`:

```python
"""Vercel API client."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import VERCEL_API_BASE


class VercelApiError(Exception):
    """Base exception for Vercel API errors."""


class VercelAuthenticationError(VercelApiError):
    """Raised when authentication fails."""


class VercelConnectionError(VercelApiError):
    """Raised when a connection error occurs."""


class VercelApiClient:
    """Async client for the Vercel REST API."""

    def __init__(
        self,
        token: str,
        session: ClientSession,
        team_id: str | None = None,
    ) -> None:
        """Initialize the client."""
        self._token = token
        self._session = session
        self._team_id = team_id

    def _headers(self) -> dict[str, str]:
        """Return auth headers."""
        return {"Authorization": f"Bearer {self._token}"}

    def _team_params(self) -> dict[str, str]:
        """Return team query params if team_id is set."""
        if self._team_id:
            return {"teamId": self._team_id}
        return {}

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Make an API request."""
        url = f"{VERCEL_API_BASE}{path}"
        merged_params = {**self._team_params(), **(params or {})}
        try:
            async with self._session.request(
                method, url, headers=self._headers(), params=merged_params or None
            ) as resp:
                if resp.status in (401, 403):
                    raise VercelAuthenticationError(
                        f"Authentication failed: {resp.status}"
                    )
                resp.raise_for_status()
                return await resp.json()
        except VercelAuthenticationError:
            raise
        except ClientResponseError as err:
            raise VercelConnectionError(
                f"API error: {err.status} {err.message}"
            ) from err
        except (ClientError, TimeoutError) as err:
            raise VercelConnectionError(
                f"Connection error: {err}"
            ) from err

    async def async_get_user(self) -> dict[str, Any]:
        """Get the authenticated user. Used for token validation."""
        data = await self._request("GET", "/v2/user")
        return data["user"]

    async def async_get_teams(self) -> list[dict[str, Any]]:
        """Get all teams for the authenticated user."""
        data = await self._request("GET", "/v2/teams")
        return data["teams"]

    async def async_get_projects(self) -> list[dict[str, Any]]:
        """Get all projects. Paginates automatically."""
        all_projects: list[dict[str, Any]] = []
        params: dict[str, Any] = {"limit": "100"}
        while True:
            data = await self._request("GET", "/v10/projects", params=params)
            all_projects.extend(data["projects"])
            pagination = data.get("pagination", {})
            next_cursor = pagination.get("next")
            if not next_cursor:
                break
            params["from"] = str(next_cursor)
        return all_projects

    async def async_get_project(self, project_id: str) -> dict[str, Any]:
        """Get a single project by ID."""
        return await self._request("GET", f"/v9/projects/{project_id}")

    async def async_get_deployments(
        self,
        project_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get recent deployments for a project."""
        data = await self._request(
            "GET",
            "/v6/deployments",
            params={"projectId": project_id, "limit": str(limit)},
        )
        return data["deployments"]

    async def async_get_domains(self) -> list[dict[str, Any]]:
        """Get all domains."""
        all_domains: list[dict[str, Any]] = []
        params: dict[str, Any] = {"limit": "100"}
        while True:
            data = await self._request("GET", "/v5/domains", params=params)
            all_domains.extend(data["domains"])
            pagination = data.get("pagination", {})
            next_cursor = pagination.get("next")
            if not next_cursor:
                break
            params["until"] = str(next_cursor)
        return all_domains

    async def async_get_domain_config(self, domain: str) -> dict[str, Any]:
        """Get domain configuration/health."""
        return await self._request("GET", f"/v6/domains/{domain}/config")

    async def async_get_project_env_vars(
        self, project_id: str
    ) -> list[dict[str, Any]]:
        """Get environment variables for a project (keys only, not values)."""
        data = await self._request("GET", f"/v9/projects/{project_id}/env")
        return data["envs"]
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_api.py -v
```

Expected: ALL PASS

**Step 6: Commit**

```bash
git add custom_components/vercel/api.py tests/conftest.py tests/test_api.py
git commit -m "feat: add Vercel API client with tests"
```

---

## Task 3: Data Types and Runtime Data

**Files:**
- Create: `custom_components/vercel/data.py`

**Step 1: Create `custom_components/vercel/data.py`**

```python
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
```

**Step 2: Commit**

```bash
git add custom_components/vercel/data.py
git commit -m "feat: add runtime data types"
```

---

## Task 4: Coordinators

**Files:**
- Create: `custom_components/vercel/coordinator.py`
- Create: `tests/test_coordinator.py`

**Step 1: Write the failing coordinator tests**

Create `tests/test_coordinator.py`:

```python
"""Tests for the Vercel coordinators."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.vercel.api import (
    VercelApiClient,
    VercelAuthenticationError,
    VercelConnectionError,
)
from custom_components.vercel.coordinator import (
    VercelDeploymentCoordinator,
    VercelProjectCoordinator,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vercel.const import DOMAIN


def _make_mock_client() -> AsyncMock:
    """Create a mock API client with default responses."""
    client = AsyncMock(spec=VercelApiClient)
    client.async_get_projects.return_value = [
        {
            "id": "prj_123",
            "name": "my-app",
            "framework": "nextjs",
            "nodeVersion": "20.x",
            "updatedAt": 1700000000000,
        },
    ]
    client.async_get_deployments.return_value = [
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
        },
    ]
    client.async_get_domains.return_value = [
        {"name": "example.com", "verified": True, "expiresAt": None, "renew": True},
    ]
    client.async_get_domain_config.return_value = {
        "configuredBy": "CNAME",
        "misconfigured": False,
    }
    client.async_get_project_env_vars.return_value = [
        {"key": "DATABASE_URL", "type": "encrypted", "target": ["production"]},
    ]
    return client


async def test_project_coordinator_update(hass: HomeAssistant) -> None:
    """Test project coordinator fetches projects, domains, and env vars."""
    entry = MockConfigEntry(domain=DOMAIN, data={"api_token": "test"})
    entry.add_to_hass(hass)

    client = _make_mock_client()
    coordinator = VercelProjectCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    data = coordinator.data
    assert "prj_123" in data["projects"]
    assert data["projects"]["prj_123"]["name"] == "my-app"
    assert "example.com" in data["domains"]
    assert data["domains"]["example.com"]["misconfigured"] is False
    assert len(data["env_vars"]["prj_123"]) == 1


async def test_deployment_coordinator_update(hass: HomeAssistant) -> None:
    """Test deployment coordinator fetches deployments per project."""
    entry = MockConfigEntry(domain=DOMAIN, data={"api_token": "test"})
    entry.add_to_hass(hass)

    client = _make_mock_client()
    # The deployment coordinator needs to know project IDs
    project_coordinator = VercelProjectCoordinator(hass, entry, client)
    await project_coordinator.async_config_entry_first_refresh()

    deployment_coordinator = VercelDeploymentCoordinator(
        hass, entry, client, project_coordinator
    )
    await deployment_coordinator.async_config_entry_first_refresh()

    data = deployment_coordinator.data
    assert "prj_123" in data
    assert len(data["prj_123"]) == 1
    assert data["prj_123"][0]["state"] == "READY"


async def test_project_coordinator_auth_failure(hass: HomeAssistant) -> None:
    """Test that auth failures raise ConfigEntryAuthFailed."""
    entry = MockConfigEntry(domain=DOMAIN, data={"api_token": "bad"})
    entry.add_to_hass(hass)

    client = _make_mock_client()
    client.async_get_projects.side_effect = VercelAuthenticationError("forbidden")

    coordinator = VercelProjectCoordinator(hass, entry, client)

    try:
        await coordinator.async_config_entry_first_refresh()
        assert False, "Should have raised ConfigEntryAuthFailed"
    except ConfigEntryAuthFailed:
        pass


async def test_project_coordinator_connection_error(hass: HomeAssistant) -> None:
    """Test that connection errors raise UpdateFailed."""
    entry = MockConfigEntry(domain=DOMAIN, data={"api_token": "test"})
    entry.add_to_hass(hass)

    client = _make_mock_client()
    client.async_get_projects.side_effect = VercelConnectionError("timeout")

    coordinator = VercelProjectCoordinator(hass, entry, client)

    try:
        await coordinator.async_config_entry_first_refresh()
        assert False, "Should have raised UpdateFailed"
    except UpdateFailed:
        pass
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_coordinator.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement the coordinators**

Create `custom_components/vercel/coordinator.py`:

```python
"""DataUpdateCoordinators for the Vercel integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VercelApiClient, VercelAuthenticationError, VercelConnectionError
from .const import (
    DEFAULT_DEPLOYMENT_SCAN_INTERVAL,
    DEFAULT_PROJECT_SCAN_INTERVAL,
    LOGGER,
)


class VercelProjectCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for projects, domains, and env vars."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: VercelApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="vercel_projects",
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_PROJECT_SCAN_INTERVAL),
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch projects, domains, domain configs, and env vars."""
        try:
            raw_projects = await self.client.async_get_projects()
            raw_domains = await self.client.async_get_domains()

            # Index projects by ID
            projects: dict[str, Any] = {}
            for proj in raw_projects:
                projects[proj["id"]] = proj

            # Fetch domain configs and index by domain name
            domains: dict[str, Any] = {}
            for domain in raw_domains:
                name = domain["name"]
                try:
                    config = await self.client.async_get_domain_config(name)
                except VercelConnectionError:
                    config = {"misconfigured": None, "configuredBy": None}
                domains[name] = {**domain, **config}

            # Fetch env vars per project (for best practices audit)
            env_vars: dict[str, list[dict[str, Any]]] = {}
            for project_id in projects:
                try:
                    envs = await self.client.async_get_project_env_vars(project_id)
                except VercelConnectionError:
                    envs = []
                env_vars[project_id] = envs

            return {
                "projects": projects,
                "domains": domains,
                "env_vars": env_vars,
            }
        except VercelAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except VercelConnectionError as err:
            raise UpdateFailed(f"Error fetching Vercel data: {err}") from err


class VercelDeploymentCoordinator(DataUpdateCoordinator[dict[str, list[dict[str, Any]]]]):
    """Coordinator for deployments (higher frequency)."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: VercelApiClient,
        project_coordinator: VercelProjectCoordinator,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="vercel_deployments",
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_DEPLOYMENT_SCAN_INTERVAL),
            always_update=False,
        )
        self.client = client
        self._project_coordinator = project_coordinator

    async def _async_update_data(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch recent deployments for each known project."""
        try:
            project_data = self._project_coordinator.data
            if not project_data:
                return {}

            result: dict[str, list[dict[str, Any]]] = {}
            for project_id in project_data["projects"]:
                try:
                    deployments = await self.client.async_get_deployments(
                        project_id, limit=5
                    )
                except VercelConnectionError:
                    deployments = []
                result[project_id] = deployments

            return result
        except VercelAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except VercelConnectionError as err:
            raise UpdateFailed(f"Error fetching deployments: {err}") from err
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_coordinator.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add custom_components/vercel/coordinator.py tests/test_coordinator.py
git commit -m "feat: add project and deployment coordinators with tests"
```

---

## Task 5: Config Flow

**Files:**
- Create: `custom_components/vercel/config_flow.py`
- Create: `custom_components/vercel/strings.json`
- Create: `tests/test_config_flow.py`

**Step 1: Write the failing config flow tests**

Create `tests/test_config_flow.py`:

```python
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

    # No teams → skip team selection, create entry directly
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

    # Has teams → show team selection
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
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config_flow.py -v
```

Expected: FAIL

**Step 3: Implement the config flow**

Create `custom_components/vercel/config_flow.py`:

```python
"""Config flow for the Vercel integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VercelApiClient, VercelAuthenticationError, VercelConnectionError
from .const import CONF_TEAM_ID, CONF_TEAM_NAME, DOMAIN


class VercelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vercel."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._token: str = ""
        self._user: dict[str, Any] = {}
        self._teams: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial token input step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._token = user_input["api_token"]
            session = async_get_clientsession(self.hass)
            client = VercelApiClient(token=self._token, session=session)

            try:
                self._user = await client.async_get_user()
                self._teams = await client.async_get_teams()
            except VercelAuthenticationError:
                errors["base"] = "invalid_auth"
            except VercelConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                if self._teams:
                    return await self.async_step_team()

                # No teams — personal account only
                unique_id = f"vercel_{self._user['id']}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Vercel ({self._user['username']})",
                    data={"api_token": self._token},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("api_token"): str}
            ),
            errors=errors,
        )

    async def async_step_team(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle team selection step."""
        if user_input is not None:
            team_id = user_input.get("team", "")

            if team_id:
                # Team selected
                team = next(t for t in self._teams if t["id"] == team_id)
                unique_id = f"vercel_{team_id}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Vercel ({team['name']})",
                    data={
                        "api_token": self._token,
                        CONF_TEAM_ID: team_id,
                        CONF_TEAM_NAME: team["name"],
                    },
                )

            # Personal account selected
            unique_id = f"vercel_{self._user['id']}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Vercel ({self._user['username']})",
                data={"api_token": self._token},
            )

        # Build team selection options
        team_options = {"": f"Personal ({self._user['username']})"}
        for team in self._teams:
            team_options[team["id"]] = team["name"]

        return self.async_show_form(
            step_id="team",
            data_schema=vol.Schema(
                {vol.Required("team"): vol.In(team_options)}
            ),
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth trigger."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth token input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = VercelApiClient(
                token=user_input["api_token"], session=session
            )

            try:
                await client.async_get_user()
            except VercelAuthenticationError:
                errors["base"] = "invalid_auth"
            except VercelConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={"api_token": user_input["api_token"]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required("api_token"): str}
            ),
            errors=errors,
        )
```

**Step 4: Create `custom_components/vercel/strings.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Connect to Vercel",
        "description": "Enter your Vercel API token. Create one at https://vercel.com/account/tokens",
        "data": {
          "api_token": "API Token"
        }
      },
      "team": {
        "title": "Select Account",
        "description": "Choose which Vercel account to monitor.",
        "data": {
          "team": "Account"
        }
      },
      "reauth_confirm": {
        "title": "Re-authenticate with Vercel",
        "description": "Your Vercel API token has expired or been revoked. Enter a new token.",
        "data": {
          "api_token": "API Token"
        }
      }
    },
    "error": {
      "invalid_auth": "Invalid API token. Check your token and try again.",
      "cannot_connect": "Unable to connect to the Vercel API.",
      "unknown": "An unexpected error occurred."
    },
    "abort": {
      "already_configured": "[%key:common::config_flow::abort::already_configured_account%]",
      "reauth_successful": "[%key:common::config_flow::abort::reauth_successful%]"
    }
  },
  "entity": {
    "sensor": {
      "deployment_status": {
        "name": "Deployment status",
        "state": {
          "ready": "Ready",
          "building": "Building",
          "error": "Error",
          "queued": "Queued",
          "canceled": "Canceled",
          "initializing": "Initializing"
        }
      },
      "deployment_url": {
        "name": "Deployment URL"
      },
      "build_duration": {
        "name": "Build duration"
      },
      "deployment_source": {
        "name": "Deployment source",
        "state": {
          "git": "Git",
          "cli": "CLI",
          "redeploy": "Redeploy",
          "import": "Import"
        }
      },
      "active_deployments": {
        "name": "Active deployments"
      },
      "failed_deployments_24h": {
        "name": "Failed deployments (24h)"
      },
      "framework": {
        "name": "Framework"
      },
      "node_version": {
        "name": "Node version"
      },
      "domain_count": {
        "name": "Domains"
      },
      "best_practices_score": {
        "name": "Best practices score"
      },
      "best_practices_issues": {
        "name": "Best practices issues"
      },
      "total_projects": {
        "name": "Total projects"
      },
      "total_domains": {
        "name": "Total domains"
      }
    },
    "binary_sensor": {
      "domain_healthy": {
        "name": "Domain healthy"
      },
      "ssl_valid": {
        "name": "SSL valid"
      },
      "domain_misconfigured": {
        "name": "Domain misconfigured"
      }
    }
  }
}
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_config_flow.py -v
```

Expected: ALL PASS

**Step 6: Commit**

```bash
git add custom_components/vercel/config_flow.py custom_components/vercel/strings.json tests/test_config_flow.py
git commit -m "feat: add config flow with team selection and reauth"
```

---

## Task 6: Best Practices Audit Module

**Files:**
- Create: `custom_components/vercel/best_practices.py`
- Create: `tests/test_best_practices.py`

**Step 1: Write the failing tests**

Create `tests/test_best_practices.py`:

```python
"""Tests for the Vercel best practices audit."""

from __future__ import annotations

from custom_components.vercel.best_practices import audit_project, BestPracticesResult


def _make_project(**overrides) -> dict:
    """Create a project dict with sensible defaults."""
    base = {
        "id": "prj_123",
        "name": "my-app",
        "framework": "nextjs",
        "nodeVersion": "20.x",
        "buildCommand": "next build",
        "rootDirectory": None,
    }
    base.update(overrides)
    return base


def _make_deployments(states: list[str]) -> list[dict]:
    """Create deployment dicts with given states."""
    return [
        {
            "uid": f"dpl_{i}",
            "state": state,
            "created": 1700000000000 + i * 60000,
            "ready": 1700000060000 + i * 60000 if state == "READY" else None,
            "isRollbackCandidate": state == "READY",
        }
        for i, state in enumerate(states)
    ]


def _make_env_vars(types: list[str]) -> list[dict]:
    """Create env var dicts with given types."""
    return [
        {"key": f"VAR_{i}", "type": t, "target": ["production"]}
        for i, t in enumerate(types)
    ]


def test_perfect_project() -> None:
    """Test a project that passes all checks."""
    project = _make_project(framework="nextjs", nodeVersion="20.x")
    deployments = _make_deployments(["READY", "READY", "READY"])
    env_vars = _make_env_vars(["encrypted", "encrypted"])

    result = audit_project(project, deployments, env_vars)
    assert result.score == 100
    assert len(result.issues) == 0


def test_no_framework() -> None:
    """Test project with no framework detected."""
    project = _make_project(framework=None)
    result = audit_project(project, [], [])
    assert result.score < 100
    assert any("framework" in i.lower() for i in result.issues)


def test_old_node_version() -> None:
    """Test project with outdated Node version."""
    project = _make_project(nodeVersion="16.x")
    result = audit_project(project, [], [])
    assert result.score < 100
    assert any("node" in i.lower() for i in result.issues)


def test_plaintext_env_vars() -> None:
    """Test project with plaintext env vars."""
    project = _make_project()
    env_vars = _make_env_vars(["plain", "encrypted", "plain"])
    result = audit_project(project, [], env_vars)
    assert result.score < 100
    assert any("env" in i.lower() or "plain" in i.lower() for i in result.issues)


def test_high_error_rate() -> None:
    """Test project with high deployment error rate."""
    project = _make_project()
    deployments = _make_deployments(["ERROR", "ERROR", "READY", "ERROR", "READY"])
    result = audit_project(project, deployments, [])
    assert result.score < 100
    assert any("error" in i.lower() or "fail" in i.lower() for i in result.issues)


def test_no_rollback_candidate() -> None:
    """Test project with no rollback candidates."""
    project = _make_project()
    deployments = [
        {"uid": "dpl_1", "state": "READY", "created": 1700000000000, "ready": 1700000060000, "isRollbackCandidate": False},
    ]
    result = audit_project(project, deployments, [])
    assert result.score < 100
    assert any("rollback" in i.lower() for i in result.issues)


def test_no_deployments() -> None:
    """Test project with no deployments (stale)."""
    project = _make_project()
    result = audit_project(project, [], [])
    assert result.score < 100
    assert any("deploy" in i.lower() or "stale" in i.lower() for i in result.issues)


def test_result_is_dataclass() -> None:
    """Test BestPracticesResult has expected fields."""
    result = audit_project(_make_project(), [], [])
    assert isinstance(result.score, int)
    assert isinstance(result.issues, list)
    assert 0 <= result.score <= 100
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_best_practices.py -v
```

Expected: FAIL

**Step 3: Implement the best practices module**

Create `custom_components/vercel/best_practices.py`:

```python
"""Best practices audit for Vercel projects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Node versions considered current (20+)
CURRENT_NODE_VERSIONS = {"20.x", "22.x", "24.x"}

# Max acceptable error rate in recent deployments
MAX_ERROR_RATE = 0.3


@dataclass
class BestPracticesResult:
    """Result of a best practices audit."""

    score: int
    issues: list[str] = field(default_factory=list)


def audit_project(
    project: dict[str, Any],
    deployments: list[dict[str, Any]],
    env_vars: list[dict[str, Any]],
) -> BestPracticesResult:
    """Audit a Vercel project against best practices.

    Returns a score from 0–100 and a list of issue descriptions.
    Each check is worth equal weight. Score = (passed / total) * 100.
    """
    checks: list[tuple[bool, str]] = []

    # Check 1: Framework detected
    framework = project.get("framework")
    checks.append((
        framework is not None and framework != "other",
        "No framework detected. Configure a framework for optimized builds.",
    ))

    # Check 2: Modern Node version
    node_version = project.get("nodeVersion", "")
    checks.append((
        node_version in CURRENT_NODE_VERSIONS,
        f"Node version {node_version!r} is outdated. Upgrade to Node 20+ for LTS support.",
    ))

    # Check 3: Environment variable hygiene (no plaintext secrets)
    plaintext_count = sum(1 for e in env_vars if e.get("type") == "plain")
    checks.append((
        plaintext_count == 0,
        f"{plaintext_count} environment variable(s) stored as plaintext. Use encrypted or secret type.",
    ))

    # Check 4: Deployment error rate
    if deployments:
        error_count = sum(1 for d in deployments if d.get("state") == "ERROR")
        error_rate = error_count / len(deployments)
        checks.append((
            error_rate <= MAX_ERROR_RATE,
            f"High deployment failure rate: {error_count}/{len(deployments)} recent deployments failed.",
        ))
    else:
        checks.append((
            False,
            "No recent deployments found. Project may be stale.",
        ))

    # Check 5: Rollback candidate available
    has_rollback = any(d.get("isRollbackCandidate") for d in deployments)
    checks.append((
        has_rollback or len(deployments) == 0,
        "No rollback candidate available. Ensure successful production deployments exist.",
    ))

    # Check 6: Has recent deployments (not stale) — only fails if zero deployments
    checks.append((
        len(deployments) > 0,
        "No deployments found. Deploy your project to get started.",
    ))

    # Calculate score
    passed = sum(1 for ok, _ in checks if ok)
    total = len(checks)
    score = round((passed / total) * 100) if total > 0 else 0

    issues = [msg for ok, msg in checks if not ok]

    return BestPracticesResult(score=score, issues=issues)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_best_practices.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add custom_components/vercel/best_practices.py tests/test_best_practices.py
git commit -m "feat: add best practices audit module with tests"
```

---

## Task 7: Base Entity

**Files:**
- Create: `custom_components/vercel/entity.py`

**Step 1: Create the base entity classes**

Create `custom_components/vercel/entity.py`:

```python
"""Base entities for the Vercel integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN


class VercelProjectEntity(CoordinatorEntity):
    """Base entity for a Vercel project (device)."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        project_id: str,
        project_name: str,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._project_id = project_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{project_id}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_{project_id}")},
            name=project_name,
            manufacturer="Vercel",
            model="Project",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://vercel.com/~/projects/{project_name}",
        )


class VercelAccountEntity(CoordinatorEntity):
    """Base entity for the Vercel account (device)."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_account_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_account")},
            name=coordinator.config_entry.title,
            manufacturer="Vercel",
            model="Account",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://vercel.com/dashboard",
        )
```

**Step 2: Commit**

```bash
git add custom_components/vercel/entity.py
git commit -m "feat: add base entity classes for projects and accounts"
```

---

## Task 8: Sensor Platform

**Files:**
- Create: `custom_components/vercel/sensor.py`
- Create: `custom_components/vercel/icons.json`
- Create: `tests/test_sensor.py`

**Step 1: Write the failing sensor tests**

Create `tests/test_sensor.py`:

```python
"""Tests for the Vercel sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vercel.const import DOMAIN


def _mock_project_coordinator_data():
    """Return mock project coordinator data."""
    return {
        "projects": {
            "prj_123": {
                "id": "prj_123",
                "name": "my-app",
                "framework": "nextjs",
                "nodeVersion": "20.x",
                "updatedAt": 1700000000000,
            },
        },
        "domains": {
            "example.com": {
                "name": "example.com",
                "verified": True,
                "misconfigured": False,
                "configuredBy": "CNAME",
            },
        },
        "env_vars": {
            "prj_123": [
                {"key": "DB_URL", "type": "encrypted", "target": ["production"]},
            ],
        },
    }


def _mock_deployment_coordinator_data():
    """Return mock deployment coordinator data."""
    return {
        "prj_123": [
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
            },
        ],
    }


async def test_sensor_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test sensor platform creates entities."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.vercel.api.VercelApiClient"
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.async_get_user = AsyncMock(return_value={"id": "user_abc"})
        client.async_get_projects = AsyncMock(
            return_value=[
                {"id": "prj_123", "name": "my-app", "framework": "nextjs", "nodeVersion": "20.x", "updatedAt": 1700000000000},
            ]
        )
        client.async_get_deployments = AsyncMock(
            return_value=[
                {
                    "uid": "dpl_abc", "name": "my-app", "state": "READY",
                    "target": "production", "created": 1700000000000,
                    "ready": 1700000060000, "source": "git",
                    "url": "my-app-abc.vercel.app",
                    "inspectorUrl": "https://vercel.com/team/my-app/dpl_abc",
                    "creator": {"username": "testuser"},
                    "meta": {"githubCommitMessage": "fix: bug"},
                    "isRollbackCandidate": True,
                },
            ]
        )
        client.async_get_domains = AsyncMock(
            return_value=[{"name": "example.com", "verified": True, "expiresAt": None, "renew": True}]
        )
        client.async_get_domain_config = AsyncMock(
            return_value={"configuredBy": "CNAME", "misconfigured": False}
        )
        client.async_get_project_env_vars = AsyncMock(
            return_value=[{"key": "DB_URL", "type": "encrypted", "target": ["production"]}]
        )

        with patch(
            "custom_components.vercel.VercelApiClient",
            return_value=client,
        ):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

    # Check that project-level sensors exist
    state = hass.states.get("sensor.my_app_deployment_status")
    assert state is not None
    assert state.state == "ready"

    state = hass.states.get("sensor.my_app_framework")
    assert state is not None
    assert state.state == "nextjs"

    state = hass.states.get("sensor.my_app_best_practices_score")
    assert state is not None
    # Score should be an integer between 0-100
    assert 0 <= int(state.state) <= 100

    # Check account-level sensors
    account_title = mock_config_entry.title.lower().replace(" ", "_").replace("(", "").replace(")", "")
    state = hass.states.get(f"sensor.{account_title}_total_projects")
    assert state is not None
    assert state.state == "1"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_sensor.py -v
```

Expected: FAIL

**Step 3: Implement the sensor platform**

Create `custom_components/vercel/sensor.py`:

```python
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
```

**Step 4: Create `custom_components/vercel/icons.json`**

```json
{
  "entity": {
    "sensor": {
      "deployment_status": {
        "default": "mdi:rocket-launch",
        "state": {
          "ready": "mdi:check-circle",
          "building": "mdi:hammer-wrench",
          "error": "mdi:alert-circle",
          "queued": "mdi:clock-outline",
          "canceled": "mdi:cancel",
          "initializing": "mdi:loading"
        }
      },
      "deployment_url": {
        "default": "mdi:link-variant"
      },
      "build_duration": {
        "default": "mdi:timer-outline"
      },
      "deployment_source": {
        "default": "mdi:source-branch"
      },
      "active_deployments": {
        "default": "mdi:counter"
      },
      "failed_deployments_24h": {
        "default": "mdi:alert-octagon"
      },
      "framework": {
        "default": "mdi:application-brackets-outline"
      },
      "node_version": {
        "default": "mdi:nodejs"
      },
      "domain_count": {
        "default": "mdi:earth"
      },
      "best_practices_score": {
        "default": "mdi:clipboard-check-outline"
      },
      "best_practices_issues": {
        "default": "mdi:clipboard-alert-outline"
      },
      "total_projects": {
        "default": "mdi:folder-multiple"
      },
      "total_domains": {
        "default": "mdi:earth"
      }
    },
    "binary_sensor": {
      "domain_healthy": {
        "default": "mdi:heart-pulse"
      },
      "ssl_valid": {
        "default": "mdi:shield-check"
      },
      "domain_misconfigured": {
        "default": "mdi:alert-rhombus"
      }
    }
  }
}
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_sensor.py -v
```

Expected: ALL PASS

**Step 6: Commit**

```bash
git add custom_components/vercel/sensor.py custom_components/vercel/icons.json tests/test_sensor.py
git commit -m "feat: add sensor platform with project and account sensors"
```

---

## Task 9: Binary Sensor Platform

**Files:**
- Create: `custom_components/vercel/binary_sensor.py`
- Create: `tests/test_binary_sensor.py`

**Step 1: Write the failing tests**

Create `tests/test_binary_sensor.py`:

```python
"""Tests for the Vercel binary sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vercel.const import DOMAIN


async def test_domain_binary_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test domain binary sensors are created."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.vercel.api.VercelApiClient") as mock_cls:
        client = mock_cls.return_value
        client.async_get_user = AsyncMock(return_value={"id": "user_abc"})
        client.async_get_projects = AsyncMock(return_value=[
            {"id": "prj_123", "name": "my-app", "framework": "nextjs", "nodeVersion": "20.x", "updatedAt": 1700000000000},
        ])
        client.async_get_deployments = AsyncMock(return_value=[
            {"uid": "dpl_abc", "state": "READY", "target": "production",
             "created": 1700000000000, "ready": 1700000060000,
             "source": "git", "url": "my-app.vercel.app",
             "inspectorUrl": "", "creator": {"username": "test"},
             "meta": {}, "isRollbackCandidate": True},
        ])
        client.async_get_domains = AsyncMock(return_value=[
            {"name": "example.com", "verified": True, "expiresAt": None, "renew": True},
        ])
        client.async_get_domain_config = AsyncMock(return_value={
            "configuredBy": "CNAME", "misconfigured": False,
        })
        client.async_get_project_env_vars = AsyncMock(return_value=[])

        with patch("custom_components.vercel.VercelApiClient", return_value=client):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

    # Domain healthy
    state = hass.states.get("binary_sensor.example_com_domain_healthy")
    assert state is not None
    assert state.state == "on"

    # Domain misconfigured
    state = hass.states.get("binary_sensor.example_com_domain_misconfigured")
    assert state is not None
    assert state.state == "off"  # not misconfigured = off
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_binary_sensor.py -v
```

Expected: FAIL

**Step 3: Implement the binary sensor platform**

Create `custom_components/vercel/binary_sensor.py`:

```python
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
        value_fn=lambda d: d.get("verified", False) and d.get("configuredBy") is not None,
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

    for domain_name, domain_data in project_coord.data.get("domains", {}).items():
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


class VercelDomainBinarySensor(CoordinatorEntity[VercelProjectCoordinator], BinarySensorEntity):
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
        domain_data = self.coordinator.data.get("domains", {}).get(self._domain_name, {})
        return self.entity_description.value_fn(domain_data)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_binary_sensor.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add custom_components/vercel/binary_sensor.py tests/test_binary_sensor.py
git commit -m "feat: add binary sensor platform for domain health"
```

---

## Task 10: Integration Entry Point (`__init__.py`)

**Files:**
- Modify: `custom_components/vercel/__init__.py`
- Create: `tests/test_init.py`

**Step 1: Write the failing tests**

Create `tests/test_init.py`:

```python
"""Tests for the Vercel integration setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vercel.const import DOMAIN


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test successful setup of a config entry."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.vercel.api.VercelApiClient") as mock_cls:
        client = mock_cls.return_value
        client.async_get_user = AsyncMock(return_value={"id": "user_abc"})
        client.async_get_projects = AsyncMock(return_value=[
            {"id": "prj_123", "name": "my-app", "framework": "nextjs", "nodeVersion": "20.x", "updatedAt": 1700000000000},
        ])
        client.async_get_deployments = AsyncMock(return_value=[])
        client.async_get_domains = AsyncMock(return_value=[])
        client.async_get_domain_config = AsyncMock(return_value={"misconfigured": False, "configuredBy": "CNAME"})
        client.async_get_project_env_vars = AsyncMock(return_value=[])

        with patch("custom_components.vercel.VercelApiClient", return_value=client):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test unloading a config entry."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.vercel.api.VercelApiClient") as mock_cls:
        client = mock_cls.return_value
        client.async_get_user = AsyncMock(return_value={"id": "user_abc"})
        client.async_get_projects = AsyncMock(return_value=[])
        client.async_get_deployments = AsyncMock(return_value=[])
        client.async_get_domains = AsyncMock(return_value=[])
        client.async_get_domain_config = AsyncMock(return_value={})
        client.async_get_project_env_vars = AsyncMock(return_value=[])

        with patch("custom_components.vercel.VercelApiClient", return_value=client):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

            result = await hass.config_entries.async_unload(mock_config_entry.entry_id)

    assert result is True
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_init.py -v
```

Expected: FAIL

**Step 3: Implement `__init__.py`**

Replace `custom_components/vercel/__init__.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_init.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add custom_components/vercel/__init__.py tests/test_init.py
git commit -m "feat: implement integration entry point with setup/unload"
```

---

## Task 11: Diagnostics

**Files:**
- Create: `custom_components/vercel/diagnostics.py`
- Create: `tests/test_diagnostics.py`

**Step 1: Write the failing test**

Create `tests/test_diagnostics.py`:

```python
"""Tests for the Vercel diagnostics platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vercel.const import DOMAIN
from custom_components.vercel.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redacts_token(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that diagnostics redacts the API token."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.vercel.api.VercelApiClient") as mock_cls:
        client = mock_cls.return_value
        client.async_get_projects = AsyncMock(return_value=[])
        client.async_get_deployments = AsyncMock(return_value=[])
        client.async_get_domains = AsyncMock(return_value=[])
        client.async_get_domain_config = AsyncMock(return_value={})
        client.async_get_project_env_vars = AsyncMock(return_value=[])

        with patch("custom_components.vercel.VercelApiClient", return_value=client):
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert "entry_data" in diag
    assert diag["entry_data"]["api_token"] == "**REDACTED**"
    assert "project_data" in diag
    assert "deployment_data" in diag
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_diagnostics.py -v
```

Expected: FAIL

**Step 3: Implement diagnostics**

Create `custom_components/vercel/diagnostics.py`:

```python
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
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_diagnostics.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/vercel/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: add diagnostics with token redaction"
```

---

## Task 12: Translations

**Files:**
- Create: `custom_components/vercel/translations/en.json`

**Step 1: Create `custom_components/vercel/translations/en.json`**

This is a copy of `strings.json` (HA generates translations from strings.json, but for custom integrations you need both):

```bash
mkdir -p custom_components/vercel/translations
cp custom_components/vercel/strings.json custom_components/vercel/translations/en.json
```

**Step 2: Commit**

```bash
git add custom_components/vercel/translations/en.json
git commit -m "feat: add English translations"
```

---

## Task 13: Full Test Suite Run and Cleanup

**Step 1: Run the full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: ALL PASS

**Step 2: If any failures, fix them**

Address any import errors, missing mocks, or assertion failures.

**Step 3: Run ruff linter**

```bash
pip install ruff
ruff check custom_components/ tests/
ruff format custom_components/ tests/
```

**Step 4: Fix any linting issues and commit**

```bash
git add -A
git commit -m "chore: fix linting and format code"
```

---

## Task 14: Create LICENSE and Final Commit

**Step 1: Create LICENSE (MIT)**

```
MIT License

Copyright (c) 2026 Nathan Owen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**Step 2: Final commit**

```bash
git add LICENSE
git commit -m "chore: add MIT license"
```

**Step 3: Verify everything**

```bash
pytest tests/ -v
ruff check custom_components/ tests/
```

Expected: ALL PASS, no lint errors.

---

## Summary of All Tasks

| Task | Description | Files Created/Modified |
|------|-------------|----------------------|
| 1 | Project scaffolding | `.gitignore`, `const.py`, `manifest.json`, `__init__.py`, `hacs.json`, `pyproject.toml`, `requirements_test.txt`, CI workflow |
| 2 | Vercel API client | `api.py`, `conftest.py`, `test_api.py` |
| 3 | Runtime data types | `data.py` |
| 4 | Coordinators | `coordinator.py`, `test_coordinator.py` |
| 5 | Config flow | `config_flow.py`, `strings.json`, `test_config_flow.py` |
| 6 | Best practices audit | `best_practices.py`, `test_best_practices.py` |
| 7 | Base entity | `entity.py` |
| 8 | Sensor platform | `sensor.py`, `icons.json`, `test_sensor.py` |
| 9 | Binary sensor platform | `binary_sensor.py`, `test_binary_sensor.py` |
| 10 | Integration entry point | `__init__.py` (full impl), `test_init.py` |
| 11 | Diagnostics | `diagnostics.py`, `test_diagnostics.py` |
| 12 | Translations | `translations/en.json` |
| 13 | Full test run + lint | cleanup |
| 14 | LICENSE + final verify | `LICENSE` |
