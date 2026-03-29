"""Validate every task.toml in benchmarks/ against schema and structural rules.

Each task directory must contain:
- task.toml that validates against schemas/task.schema.json
- ground_truth.json (valid JSON)
- instruction.md
- All check scripts referenced by checkpoints (and executable)
- Checkpoint weights summing to 1.0
"""

from __future__ import annotations

import json
import os
import stat
import tomllib
import warnings
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "schemas" / "task.schema.json"
BENCHMARKS_DIR = ROOT / "benchmarks"


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def _collect_task_dirs() -> list[Path]:
    """Find all task.toml files, excluding mined/ and EXAMPLE_*.toml."""
    tasks: list[Path] = []
    for toml_path in sorted(BENCHMARKS_DIR.rglob("task.toml")):
        # Skip mined/ directory
        rel = toml_path.relative_to(BENCHMARKS_DIR)
        if rel.parts[0] in ("mined", "_archived"):
            continue
        tasks.append(toml_path.parent)
    return tasks


TASK_DIRS = _collect_task_dirs()
TASK_IDS = [str(d.relative_to(BENCHMARKS_DIR)) for d in TASK_DIRS]


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return _load_schema()


@pytest.fixture(scope="module")
def validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema)


# -- parametrize over discovered tasks --


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=TASK_IDS)
class TestTaskValid:
    """Validate a single task directory."""

    @staticmethod
    def _load_toml(task_dir: Path) -> dict[str, Any]:
        with open(task_dir / "task.toml", "rb") as f:
            return tomllib.load(f)

    def test_schema_valid(self, task_dir: Path, validator: Draft202012Validator) -> None:
        """task.toml validates against task.schema.json."""
        task = self._load_toml(task_dir)
        errors = [e.message for e in validator.iter_errors(task)]
        assert errors == [], f"Schema errors: {errors}"

    def test_checkpoint_weights_sum(self, task_dir: Path) -> None:
        """Checkpoint weights must sum to 1.0 (within 0.01 tolerance)."""
        task = self._load_toml(task_dir)
        checkpoints = task.get("checkpoints", [])
        total = sum(cp["weight"] for cp in checkpoints)
        assert abs(total - 1.0) < 0.01, (
            f"Checkpoint weights sum to {total}, expected 1.0"
        )

    def test_ground_truth_json_exists(self, task_dir: Path) -> None:
        """ground_truth.json must exist and be valid JSON."""
        gt_path = task_dir / "ground_truth.json"
        assert gt_path.exists(), f"Missing ground_truth.json in {task_dir.name}"
        content = gt_path.read_text()
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Invalid JSON in ground_truth.json: {exc}")

    def test_instruction_md_exists(self, task_dir: Path) -> None:
        """instruction.md must exist."""
        assert (task_dir / "instruction.md").exists(), (
            f"Missing instruction.md in {task_dir.name}"
        )

    def test_check_scripts_exist_and_executable(self, task_dir: Path) -> None:
        """All checkpoint verifier scripts must exist and be executable."""
        task = self._load_toml(task_dir)
        missing = []
        not_exec = []
        for cp in task.get("checkpoints", []):
            script = task_dir / cp["verifier"]
            if not script.exists():
                missing.append(cp["verifier"])
            elif not os.access(script, os.X_OK):
                not_exec.append(cp["verifier"])
        errors = []
        if missing:
            errors.append(f"Missing scripts: {missing}")
        if not_exec:
            errors.append(f"Not executable: {not_exec}")
        assert not errors, "; ".join(errors)

    def test_task_type_present(self, task_dir: Path) -> None:
        """task_type should be present (warning only, does not fail)."""
        task = self._load_toml(task_dir)
        task_block = task.get("task", {})
        if "task_type" not in task_block:
            warnings.warn(
                f"{task_dir.name}: missing task_type field",
                stacklevel=1,
            )
