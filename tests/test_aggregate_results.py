"""Tests for scripts/triage/aggregate_results.py — checkpoint-aware aggregation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers to build triage-style task dicts (output of triage_run.classify_task)
# ---------------------------------------------------------------------------


def _task(
    task_id: str,
    category: str = "pass",
    score: float = 1.0,
    suite: str = "customer_escalation",
    task_type: str = "error_provenance",
    difficulty: str = "medium",
    checkpoints: list[dict[str, Any]] | None = None,
    checkpoints_passed: int = 1,
    checkpoints_total: int = 2,
) -> dict[str, Any]:
    if checkpoints is None:
        checkpoints = [
            {"name": "cp1", "score": 1.0, "passed": True, "weight": 1.0},
            {"name": "cp2", "score": 0.0, "passed": False, "weight": 1.0},
        ]
    return {
        "task_id": task_id,
        "category": category,
        "score": score,
        "phase": "complete",
        "success": True,
        "fingerprint_id": None,
        "fingerprint_severity": None,
        "fingerprint_label": None,
        "fingerprint_advice": None,
        "checkpoints": checkpoints,
        "checkpoints_passed": checkpoints_passed,
        "checkpoints_total": checkpoints_total,
        "metadata": {
            "suite": suite,
            "task_type": task_type,
            "difficulty": difficulty,
        },
    }


SAMPLE_TASKS = [
    _task("t1", "pass", 2.0, "customer_escalation", "error_provenance", "medium",
          checkpoints=[
              {"name": "a", "score": 1.0, "passed": True, "weight": 1.0},
              {"name": "b", "score": 1.0, "passed": True, "weight": 1.0},
          ], checkpoints_passed=2, checkpoints_total=2),
    _task("t2", "pass", 1.0, "customer_escalation", "error_provenance", "hard",
          checkpoints=[
              {"name": "a", "score": 1.0, "passed": True, "weight": 1.0},
              {"name": "b", "score": 0.0, "passed": False, "weight": 1.0},
          ], checkpoints_passed=1, checkpoints_total=2),
    _task("t3", "D_agent", 0.0, "feature_delivery", "monorepo_boundary", "hard",
          checkpoints=[
              {"name": "x", "score": 0.0, "passed": False, "weight": 1.0},
          ], checkpoints_passed=0, checkpoints_total=1),
    _task("t4", "A_infra", 0.0, "feature_delivery", "db_schema_evolution", "easy",
          checkpoints=[], checkpoints_passed=0, checkpoints_total=0),
    _task("t5", "pass", 3.0, "security_operations", "error_provenance", "medium",
          checkpoints=[
              {"name": "c1", "score": 1.0, "passed": True, "weight": 1.0},
              {"name": "c2", "score": 1.0, "passed": True, "weight": 1.0},
              {"name": "c3", "score": 1.0, "passed": True, "weight": 1.0},
          ], checkpoints_passed=3, checkpoints_total=3),
]


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from triage.aggregate_results import (
    aggregate,
    compute_group_stats,
    compute_score_histogram,
    AggregateReport,
)


# ---------------------------------------------------------------------------
# Tests: compute_group_stats
# ---------------------------------------------------------------------------


class TestComputeGroupStats:
    def test_basic_stats(self) -> None:
        tasks = [SAMPLE_TASKS[0], SAMPLE_TASKS[1]]  # scores 2.0, 1.0
        stats = compute_group_stats(tasks)
        assert stats["count"] == 2
        assert stats["pass_count"] == 2
        assert stats["pass_rate"] == 1.0
        assert stats["score_mean"] == pytest.approx(1.5)
        assert stats["score_median"] == pytest.approx(1.5)
        assert stats["score_min"] == pytest.approx(1.0)
        assert stats["score_max"] == pytest.approx(2.0)

    def test_mixed_pass_fail(self) -> None:
        tasks = [SAMPLE_TASKS[0], SAMPLE_TASKS[2]]  # pass, D_agent
        stats = compute_group_stats(tasks)
        assert stats["count"] == 2
        assert stats["pass_count"] == 1
        assert stats["pass_rate"] == pytest.approx(0.5)

    def test_empty_group(self) -> None:
        stats = compute_group_stats([])
        assert stats["count"] == 0
        assert stats["pass_rate"] == 0.0
        assert stats["score_mean"] == 0.0

    def test_checkpoint_stats(self) -> None:
        tasks = [SAMPLE_TASKS[0], SAMPLE_TASKS[1]]
        stats = compute_group_stats(tasks)
        assert stats["checkpoints_passed_total"] == 3
        assert stats["checkpoints_total"] == 4
        assert stats["checkpoint_pass_rate"] == pytest.approx(0.75)

    def test_category_distribution(self) -> None:
        stats = compute_group_stats(SAMPLE_TASKS)
        dist = stats["category_distribution"]
        assert dist["pass"] == 3
        assert dist["D_agent"] == 1
        assert dist["A_infra"] == 1


# ---------------------------------------------------------------------------
# Tests: compute_score_histogram
# ---------------------------------------------------------------------------


class TestComputeScoreHistogram:
    def test_histogram_bins(self) -> None:
        scores = [0.0, 0.0, 1.0, 2.0, 3.0]
        hist = compute_score_histogram(scores)
        # Should have defined bins with counts
        assert isinstance(hist, list)
        assert all("bin" in entry and "count" in entry for entry in hist)

    def test_empty_scores(self) -> None:
        hist = compute_score_histogram([])
        assert isinstance(hist, list)

    def test_all_zeros(self) -> None:
        hist = compute_score_histogram([0.0, 0.0, 0.0])
        total = sum(entry["count"] for entry in hist)
        assert total == 3


# ---------------------------------------------------------------------------
# Tests: aggregate (main entry point)
# ---------------------------------------------------------------------------


class TestAggregate:
    def test_overall_summary(self) -> None:
        report = aggregate(SAMPLE_TASKS)
        assert report["overall"]["count"] == 5
        assert report["overall"]["pass_count"] == 3
        assert report["overall"]["category_distribution"]["pass"] == 3

    def test_by_suite_keys(self) -> None:
        report = aggregate(SAMPLE_TASKS)
        assert "customer_escalation" in report["by_suite"]
        assert "feature_delivery" in report["by_suite"]
        assert "security_operations" in report["by_suite"]

    def test_by_suite_stats(self) -> None:
        report = aggregate(SAMPLE_TASKS)
        ce = report["by_suite"]["customer_escalation"]
        assert ce["count"] == 2
        assert ce["pass_count"] == 2

    def test_by_task_type_keys(self) -> None:
        report = aggregate(SAMPLE_TASKS)
        assert "error_provenance" in report["by_task_type"]
        assert "monorepo_boundary" in report["by_task_type"]

    def test_by_difficulty_keys(self) -> None:
        report = aggregate(SAMPLE_TASKS)
        assert "medium" in report["by_difficulty"]
        assert "hard" in report["by_difficulty"]
        assert "easy" in report["by_difficulty"]

    def test_score_histogram_present(self) -> None:
        report = aggregate(SAMPLE_TASKS)
        assert "score_histogram" in report
        assert isinstance(report["score_histogram"], list)

    def test_per_task_preserved(self) -> None:
        report = aggregate(SAMPLE_TASKS)
        assert len(report["per_task"]) == 5
        ids = {t["task_id"] for t in report["per_task"]}
        assert ids == {"t1", "t2", "t3", "t4", "t5"}

    def test_json_serializable(self) -> None:
        report = aggregate(SAMPLE_TASKS)
        # Must be JSON-serializable
        json_str = json.dumps(report)
        roundtripped = json.loads(json_str)
        assert roundtripped["overall"]["count"] == 5


# ---------------------------------------------------------------------------
# Tests: AggregateReport (typed wrapper)
# ---------------------------------------------------------------------------


class TestAggregateReport:
    def test_from_tasks(self) -> None:
        report = AggregateReport.from_tasks(SAMPLE_TASKS)
        assert report.overall["count"] == 5

    def test_to_json(self) -> None:
        report = AggregateReport.from_tasks(SAMPLE_TASKS)
        data = report.to_dict()
        assert "generated_at" in data
        assert "overall" in data
        assert "by_suite" in data

    def test_to_json_string(self) -> None:
        report = AggregateReport.from_tasks(SAMPLE_TASKS)
        s = report.to_json()
        parsed = json.loads(s)
        assert parsed["overall"]["count"] == 5


# ---------------------------------------------------------------------------
# Tests: CLI integration
# ---------------------------------------------------------------------------


class TestCLI:
    def test_from_triage_file(self, tmp_path: Path) -> None:
        """CLI can consume a triage JSON file."""
        from triage.aggregate_results import parse_args

        triage_data = {
            "per_task": SAMPLE_TASKS,
            "summary": {"total": 5},
        }
        triage_file = tmp_path / "triage.json"
        triage_file.write_text(json.dumps(triage_data))

        args = parse_args(["--triage-file", str(triage_file)])
        assert args.triage_file == str(triage_file)

    def test_from_results_dir(self) -> None:
        from triage.aggregate_results import parse_args

        args = parse_args(["--results-dir", "results/runs"])
        assert args.results_dir == "results/runs"

    def test_output_flag(self) -> None:
        from triage.aggregate_results import parse_args

        args = parse_args(["--output", "report.json"])
        assert args.output == "report.json"

    def test_main_with_triage_file(self, tmp_path: Path) -> None:
        """End-to-end: main() reads triage file and writes output."""
        from triage.aggregate_results import main

        triage_data = {
            "per_task": SAMPLE_TASKS,
            "summary": {"total": 5},
        }
        triage_file = tmp_path / "triage.json"
        triage_file.write_text(json.dumps(triage_data))
        out_file = tmp_path / "aggregate.json"

        main(["--triage-file", str(triage_file), "--output", str(out_file)])

        assert out_file.exists()
        result = json.loads(out_file.read_text())
        assert result["overall"]["count"] == 5
        assert "by_suite" in result
        assert "score_histogram" in result
