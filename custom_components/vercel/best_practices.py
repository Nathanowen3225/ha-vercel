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

    Returns a score from 0-100 and a list of issue descriptions.
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

    # Check 6: Has recent deployments (not stale) - only fails if zero deployments
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
