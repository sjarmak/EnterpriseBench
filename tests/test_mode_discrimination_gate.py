#!/usr/bin/env python3
"""Tests for scripts/analysis/mode_discrimination_gate.py."""

from __future__ import annotations

import csv
import json
import math
import tempfile
from pathlib import Path

import pytest

from scripts.analysis.mode_discrimination_gate import (
    GateVerdict,
    ResultsMap,
    TaskGateResult,
    cohens_d,
    evaluate_gate,
    format_human,
    format_json,
    load_results,
    load_results_csv,
    load_results_manifest,
    main,
)

# ---------------------------------------------------------------------------
# cohens_d tests
# ---------------------------------------------------------------------------


class TestCohensD:
    def test_equal_means_returns_zero(self) -> None:
        g1 = [5.0, 5.0, 5.0, 5.0]
        g2 = [5.0, 5.0, 5.0, 5.0]
        # Both groups identical but with variance=0 -> None
        # Use slight variance instead
        g1 = [4.0, 5.0, 6.0, 5.0]
        g2 = [4.0, 5.0, 6.0, 5.0]
        d = cohens_d(g1, g2)
        assert d is not None
        assert abs(d) < 1e-10

    def test_large_difference_positive_d(self) -> None:
        baseline = [1.0, 2.0, 1.5, 2.5, 1.0]
        hybrid = [8.0, 9.0, 8.5, 9.5, 8.0]
        d = cohens_d(baseline, hybrid)
        assert d is not None
        assert d > 2.0  # very large effect

    def test_hybrid_lower_negative_d(self) -> None:
        baseline = [8.0, 9.0, 8.5]
        hybrid = [1.0, 2.0, 1.5]
        d = cohens_d(baseline, hybrid)
        assert d is not None
        assert d < -2.0

    def test_known_value(self) -> None:
        """Verify against hand-calculated Cohen's d."""
        # group1: mean=2, var=2/2=1, group2: mean=5, var=2/2=1
        g1 = [1.0, 2.0, 3.0]
        g2 = [4.0, 5.0, 6.0]
        d = cohens_d(g1, g2)
        # pooled_var = ((2*1)+(2*1))/(3+3-2) = 4/4 = 1, pooled_sd=1
        # d = (5-2)/1 = 3.0
        assert d is not None
        assert abs(d - 3.0) < 1e-10

    def test_insufficient_samples_returns_none(self) -> None:
        assert cohens_d([1.0], [2.0, 3.0]) is None
        assert cohens_d([1.0, 2.0], [3.0]) is None
        assert cohens_d([], [1.0, 2.0]) is None

    def test_zero_variance_returns_none(self) -> None:
        g1 = [5.0, 5.0, 5.0]
        g2 = [5.0, 5.0, 5.0]
        assert cohens_d(g1, g2) is None

    def test_medium_effect(self) -> None:
        """Groups designed to produce d = 0.5 exactly."""
        # var = sum((x-mean)^2)/(n-1) for [0, 1]: var=0.5, sd=sqrt(0.5)
        # Two groups offset by 0.5*sd: d = 0.5
        # Use [0, 2] -> mean=1, var=2, sd=sqrt(2)
        # Offset = 0.5 * sqrt(2) ~ 0.707
        # g2 = [0+offset, 2+offset]
        import math as _m

        sd = _m.sqrt(2.0)
        offset = 0.5 * sd
        g1 = [0.0, 2.0]
        g2 = [offset, 2.0 + offset]
        d = cohens_d(g1, g2)
        assert d is not None
        assert abs(d - 0.5) < 1e-10


# ---------------------------------------------------------------------------
# Gate evaluation tests
# ---------------------------------------------------------------------------


def _make_results(
    task_scores: dict[str, tuple[list[float], list[float]]],
) -> ResultsMap:
    """Helper to build ResultsMap from task_id -> (baseline, hybrid) pairs."""
    results: ResultsMap = {}
    for task_id, (baseline, hybrid) in task_scores.items():
        results[task_id] = {"baseline": baseline, "hybrid": hybrid}
    return results


