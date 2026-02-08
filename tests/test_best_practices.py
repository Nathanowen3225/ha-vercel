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
