"""Tests for scripts/validate_tasks_preflight.py.

Tests the validation logic with synthetic task fixtures to ensure
each check correctly identifies issues.
"""

from __future__ import annotations

import json
import os
import stat
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Import from the script under test
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import validate_tasks_preflight as vtp

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_benchmarks(tmp_path: Path) -> Path:
    """Create a minimal benchmarks directory structure."""
    return tmp_path / "benchmarks"


@pytest.fixture()
def minimal_task_toml() -> str:
    """A valid task.toml content as a TOML string."""
    return textwrap.dedent("""\
        difficulty_stratum = "dual_repo"
        mcp_suite = "eb_v1"
        repo_set_id = "test-ecosystem"
        org_scale = true
        verification_modes = ["deterministic"]

        [task]
        id = "test-task-001"
        suite = "customer_escalation"
        difficulty = "hard"
        session_type = "single"
        description = "Test task"
        prompt = "Do the thing."

        [[repos]]
        url = "https://github.com/test/repo"
        rev = "v1.0.0"
        path = "repo"

        [[checkpoints]]
        name = "check_one"
        weight = 0.60
        verifier = "checks/check_one.sh"
        description = "First check"

        [[checkpoints]]
        name = "check_two"
        weight = 0.40
        verifier = "checks/check_two.sh"
        description = "Second check"

        [artifacts]
        required = ["answer"]

        [tool_access]
        expected_mcp_benefit = "high"
        mcp_benefit_rationale = "Test rationale"
        sourcegraph_mirror_config = "configs/sg_mirrors/test-task-001.json"

        [ground_truth]
        tiers = ["deterministic"]

        [[ground_truth.required_files]]
        path = "src/main.go"
        repo = "repo"
        confidence = 0.95
        source = "deterministic"
    """)


def _create_task_dir(
    benchmarks: Path,
    suite: str,
    task_name: str,
    toml_content: str,
    *,
    create_instruction: bool = True,
    create_ground_truth: bool = True,
    create_checks: bool = True,
    create_environment: bool = True,
    ground_truth_data: dict[str, Any] | None = None,
) -> Path:
    """Helper to create a complete task directory."""
    task_dir = benchmarks / suite / task_name
    task_dir.mkdir(parents=True, exist_ok=True)

    # task.toml
    (task_dir / "task.toml").write_text(toml_content)

    # instruction.md
    if create_instruction:
        (task_dir / "instruction.md").write_text("# Test instruction\n")

    # ground_truth.json
    if create_ground_truth:
        gt_data = (
            ground_truth_data
            if ground_truth_data is not None
            else {
                "ground_truth": {
                    "required_files": [{"path": "src/main.go", "repo": "repo"}]
                }
            }
        )
        (task_dir / "ground_truth.json").write_text(json.dumps(gt_data))

    # checks directory with scripts
    if create_checks:
        checks_dir = task_dir / "checks"
        checks_dir.mkdir(exist_ok=True)
        for script_name in ["check_one.sh", "check_two.sh"]:
            script = checks_dir / script_name
            script.write_text("#!/bin/bash\nexit 0\n")
            script.chmod(script.stat().st_mode | stat.S_IEXEC)

    # environment with Dockerfiles
    if create_environment:
        env_dir = task_dir / "environment"
        env_dir.mkdir(exist_ok=True)
        (env_dir / "Dockerfile").write_text("FROM python:3.11\n")
        (env_dir / "Dockerfile.hybrid").write_text("FROM python:3.11\n")
        (env_dir / "Dockerfile.sg_only").write_text("FROM python:3.11\n")

    return task_dir


def _validate(
    task_dir: Path,
    sg_index: dict[str, bool] | None = None,
    mirror_task_ids: set[str] | None = None,
) -> vtp.TaskValidation:
    """Convenience wrapper that infers benchmarks_dir from task_dir structure."""
    # task_dir is benchmarks/suite/task_name, so grandparent is benchmarks
    benchmarks_dir = task_dir.parent.parent
    return vtp.validate_task(
        task_dir,
        None,
        None,
        sg_index or {},
        mirror_task_ids or set(),
        benchmarks_dir=benchmarks_dir,
    )