class TestEvaluateGate:
    def test_pass_2_of_4(self) -> None:
        results = _make_results(
            {
                "task-a": ([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]),  # d=3.0, pass
                "task-b": ([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]),  # d=3.0, pass
                "task-c": ([5.0, 5.0, 5.0], [5.1, 5.1, 5.1]),  # d~0.1, fail
                "task-d": ([5.0, 5.0, 5.0], [5.1, 5.1, 5.1]),  # d~0.1, fail
            }
        )
        verdict = evaluate_gate(results, threshold=0.5, min_tasks=2)
        assert verdict.passed is True
        assert verdict.tasks_passing == 2
        assert verdict.tasks_total == 4

    def test_fail_1_of_4(self) -> None:
        results = _make_results(
            {
                "task-a": ([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]),  # pass
                "task-b": ([5.0, 5.0, 5.0], [5.1, 5.1, 5.1]),  # fail
                "task-c": ([5.0, 5.0, 5.0], [5.1, 5.1, 5.1]),  # fail
                "task-d": ([5.0, 5.0, 5.0], [5.1, 5.1, 5.1]),  # fail
            }
        )
        verdict = evaluate_gate(results, threshold=0.5, min_tasks=2)
        assert verdict.passed is False
        assert verdict.tasks_passing == 1

    def test_insufficient_data_per_task(self) -> None:
        results = _make_results(
            {
                "task-a": ([1.0], [4.0]),  # n<2, d=None -> fail
            }
        )
        verdict = evaluate_gate(results, threshold=0.5, min_tasks=1)
        assert verdict.passed is False
        assert verdict.per_task[0].cohens_d is None

    def test_empty_results(self) -> None:
        verdict = evaluate_gate({}, threshold=0.5, min_tasks=2)
        assert verdict.passed is False
        assert verdict.tasks_total == 0

    def test_missing_hybrid_mode(self) -> None:
        results: ResultsMap = {"task-a": {"baseline": [1.0, 2.0, 3.0]}}
        verdict = evaluate_gate(results, threshold=0.5, min_tasks=1)
        assert verdict.passed is False
        assert verdict.per_task[0].cohens_d is None

    def test_custom_threshold(self) -> None:
        results = _make_results(
            {
                "task-a": ([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]),  # d=3.0
            }
        )
        verdict = evaluate_gate(results, threshold=5.0, min_tasks=1)
        assert verdict.passed is False  # d=3 < threshold=5


# ---------------------------------------------------------------------------
# CSV loading tests
# ---------------------------------------------------------------------------


class TestLoadCSV:
    def test_loads_scored_rows(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "summary.csv"
        csv_path.write_text(
            "task_id,mode,rep_index,account_id,status,score,error\n"
            "t1,baseline,1,1,completed,0.3,\n"
            "t1,baseline,2,2,completed,0.4,\n"
            "t1,hybrid,1,3,completed,0.8,\n"
            "t1,hybrid,2,4,completed,0.9,\n"
        )
        results = load_results_csv(csv_path)
        assert "t1" in results
        assert results["t1"]["baseline"] == [0.3, 0.4]
        assert results["t1"]["hybrid"] == [0.8, 0.9]

    def test_skips_empty_scores(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "summary.csv"
        csv_path.write_text(
            "task_id,mode,rep_index,account_id,status,score,error\n"
            "t1,baseline,1,1,completed,,\n"
            "t1,hybrid,1,2,completed,,\n"
        )
        results = load_results_csv(csv_path)
        assert results == {}

    def test_multiple_tasks(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "summary.csv"
        csv_path.write_text(
            "task_id,mode,rep_index,account_id,status,score,error\n"
            "t1,baseline,1,1,completed,0.3,\n"
            "t2,baseline,1,2,completed,0.5,\n"
        )
        results = load_results_csv(csv_path)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Manifest loading tests
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_loads_scored_entries(self, tmp_path: Path) -> None:
        manifest = {
            "entries": [
                {"task_id": "t1", "mode": "baseline", "score": 0.3},
                {"task_id": "t1", "mode": "baseline", "score": 0.4},
                {"task_id": "t1", "mode": "hybrid", "score": 0.9},
            ]
        }
        manifest_path = tmp_path / "run_manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        results = load_results_manifest(manifest_path)
        assert results["t1"]["baseline"] == [0.3, 0.4]
        assert results["t1"]["hybrid"] == [0.9]

    def test_skips_null_scores(self, tmp_path: Path) -> None:
        manifest = {
            "entries": [
                {"task_id": "t1", "mode": "baseline", "score": None},
            ]
        }
        manifest_path = tmp_path / "run_manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        results = load_results_manifest(manifest_path)
        assert results == {}


# ---------------------------------------------------------------------------
# load_results fallback tests
# ---------------------------------------------------------------------------


class TestLoadResults:
    def test_prefers_csv(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "summary.csv"
        csv_path.write_text(
            "task_id,mode,rep_index,account_id,status,score,error\n"
            "t1,baseline,1,1,completed,0.5,\n"
        )
        manifest_path = tmp_path / "run_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {"entries": [{"task_id": "t1", "mode": "baseline", "score": 0.9}]}
            )
        )
        results = load_results(tmp_path)
        # CSV should be preferred
        assert results["t1"]["baseline"] == [0.5]

    def test_falls_back_to_manifest(self, tmp_path: Path) -> None:
        # CSV with no scores
        csv_path = tmp_path / "summary.csv"
        csv_path.write_text(
            "task_id,mode,rep_index,account_id,status,score,error\n"
            "t1,baseline,1,1,completed,,\n"
        )
        manifest_path = tmp_path / "run_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {"entries": [{"task_id": "t1", "mode": "baseline", "score": 0.7}]}
            )
        )
        results = load_results(tmp_path)
        assert results["t1"]["baseline"] == [0.7]

    def test_empty_dir(self, tmp_path: Path) -> None:
        results = load_results(tmp_path)
        assert results == {}


