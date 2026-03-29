"""Schema coverage tests — one synthetic minimal task per task type.

Validates that schemas/task.schema.json can represent all 10 task types
defined in docs/TASK_TYPE_PRD.md.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "task.schema.json"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "task_types"

# ── helpers ──────────────────────────────────────────────────────────────────

def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def _validate(task: dict[str, Any]) -> list[str]:
    """Return list of validation error messages (empty = valid)."""
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    return [e.message for e in validator.iter_errors(task)]


# ── minimal task builders ────────────────────────────────────────────────────

def _base(
    task_id: str,
    suite: str,
    task_type: str,
    *,
    difficulty: str = "hard",
    session_type: str = "single",
    multi_repo_pattern: str = "propagate",
    artifacts_required: list[str] | None = None,
    difficulty_stratum: str = "dual_repo",
    repos: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a minimal valid task dict."""
    if artifacts_required is None:
        artifacts_required = ["answer"]
    if repos is None:
        repos = [
            {"url": "github.com/org/repo-a", "rev": "v1.0.0", "path": "repo-a", "role": "primary"},
            {"url": "github.com/org/repo-b", "rev": "v2.0.0", "path": "repo-b", "role": "dependency"},
        ]
    return {
        "task": {
            "id": task_id,
            "suite": suite,
            "difficulty": difficulty,
            "session_type": session_type,
            "task_type": task_type,
            "description": f"Synthetic task for {task_type}",
            "prompt": f"Perform {task_type} analysis.",
        },
        "repos": repos,
        "metadata": {
            "languages": ["go"],
            "multi_repo_pattern": multi_repo_pattern,
        },
        "checkpoints": [
            {"name": "step_one", "weight": 0.6, "verifier": "checks/check_one.sh"},
            {"name": "step_two", "weight": 0.4, "verifier": "checks/check_two.sh"},
        ],
        "artifacts": {"required": artifacts_required},
        "difficulty_stratum": difficulty_stratum,
        "ground_truth": {
            "tiers": ["deterministic"],
            "required_files": [
                {"path": "src/main.go", "repo": "repo-a"},
            ],
        },
    }


# ── fixtures (one per task type) ─────────────────────────────────────────────

TASK_TYPE_FIXTURES: dict[str, dict[str, Any]] = {
    "api_contract": _base(
        "api-contract-proto-rename-001",
        "dependency_management",
        "api_contract",
        multi_repo_pattern="propagate",
        artifacts_required=["answer"],
    ),
    "refactor_orchestration": _base(
        "refactor-orch-grpc-bump-001",
        "technical_debt",
        "refactor_orchestration",
        multi_repo_pattern="orchestrate",
        artifacts_required=["answer"],
        repos=[
            {"url": "github.com/grpc/grpc-go", "rev": "v1.59.0", "path": "grpc-go", "role": "dependency"},
            {"url": "github.com/etcd-io/etcd", "rev": "v3.5.10", "path": "etcd", "role": "primary"},
            {"url": "github.com/kubernetes/kubernetes", "rev": "v1.29.0", "path": "kubernetes", "role": "consumer"},
        ],
        difficulty_stratum="multi_repo",
    ),
    "dependency_graph": _base(
        "dep-graph-cve-trace-001",
        "dependency_management",
        "dependency_graph",
        multi_repo_pattern="investigate",
        artifacts_required=["answer", "security_assessment"],
    ),
    "monorepo_boundary": _base(
        "monorepo-boundary-babel-001",
        "feature_delivery",
        "monorepo_boundary",
        multi_repo_pattern="enforce",
        artifacts_required=["answer"],
        repos=[
            {"url": "github.com/babel/babel", "rev": "v7.23.0", "path": "babel", "role": "primary"},
        ],
        difficulty_stratum="monorepo_cross_package",
    ),
    "db_schema_evolution": _base(
        "db-schema-add-column-001",
        "feature_delivery",
        "db_schema_evolution",
        multi_repo_pattern="propagate",
        artifacts_required=["answer"],
    ),
    "error_provenance": _base(
        "error-trace-500-login-001",
        "customer_escalation",
        "error_provenance",
        multi_repo_pattern="investigate",
        artifacts_required=["answer"],
    ),
    "support_code_mapping": _base(
        "support-map-timeout-001",
        "customer_escalation",
        "support_code_mapping",
        multi_repo_pattern="investigate",
        artifacts_required=["answer"],
        difficulty="medium",
        difficulty_stratum="calibration",
        repos=[
            {"url": "github.com/org/repo-a", "rev": "v1.0.0", "path": "repo-a", "role": "primary"},
        ],
    ),
    "dead_code_necropsy": _base(
        "dead-code-flag-cleanup-001",
        "technical_debt",
        "dead_code_necropsy",
        multi_repo_pattern="investigate",
        artifacts_required=["answer"],
        difficulty_stratum="large_single",
    ),
    "incident_investigation": _base(
        "incident-inv-oom-crash-001",
        "incident_response",
        "incident_investigation",
        multi_repo_pattern="investigate",
        artifacts_required=["incident_report"],
    ),
    "config_drift": _base(
        "config-drift-env-mismatch-001",
        "platform_engineering",
        "config_drift",
        multi_repo_pattern="investigate",
        artifacts_required=["answer"],
    ),
}