# ---------------------------------------------------------------------------
# Tests for collect_task_dirs
# ---------------------------------------------------------------------------


class TestCollectTaskDirs:
    def test_excludes_archived(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        _create_task_dir(tmp_benchmarks, "_archived", "old-task", minimal_task_toml)
        _create_task_dir(
            tmp_benchmarks, "customer_escalation", "good-task", minimal_task_toml
        )

        with patch.object(vtp, "BENCHMARKS_DIR", tmp_benchmarks):
            dirs = vtp.collect_task_dirs()
        assert len(dirs) == 1
        assert dirs[0].name == "good-task"

    def test_excludes_mined(self, tmp_benchmarks: Path, minimal_task_toml: str) -> None:
        _create_task_dir(tmp_benchmarks, "mined", "candidate", minimal_task_toml)
        _create_task_dir(
            tmp_benchmarks, "customer_escalation", "real-task", minimal_task_toml
        )

        with patch.object(vtp, "BENCHMARKS_DIR", tmp_benchmarks):
            dirs = vtp.collect_task_dirs()
        assert len(dirs) == 1

    def test_suite_filter(self, tmp_benchmarks: Path, minimal_task_toml: str) -> None:
        _create_task_dir(
            tmp_benchmarks, "customer_escalation", "task-a", minimal_task_toml
        )
        _create_task_dir(tmp_benchmarks, "technical_debt", "task-b", minimal_task_toml)

        with patch.object(vtp, "BENCHMARKS_DIR", tmp_benchmarks):
            dirs = vtp.collect_task_dirs(suite_filter="technical_debt")
        assert len(dirs) == 1
        assert dirs[0].name == "task-b"

    def test_task_id_filter(self, tmp_benchmarks: Path, minimal_task_toml: str) -> None:
        _create_task_dir(
            tmp_benchmarks, "customer_escalation", "task-a", minimal_task_toml
        )
        _create_task_dir(
            tmp_benchmarks, "customer_escalation", "task-b", minimal_task_toml
        )

        with patch.object(vtp, "BENCHMARKS_DIR", tmp_benchmarks):
            dirs = vtp.collect_task_dirs(task_id_filter="task-a")
        assert len(dirs) == 1
        assert dirs[0].name == "task-a"


# ---------------------------------------------------------------------------
# Tests for validate_task
# ---------------------------------------------------------------------------


class TestValidateTask:
    def test_fully_valid_task(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "good-task", minimal_task_toml
        )
        result = _validate(task_dir)
        # Should be ready (no errors, only warnings for schema/mirror)
        assert result.ready
        assert result.has_instruction
        assert result.has_ground_truth
        assert result.weights_valid
        assert result.scripts_valid
        assert result.has_environment_dir
        assert result.has_dockerfile
        assert result.has_dockerfile_hybrid

    def test_missing_instruction(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "no-instruction",
            minimal_task_toml,
            create_instruction=False,
        )
        result = _validate(task_dir)
        assert not result.ready
        assert not result.has_instruction
        assert any(i.check == "instruction" for i in result.issues)

    def test_missing_ground_truth(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "no-gt",
            minimal_task_toml,
            create_ground_truth=False,
        )
        result = _validate(task_dir)
        assert not result.ready
        assert not result.has_ground_truth

    def test_empty_ground_truth(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "empty-gt",
            minimal_task_toml,
            ground_truth_data={},
        )
        result = _validate(task_dir)
        assert not result.ready
        assert any(
            i.check == "ground_truth" and "empty" in i.message for i in result.issues
        )

    def test_missing_check_scripts(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "no-checks",
            minimal_task_toml,
            create_checks=False,
        )
        result = _validate(task_dir)
        assert not result.ready
        assert not result.scripts_valid

    def test_no_environment_dir(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "no-env",
            minimal_task_toml,
            create_environment=False,
        )
        result = _validate(task_dir)
        # Environment is a warning, not an error
        assert result.ready
        assert not result.has_environment_dir
        assert any(i.check == "environment" for i in result.issues)

    def test_bad_checkpoint_weights(self, tmp_benchmarks: Path) -> None:
        bad_toml = textwrap.dedent("""\
            difficulty_stratum = "dual_repo"
            mcp_suite = "eb_v1"
            repo_set_id = "test-ecosystem"
            org_scale = true
            verification_modes = ["deterministic"]

            [task]
            id = "test-weights-001"
            suite = "customer_escalation"
            difficulty = "hard"
            session_type = "single"
            prompt = "test"

            [[repos]]
            url = "https://github.com/test/repo"
            rev = "v1.0.0"
            path = "repo"

            [[checkpoints]]
            name = "check_one"
            weight = 0.30
            verifier = "checks/check_one.sh"

            [[checkpoints]]
            name = "check_two"
            weight = 0.30
            verifier = "checks/check_two.sh"

            [artifacts]
            required = ["answer"]

            [tool_access]
            expected_mcp_benefit = "high"
            mcp_benefit_rationale = "test"

            [ground_truth]
            tiers = ["deterministic"]

            [[ground_truth.required_files]]
            path = "src/main.go"
            repo = "repo"
        """)
        task_dir = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "bad-weights", bad_toml
        )
        result = _validate(task_dir)
        assert not result.ready
        assert not result.weights_valid
        assert any(i.check == "weights" for i in result.issues)

    def test_mirror_config_by_task_id(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "mirror-test", minimal_task_toml
        )
        # Task ID in toml is "test-task-001"
        result = _validate(task_dir, mirror_task_ids={"test-task-001"})
        assert result.has_mirror_config

    def test_missing_top_level_fields(self, tmp_benchmarks: Path) -> None:
        # toml without mcp_suite, verification_modes
        bare_toml = textwrap.dedent("""\
            difficulty_stratum = "dual_repo"

            [task]
            id = "bare-task-001"
            suite = "customer_escalation"
            difficulty = "hard"
            session_type = "single"
            prompt = "test"

            [[repos]]
            url = "https://github.com/test/repo"
            rev = "v1.0.0"
            path = "repo"

            [[checkpoints]]
            name = "check_one"
            weight = 1.0
            verifier = "checks/check_one.sh"

            [artifacts]
            required = ["answer"]

            [tool_access]
            expected_mcp_benefit = "low"
            mcp_benefit_rationale = "test"

            [ground_truth]
            tiers = ["deterministic"]

            [[ground_truth.required_files]]
            path = "src/main.go"
            repo = "repo"
        """)
        task_dir = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "bare-task", bare_toml
        )
        # Only one check script needed
        (task_dir / "checks" / "check_one.sh").write_text("#!/bin/bash\nexit 0\n")
        (task_dir / "checks" / "check_one.sh").chmod(0o755)

        result = _validate(task_dir)
        assert not result.top_level_fields_present
        assert any(i.check == "top_level_fields" for i in result.issues)