# ---------------------------------------------------------------------------
# Output format tests
# ---------------------------------------------------------------------------


class TestFormatting:
    def _sample_verdict(self, passed: bool = True) -> GateVerdict:
        return GateVerdict(
            passed=passed,
            tasks_passing=2,
            tasks_total=4,
            threshold=0.5,
            min_tasks_required=2,
            per_task=(
                TaskGateResult("t1", 1.5, 3, 3, 2.0, 5.0, True),
                TaskGateResult("t2", 0.8, 3, 3, 3.0, 4.0, True),
                TaskGateResult("t3", 0.1, 3, 3, 5.0, 5.1, False),
                TaskGateResult("t4", None, 1, 1, 1.0, 2.0, False),
            ),
        )

    def test_human_format_pass(self) -> None:
        output = format_human(self._sample_verdict(passed=True))
        assert "PASS" in output
        assert "Phase 2 scaling is approved" in output

    def test_human_format_fail(self) -> None:
        output = format_human(self._sample_verdict(passed=False))
        assert "FAIL" in output
        assert "NOT approved" in output

    def test_json_format_structure(self) -> None:
        output = format_json(self._sample_verdict())
        data = json.loads(output)
        assert data["gate"] == "mode_discrimination"
        assert data["passed"] is True
        assert data["tasks_passing"] == 2
        assert data["tasks_total"] == 4
        assert len(data["per_task"]) == 4

    def test_json_format_per_task_fields(self) -> None:
        output = format_json(self._sample_verdict())
        data = json.loads(output)
        t1 = data["per_task"][0]
        assert t1["task_id"] == "t1"
        assert t1["cohens_d"] == 1.5
        assert t1["passes_threshold"] is True


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_json_output_with_data(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "summary.csv"
        csv_path.write_text(
            "task_id,mode,rep_index,account_id,status,score,error\n"
            "t1,baseline,1,1,completed,1.0,\n"
            "t1,baseline,2,2,completed,2.0,\n"
            "t1,baseline,3,3,completed,3.0,\n"
            "t1,hybrid,1,4,completed,4.0,\n"
            "t1,hybrid,2,5,completed,5.0,\n"
            "t1,hybrid,3,1,completed,6.0,\n"
        )
        rc = main(["--results-dir", str(tmp_path), "--json", "--min-tasks", "1"])
        assert rc == 0  # gate passes (d=3.0 > 0.5, 1/1 >= 1)

    def test_no_data_returns_error(self, tmp_path: Path) -> None:
        rc = main(["--results-dir", str(tmp_path), "--json"])
        assert rc == 1

    def test_gate_fail_returns_1(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "summary.csv"
        csv_path.write_text(
            "task_id,mode,rep_index,account_id,status,score,error\n"
            "t1,baseline,1,1,completed,5.0,\n"
            "t1,baseline,2,2,completed,5.0,\n"
            "t1,hybrid,1,3,completed,5.1,\n"
            "t1,hybrid,2,4,completed,5.1,\n"
        )
        rc = main(["--results-dir", str(tmp_path), "--min-tasks", "1"])
        assert rc == 1  # d ~ 0.1 < 0.5