# ── tests ────────────────────────────────────────────────────────────────────

class TestAllTaskTypesValid:
    """Every task type fixture must pass JSON Schema validation."""

    @pytest.mark.parametrize("task_type", sorted(TASK_TYPE_FIXTURES))
    def test_fixture_validates(self, task_type: str) -> None:
        task = TASK_TYPE_FIXTURES[task_type]
        errors = _validate(task)
        assert errors == [], f"{task_type} failed validation: {errors}"

    def test_all_ten_types_covered(self) -> None:
        schema = _load_schema()
        schema_types = set(
            schema["properties"]["task"]["properties"]["task_type"]["enum"]
        )
        fixture_types = set(TASK_TYPE_FIXTURES)
        assert fixture_types == schema_types, (
            f"Missing fixtures: {schema_types - fixture_types}, "
            f"Extra fixtures: {fixture_types - schema_types}"
        )


class TestTaskTypeFieldConstraints:
    """Verify task_type enum rejects unknown values."""

    def test_unknown_task_type_rejected(self) -> None:
        task = _base(
            "bad-type-test-001",
            "dependency_management",
            "nonexistent_type",
        )
        errors = _validate(task)
        assert any("nonexistent_type" in e for e in errors)


class TestTaskTypeSuiteMapping:
    """Verify each task type uses the correct PRD suite."""

    EXPECTED_SUITE: dict[str, str] = {
        "api_contract": "dependency_management",
        "refactor_orchestration": "technical_debt",
        "dependency_graph": "dependency_management",
        "monorepo_boundary": "feature_delivery",
        "db_schema_evolution": "feature_delivery",
        "error_provenance": "customer_escalation",
        "support_code_mapping": "customer_escalation",
        "dead_code_necropsy": "technical_debt",
        "incident_investigation": "incident_response",
        "config_drift": "platform_engineering",
    }

    @pytest.mark.parametrize("task_type,expected_suite", EXPECTED_SUITE.items())
    def test_suite_matches_prd(self, task_type: str, expected_suite: str) -> None:
        task = TASK_TYPE_FIXTURES[task_type]
        assert task["task"]["suite"] == expected_suite


class TestTaskTypeArtifacts:
    """Verify each task type declares the required artifacts from the PRD."""

    EXPECTED_ARTIFACTS: dict[str, list[str]] = {
        "api_contract": ["answer"],
        "refactor_orchestration": ["answer"],
        "dependency_graph": ["answer", "security_assessment"],
        "monorepo_boundary": ["answer"],
        "db_schema_evolution": ["answer"],
        "error_provenance": ["answer"],
        "support_code_mapping": ["answer"],
        "dead_code_necropsy": ["answer"],
        "incident_investigation": ["incident_report"],
        "config_drift": ["answer"],
    }

    @pytest.mark.parametrize("task_type,expected_artifacts", EXPECTED_ARTIFACTS.items())
    def test_artifacts_match_prd(self, task_type: str, expected_artifacts: list[str]) -> None:
        task = TASK_TYPE_FIXTURES[task_type]
        assert sorted(task["artifacts"]["required"]) == sorted(expected_artifacts)


class TestTaskTypeMultiRepoPatterns:
    """Verify each task type uses the correct multi-repo pattern."""

    EXPECTED_PATTERN: dict[str, str] = {
        "api_contract": "propagate",
        "refactor_orchestration": "orchestrate",
        "dependency_graph": "investigate",
        "monorepo_boundary": "enforce",
        "db_schema_evolution": "propagate",
        "error_provenance": "investigate",
        "support_code_mapping": "investigate",
        "dead_code_necropsy": "investigate",
        "incident_investigation": "investigate",
        "config_drift": "investigate",
    }

    @pytest.mark.parametrize("task_type,expected_pattern", EXPECTED_PATTERN.items())
    def test_pattern_matches_prd(self, task_type: str, expected_pattern: str) -> None:
        task = TASK_TYPE_FIXTURES[task_type]
        assert task["metadata"]["multi_repo_pattern"] == expected_pattern


class TestDifficultyStratumCoverage:
    """Verify that fixture set covers all difficulty strata."""

    def test_all_strata_represented(self) -> None:
        strata = {t["difficulty_stratum"] for t in TASK_TYPE_FIXTURES.values()}
        required_strata = {
            "calibration",
            "large_single",
            "dual_repo",
            "multi_repo",
            "monorepo_cross_package",
        }
        missing = required_strata - strata
        assert not missing, f"No fixture covers strata: {missing}"


class TestExistingFixturesStillValid:
    """Ensure schema extension doesn't break existing fixtures."""

    def test_example_task(self) -> None:
        example = Path(__file__).parent.parent / "benchmarks" / "EXAMPLE_TASK.toml"
        with open(example, "rb") as f:
            task = tomllib.load(f)
        errors = _validate(task)
        assert errors == [], f"EXAMPLE_TASK.toml broke after schema patch: {errors}"

    def test_valid_task_fixture(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "valid_task.toml"
        with open(fixture, "rb") as f:
            task = tomllib.load(f)
        errors = _validate(task)
        assert errors == [], f"valid_task.toml broke after schema patch: {errors}"