# ---------------------------------------------------------------------------
# Tests for generate_registry
# ---------------------------------------------------------------------------


class TestGenerateRegistry:
    def test_registry_structure(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "reg-task", minimal_task_toml
        )
        result = _validate(task_dir)
        registry = vtp.generate_registry([result])

        assert "summary" in registry
        assert "tasks" in registry
        assert "blocking_issues" in registry
        assert registry["summary"]["total_tasks"] == 1
        assert "customer_escalation" in registry["tasks"]
        assert len(registry["tasks"]["customer_escalation"]) == 1

    def test_registry_counts(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        # One valid, one broken
        good = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "good", minimal_task_toml
        )
        bad = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "bad",
            minimal_task_toml,
            create_instruction=False,
        )
        r1 = _validate(good)
        r2 = _validate(bad)
        registry = vtp.generate_registry([r1, r2])

        assert registry["summary"]["total_tasks"] == 2
        assert registry["summary"]["ready"] == 1
        assert registry["summary"]["blocked"] == 1
        assert len(registry["blocking_issues"]) > 0


# ---------------------------------------------------------------------------
# Tests for load_sg_index
# ---------------------------------------------------------------------------


class TestLoadSgIndex:
    def test_loads_index(self, tmp_path: Path) -> None:
        index_path = tmp_path / "sg_indexing_list.json"
        index_path.write_text(
            json.dumps(
                {
                    "repos": [
                        {"sg_name": "sg-evals/test/repo--v1", "_indexed": True},
                        {"sg_name": "sg-evals/other/repo--v2", "_indexed": False},
                    ]
                }
            )
        )
        with patch.object(vtp, "SG_INDEXING_PATH", index_path):
            result = vtp.load_sg_index()
        assert result["sg-evals/test/repo--v1"] is True
        assert result["sg-evals/other/repo--v2"] is False

    def test_missing_file(self, tmp_path: Path) -> None:
        with patch.object(vtp, "SG_INDEXING_PATH", tmp_path / "nonexistent.json"):
            result = vtp.load_sg_index()
        assert result == {}


