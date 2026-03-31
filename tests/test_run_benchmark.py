"""Tests for scripts/run_benchmark.py — --skip-completed flag."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from run_benchmark import (
    TaskInfo,
    is_task_completed,
    filter_completed_tasks,
    build_parser,
    main,
    PROJECT_ROOT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task_info(task_id: str = "test-001", difficulty: str = "medium") -> TaskInfo:
    return TaskInfo(
        task_id=task_id,
        suite="customer_escalation",
        difficulty=difficulty,
        session_type="single",
        task_type="error_provenance",
        toml_path=Path("/fake/task.toml"),
    )


def _write_results(results_dir: Path, task_id: str, success: bool, *, mode: str | None = None) -> Path:
    """Write a results.json file in the expected location."""
    if mode:
        out = results_dir / task_id / mode / "results.json"
    else:
        out = results_dir / task_id / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": task_id,
        "success": success,
        "scores": {"task_score": 2.5 if success else 0.0},
    }
    out.write_text(json.dumps(payload))
    return out


def _write_task_toml(path: Path, task_id: str) -> Path:
    """Write a minimal task.toml."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""
[task]
id = "{task_id}"
suite = "customer_escalation"
difficulty = "medium"
session_type = "single"
task_type = "error_provenance"
description = "Test task"
prompt = "Do something."

[[repos]]
url = "github.com/example/repo"
rev = "v1.0.0"
path = "repo"
role = "primary"

[[checkpoints]]
name = "step1"
weight = 1.0
verifier = "checks/check.sh"

[artifacts]
required = []
""")
    return path


# ---------------------------------------------------------------------------
# is_task_completed
# ---------------------------------------------------------------------------

class TestIsTaskCompleted:
    def test_returns_true_when_results_exist_with_success(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results" / "runs"
        _write_results(results_dir, "task-abc", success=True)
        assert is_task_completed("task-abc", results_dir=results_dir, mode="baseline") is True

    def test_returns_false_when_results_exist_with_failure(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results" / "runs"
        _write_results(results_dir, "task-abc", success=False)
        assert is_task_completed("task-abc", results_dir=results_dir, mode="baseline") is False

    def test_returns_false_when_no_results_file(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results" / "runs"
        results_dir.mkdir(parents=True)
        assert is_task_completed("task-missing", results_dir=results_dir, mode="baseline") is False

    def test_returns_false_when_results_dir_absent(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "nonexistent"
        assert is_task_completed("task-abc", results_dir=results_dir, mode="baseline") is False

    def test_returns_false_on_malformed_json(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results" / "runs"
        f = results_dir / "task-bad" / "results.json"
        f.parent.mkdir(parents=True)
        f.write_text("NOT JSON")
        assert is_task_completed("task-bad", results_dir=results_dir, mode="baseline") is False

    def test_checks_mode_subdirectory(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results" / "runs"
        _write_results(results_dir, "task-mode", success=True, mode="mcp_only")
        # Should find it when mode matches
        assert is_task_completed("task-mode", results_dir=results_dir, mode="mcp_only") is True
        # Should NOT find it for a different mode (no top-level results.json either)
        assert is_task_completed("task-mode", results_dir=results_dir, mode="baseline") is False


# ---------------------------------------------------------------------------
# filter_completed_tasks
# ---------------------------------------------------------------------------

class TestFilterCompletedTasks:
    def test_removes_completed_tasks(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results" / "runs"
        _write_results(results_dir, "done-001", success=True)

        tasks = [
            _make_task_info("done-001"),
            _make_task_info("pending-002"),
        ]
        remaining, skipped = filter_completed_tasks(
            tasks, results_dir=results_dir, mode="baseline"
        )
        assert len(remaining) == 1
        assert remaining[0].task_id == "pending-002"
        assert len(skipped) == 1
        assert skipped[0].task_id == "done-001"

    def test_keeps_failed_tasks(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results" / "runs"
        _write_results(results_dir, "failed-001", success=False)

        tasks = [_make_task_info("failed-001")]
        remaining, skipped = filter_completed_tasks(
            tasks, results_dir=results_dir, mode="baseline"
        )
        assert len(remaining) == 1
        assert len(skipped) == 0

    def test_returns_all_when_no_results(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results" / "runs"
        results_dir.mkdir(parents=True)
        tasks = [_make_task_info("a"), _make_task_info("b")]
        remaining, skipped = filter_completed_tasks(
            tasks, results_dir=results_dir, mode="baseline"
        )
        assert len(remaining) == 2
        assert len(skipped) == 0


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

class TestCliParser:
    def test_skip_completed_flag_exists(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["benchmarks/", "--all", "--skip-completed"])
        assert args.skip_completed is True

    def test_skip_completed_default_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["benchmarks/", "--all"])
        assert args.skip_completed is False


# ---------------------------------------------------------------------------
# Summary includes skipped count
# ---------------------------------------------------------------------------

class TestSummarySkipCount:
    def test_summary_includes_previously_completed(self, tmp_path: Path) -> None:
        """When --skip-completed is used, summary should show previously_completed count."""
        from run_benchmark import write_summary, TaskResult

        results = [
            TaskResult(task_id="t1", difficulty="medium", status="completed", score=1.0),
        ]
        run_id = "test_run"
        # Monkey-patch PROJECT_ROOT temporarily for write_summary
        import run_benchmark
        original_root = run_benchmark.PROJECT_ROOT
        run_benchmark.PROJECT_ROOT = tmp_path
        try:
            summary_path = write_summary(results, run_id, previously_completed=3)
            data = json.loads(summary_path.read_text())
            assert data["previously_completed"] == 3
        finally:
            run_benchmark.PROJECT_ROOT = original_root