# ---------------------------------------------------------------------------
# Tests for TaskValidation properties
# ---------------------------------------------------------------------------


class TestTaskValidationProperties:
    def test_ready_with_no_issues(self) -> None:
        v = vtp.TaskValidation(task_id="t", suite="s", task_dir="/tmp")
        assert v.ready

    def test_not_ready_with_error(self) -> None:
        v = vtp.TaskValidation(
            task_id="t",
            suite="s",
            task_dir="/tmp",
            issues=[vtp.TaskIssue("error", "test", "fail")],
        )
        assert not v.ready

    def test_ready_with_warning_only(self) -> None:
        v = vtp.TaskValidation(
            task_id="t",
            suite="s",
            task_dir="/tmp",
            issues=[vtp.TaskIssue("warning", "test", "warn")],
        )
        assert v.ready

    def test_error_and_warning_counts(self) -> None:
        v = vtp.TaskValidation(
            task_id="t",
            suite="s",
            task_dir="/tmp",
            issues=[
                vtp.TaskIssue("error", "a", "x"),
                vtp.TaskIssue("error", "b", "y"),
                vtp.TaskIssue("warning", "c", "z"),
            ],
        )
        assert v.error_count == 2
        assert v.warning_count == 1


# ---------------------------------------------------------------------------
# Integration: run against real benchmarks
# ---------------------------------------------------------------------------


class TestRealBenchmarks:
    """Smoke test against the actual EnterpriseBench tasks."""

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "benchmarks").exists(),
        reason="Not in EnterpriseBench repo",
    )
    def test_all_tasks_parseable(self) -> None:
        """Every task.toml should at least parse without error."""
        task_dirs = vtp.collect_task_dirs()
        assert len(task_dirs) > 0
        sg_index = vtp.load_sg_index()
        mirror_ids = vtp.load_mirror_task_ids()
        for td in task_dirs:
            result = vtp.validate_task(td, None, None, sg_index, mirror_ids)
            # Should not have toml_parse errors
            parse_errors = [i for i in result.issues if i.check == "toml_parse"]
            assert parse_errors == [], f"{td.name}: {parse_errors}"

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "benchmarks").exists(),
        reason="Not in EnterpriseBench repo",
    )
    def test_all_tasks_ready(self) -> None:
        """All real tasks should be ready (no blocking errors)."""
        task_dirs = vtp.collect_task_dirs()
        sg_index = vtp.load_sg_index()
        mirror_ids = vtp.load_mirror_task_ids()
        blocked = []
        for td in task_dirs:
            result = vtp.validate_task(td, None, None, sg_index, mirror_ids)
            if not result.ready:
                errors = [i for i in result.issues if i.severity == "error"]
                blocked.append((td.name, errors))
        assert blocked == [], f"Blocked tasks: {blocked}"
