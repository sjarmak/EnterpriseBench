"""Tests for scripts/analyze_scores.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Ensure the scripts directory is importable
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.attempt_policy import SELECTION_EARLIEST_VALID, AttemptPolicy

from analyze_scores import (
    Checkpoint,
    TaskResult,
    analyze,
    _compute_delta,
    _dist_stats,
    _statistical_tests,
    calibration_bias,
    infer_mode,
    load_all_results,
    load_task_metadata_from_toml,
    parse_result,
    per_task_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    task_id: str = "test-task-001",
    mode: str = "baseline",
    task_score: float = 0.6667,
    checkpoints_total: int = 3,
    all_passed: bool = False,
    checkpoints_passed: int = 2,
    suite: str = "customer_escalation",
    task_type: str = "error_provenance",
    difficulty: str = "medium",
) -> TaskResult:
    # task_score IS the normalized score: under the v2 contract
    # (eb_verify.score_contract) it is the weighted mean, already in [0,1], and
    # checkpoints_total is a task SHAPE that no longer enters the arithmetic.
    # This helper used to re-derive normalized = task_score / checkpoints_total,
    # which meant every assertion below re-stated the defect being tested and
    # passed under the buggy and the corrected implementation alike.
    return TaskResult(
        task_id=task_id,
        mode=mode,
        success=True,
        task_score=task_score,
        normalized_score=task_score,
        all_passed=all_passed,
        checkpoints_passed=checkpoints_passed,
        checkpoints_total=checkpoints_total,
        checkpoints=(
            Checkpoint("cp1", 1.0, 1.0, True),
            Checkpoint("cp2", 1.0, 1.0, True),
            Checkpoint("cp3", 1.0, 0.0, False),
        ),
        suite=suite,
        task_type=task_type,
        difficulty=difficulty,
        languages=("python",),
        agent_time=100.0,
        source_path="/tmp/test",
    )


def _write_results_json(path: Path, **overrides: object) -> None:
    """Write a minimal results.json to the given path."""
    data = {
        "task_id": overrides.get("task_id", "test-task-001"),
        "success": True,
        "scores": {
            "task_score": overrides.get("task_score", 0.6667),
            "score_contract_version": overrides.get("score_contract_version", 2),
            "all_passed": overrides.get("all_passed", False),
            "checkpoints_passed": overrides.get("checkpoints_passed", 2),
            "checkpoints_total": overrides.get("checkpoints_total", 3),
            "checkpoints": overrides.get(
                "checkpoints",
                [
                    {"name": "cp1", "weight": 0.3333, "score": 1.0, "passed": True},
                    {"name": "cp2", "weight": 0.3333, "score": 1.0, "passed": True},
                    {"name": "cp3", "weight": 0.3334, "score": 0.0, "passed": False},
                ],
            ),
        },
        "timing": {"agent": 100.0},
        "task_metadata": {
            "suite": overrides.get("suite", "customer_escalation"),
            "task_type": overrides.get("task_type", "error_provenance"),
            "difficulty": overrides.get("difficulty", "medium"),
            "languages": ["python"],
        },
    }
    if "config" in overrides:
        data["config"] = overrides["config"]
    if "status" in overrides:
        data["status"] = overrides["status"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _write_attempt(
    batch_dir: Path, *, timestamp: str | None = None, **overrides: object
) -> Path:
    """Write one attempt directory: results.json plus a dated agent_trace.jsonl.

    The trace is what dates the attempt, and the date is what orders a cell's
    attempts, so a selection test that writes only results.json is testing the
    run_dir tiebreak rather than the rule.
    """
    task_dir = batch_dir / "test-task-001"
    _write_results_json(task_dir / "results.json", **overrides)
    if timestamp is not None:
        (task_dir / "agent_trace.jsonl").write_text(
            json.dumps({"type": "assistant", "timestamp": timestamp}) + "\n"
        )
    return task_dir


# ---------------------------------------------------------------------------
# Score normalization
# ---------------------------------------------------------------------------


class TestScoreNormalization:
    """Normalization is a property of parse_result, not of this file's helper.

    The four tests that used to live here asserted that
    ``task_score / checkpoints_total`` equals ``task_score / checkpoints_total``
    — they exercised the fixture builder, so they were green throughout the
    double-normalization defect. The real coverage is in
    tests/test_score_contract.py, which runs the production loader over
    materially different task shapes and asserts literals.
    """

    def test_normalized_score_is_the_contract_value_verbatim(self):
        r = _make_result(task_score=0.75, checkpoints_total=4)
        assert r.normalized_score == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_keeps_the_earliest_attempt_not_the_best_one(self, tmp_path: Path):
        """A cell is represented by its first attempt, whatever the re-run scored.

        Keeping the maximum over N attempts made a cell's reported score a
        function of how often it happened to be retried, and arms are not
        retried equally — the bias does not cancel between arms.
        """
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"
        benchmarks = tmp_path / "benchmarks"
        benchmarks.mkdir()

        _write_attempt(dir1, task_score=0.3333, timestamp="2026-01-01T00:00:00Z")
        _write_attempt(dir2, task_score=0.6667, timestamp="2026-06-01T00:00:00Z")

        results = load_all_results([dir1, dir2], benchmarks)
        assert len(results) == 1
        assert results[0].normalized_score == pytest.approx(0.3333)

    def test_host_clock_defeats_agent_forged_trace_order(self, tmp_path: Path):
        benchmarks = tmp_path / "benchmarks"
        benchmarks.mkdir()
        first = _write_attempt(
            tmp_path / "run1",
            task_score=0.3333,
            timestamp="2099-01-01T00:00:00Z",
        )
        second = _write_attempt(
            tmp_path / "run2",
            task_score=0.9999,
            timestamp="1970-01-01T00:00:00Z",
        )
        first_data = json.loads((first / "results.json").read_text())
        second_data = json.loads((second / "results.json").read_text())
        first_data["started_at"] = "2026-01-01T00:00:00Z"
        second_data["started_at"] = "2026-02-01T00:00:00Z"
        (first / "results.json").write_text(json.dumps(first_data))
        (second / "results.json").write_text(json.dumps(second_data))

        results = load_all_results([tmp_path / "run1", tmp_path / "run2"], benchmarks)

        assert results[0].normalized_score == pytest.approx(0.3333)
        assert results[0].attempt_timestamp_source == "results.started_at"
        summary = per_task_summary(results)
        assert summary[0]["attempts"]["baseline"] == {
            "run_dir": results[0].run_dir,
            "timestamp": "2026-01-01T00:00:00Z",
            "timestamp_source": "results.started_at",
        }

    def test_an_invalid_attempt_is_never_selected(self, tmp_path: Path):
        """The resurrection case: run_task marks a run invalid for gates that
        fire after the verifier already wrote a score, so a scored results.json
        is not evidence the run is scoreable."""
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"
        benchmarks = tmp_path / "benchmarks"
        benchmarks.mkdir()

        _write_attempt(
            dir1, task_score=1.0, timestamp="2026-01-01T00:00:00Z", status="invalid"
        )
        _write_attempt(dir2, task_score=0.3333, timestamp="2026-06-01T00:00:00Z")

        results = load_all_results([dir1, dir2], benchmarks)
        assert len(results) == 1
        assert results[0].normalized_score == pytest.approx(0.3333)

    def test_a_cell_whose_every_attempt_is_invalid_drops_out(self, tmp_path: Path):
        benchmarks = tmp_path / "benchmarks"
        benchmarks.mkdir()
        _write_attempt(tmp_path / "run1", status="invalid")

        assert load_all_results([tmp_path / "run1"], benchmarks) == []

    def test_different_modes_kept(self, tmp_path: Path):
        """Different modes for same task are NOT deduplicated."""
        dir1 = tmp_path / "runs"
        benchmarks = tmp_path / "benchmarks"
        benchmarks.mkdir()

        _write_results_json(
            dir1 / "test-task-001" / "results.json",
            task_score=0.3333,
        )
        _write_results_json(
            dir1 / "test-task-001_hybrid" / "results.json",
            task_score=0.6667,
            config={"mode": "hybrid"},
        )

        results = load_all_results([dir1], benchmarks)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# MCP delta computation
# ---------------------------------------------------------------------------


class TestMCPDelta:
    def test_basic_delta(self):
        results = [
            _make_result(
                task_id="t1", mode="baseline", task_score=0.5, checkpoints_total=2
            ),
            _make_result(
                task_id="t1", mode="hybrid", task_score=1.0, checkpoints_total=2
            ),
            _make_result(
                task_id="t2", mode="baseline", task_score=1.0, checkpoints_total=2
            ),
            _make_result(
                task_id="t2", mode="hybrid", task_score=1.0, checkpoints_total=2
            ),
        ]
        delta = _compute_delta(results, "hybrid")
        assert delta["n_paired"] == 2
        assert delta["mean_delta"] == pytest.approx(0.25)
        assert delta["pct_improved"] == pytest.approx(0.5)
        assert delta["pct_unchanged"] == pytest.approx(0.5)
        assert delta["pct_degraded"] == pytest.approx(0.0)

    def test_no_pairs(self):
        results = [
            _make_result(task_id="t1", mode="baseline"),
            _make_result(task_id="t2", mode="hybrid"),
        ]
        delta = _compute_delta(results, "hybrid")
        assert delta["n_paired"] == 0

    def test_degradation(self):
        results = [
            _make_result(
                task_id="t1", mode="baseline", task_score=1.0, checkpoints_total=3
            ),
            _make_result(
                task_id="t1", mode="mcp_only", task_score=0.3333, checkpoints_total=3
            ),
        ]
        delta = _compute_delta(results, "mcp_only")
        assert delta["n_paired"] == 1
        assert delta["mean_delta"] < 0
        assert delta["pct_degraded"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Calibration bias detection
# ---------------------------------------------------------------------------


class TestCalibrationBias:
    def test_no_bias(self):
        results = [
            _make_result(
                task_id="cal-test-001",
                mode="baseline",
                task_score=0.6667,
                checkpoints_total=3,
            ),
            _make_result(
                task_id="cal-test-001",
                mode="hybrid",
                task_score=0.6667,
                checkpoints_total=3,
            ),
        ]
        cb = calibration_bias(results)
        assert cb["calibration_task_count"] == 2
        assert cb["bias_flagged"] is False
        assert cb["max_mode_delta"] == pytest.approx(0.0)

    def test_bias_flagged(self):
        results = [
            _make_result(
                task_id="cal-test-001",
                mode="baseline",
                task_score=0.3333,
                checkpoints_total=3,
            ),
            _make_result(
                task_id="cal-test-001",
                mode="hybrid",
                task_score=1.0,
                checkpoints_total=3,
            ),
        ]
        cb = calibration_bias(results, bias_threshold=0.10)
        assert cb["bias_flagged"] is True
        # delta = 1.0 - 0.333 = 0.667
        assert cb["max_mode_delta"] > 0.10

    def test_no_calibration_tasks(self):
        results = [_make_result(task_id="normal-001")]
        cb = calibration_bias(results)
        assert cb["calibration_task_count"] == 0
        assert cb["bias_flagged"] is False


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------


class TestStatisticalTests:
    def test_cohens_d_zero_when_identical(self):
        result = _statistical_tests([0.5, 0.6, 0.7], [0.5, 0.6, 0.7])
        assert result["cohens_d"] == pytest.approx(0.0)

    def test_cohens_d_positive_when_improved(self):
        result = _statistical_tests(
            [0.3, 0.4, 0.5, 0.6, 0.3, 0.4],
            [0.5, 0.6, 0.7, 0.8, 0.5, 0.6],
        )
        assert result["cohens_d"] > 0

    def test_graceful_without_scipy(self, monkeypatch: pytest.MonkeyPatch):
        """If scipy import fails, should still return results with None."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "scipy" in name:
                raise ImportError("no scipy")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = _statistical_tests([0.5, 0.6], [0.7, 0.8])
        assert result["wilcoxon_p"] is None


# ---------------------------------------------------------------------------
# Mode inference
# ---------------------------------------------------------------------------


class TestModeInference:
    def test_config_mode_takes_precedence(self, tmp_path: Path):
        path = tmp_path / "some_dir" / "results.json"
        data = {"config": {"mode": "hybrid"}}
        assert infer_mode(path, data) == "hybrid"

    def test_dirname_suffix_hybrid(self, tmp_path: Path):
        path = tmp_path / "mcp_batch" / "task-001_hybrid" / "results.json"
        data = {}
        assert infer_mode(path, data) == "hybrid"

    def test_dirname_suffix_mcp_only(self, tmp_path: Path):
        path = tmp_path / "mcp_batch" / "task-001_mcp_only" / "results.json"
        data = {}
        assert infer_mode(path, data) == "mcp_only"

    def test_runs_defaults_baseline(self, tmp_path: Path):
        path = tmp_path / "results" / "runs" / "task-001" / "results.json"
        data = {}
        assert infer_mode(path, data) == "baseline"

    def test_smoke_hybrid(self, tmp_path: Path):
        path = tmp_path / "results" / "smoke_hybrid_v2" / "results.json"
        data = {}
        assert infer_mode(path, data) == "hybrid"

    def test_smoke_mcp(self, tmp_path: Path):
        path = tmp_path / "results" / "smoke_mcp" / "results.json"
        data = {}
        assert infer_mode(path, data) == "mcp_only"


# ---------------------------------------------------------------------------
# Metadata fallback to task.toml
# ---------------------------------------------------------------------------


class TestMetadataFallback:
    def test_loads_from_toml(self, tmp_path: Path):
        task_dir = tmp_path / "benchmarks" / "some_suite" / "my-task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "task.toml").write_text(
            "[task]\n"
            'id = "my-task-001"\n'
            'suite = "feature_delivery"\n'
            'task_type = "monorepo_boundary"\n'
            'difficulty = "hard"\n'
            "\n"
            "[metadata]\n"
            'languages = ["go", "python"]\n'
        )
        meta = load_task_metadata_from_toml("my-task-001", tmp_path / "benchmarks")
        assert meta["suite"] == "feature_delivery"
        assert meta["task_type"] == "monorepo_boundary"
        assert meta["difficulty"] == "hard"
        assert meta["languages"] == ["go", "python"]

    def test_returns_empty_when_not_found(self, tmp_path: Path):
        benchmarks = tmp_path / "benchmarks"
        benchmarks.mkdir()
        meta = load_task_metadata_from_toml("nonexistent", benchmarks)
        assert meta == {}

    def test_parse_result_falls_back_to_toml(self, tmp_path: Path):
        """If results.json has no task_metadata, fall back to task.toml."""
        # Write results.json without task_metadata
        results_dir = tmp_path / "runs" / "my-task-001"
        results_dir.mkdir(parents=True)
        data = {
            "task_id": "my-task-001",
            "success": True,
            "scores": {
                "task_score": 0.5,
                "score_contract_version": 2,
                "all_passed": False,
                "checkpoints_passed": 1,
                "checkpoints_total": 2,
                "checkpoints": [
                    {"name": "cp1", "weight": 0.5, "score": 1.0, "passed": True},
                    {"name": "cp2", "weight": 0.5, "score": 0.0, "passed": False},
                ],
            },
            "timing": {"agent": 50.0},
        }
        (results_dir / "results.json").write_text(json.dumps(data))

        # Write task.toml
        task_dir = tmp_path / "benchmarks" / "suite" / "my-task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "task.toml").write_text(
            "[task]\n"
            'suite = "technical_debt"\n'
            'task_type = "dead_code_necropsy"\n'
            'difficulty = "easy"\n'
            "[metadata]\n"
            'languages = ["java"]\n'
        )

        result = parse_result(
            results_dir / "results.json",
            tmp_path / "benchmarks",
        )
        assert result is not None
        assert result.suite == "technical_debt"
        assert result.task_type == "dead_code_necropsy"
        assert result.difficulty == "easy"


# ---------------------------------------------------------------------------
# Distribution stats
# ---------------------------------------------------------------------------


class TestDistStats:
    def test_empty_list(self):
        stats = _dist_stats([])
        assert stats["count"] == 0
        assert stats["mean"] is None

    def test_single_result(self):
        r = _make_result(task_score=0.5, checkpoints_total=4)
        stats = _dist_stats([r])
        assert stats["count"] == 1
        assert stats["mean"] == pytest.approx(0.5)
        assert stats["std"] == 0.0

    def test_multiple_results(self):
        results = [
            _make_result(task_id=f"t{i}", task_score=i / 3, checkpoints_total=3)
            for i in range(4)
        ]
        stats = _dist_stats(results)
        assert stats["count"] == 4
        assert stats["min"] == pytest.approx(0.0)
        assert stats["max"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Per-task summary
# ---------------------------------------------------------------------------


class TestPerTaskSummary:
    def test_cross_mode_summary(self):
        results = [
            _make_result(
                task_id="t1", mode="baseline", task_score=0.5, checkpoints_total=2
            ),
            _make_result(
                task_id="t1", mode="hybrid", task_score=1.0, checkpoints_total=2
            ),
        ]
        summary = per_task_summary(results)
        assert len(summary) == 1
        assert summary[0]["task_id"] == "t1"
        assert "baseline" in summary[0]["scores"]
        assert "hybrid" in summary[0]["scores"]
        assert summary[0]["scores"]["baseline"] == pytest.approx(0.5)
        assert summary[0]["scores"]["hybrid"] == pytest.approx(1.0)

    def test_calibration_flag(self):
        results = [_make_result(task_id="cal-test-001")]
        summary = per_task_summary(results)
        assert summary[0]["is_calibration"] is True

        results2 = [_make_result(task_id="normal-001")]
        summary2 = per_task_summary(results2)
        assert summary2[0]["is_calibration"] is False


class TestAnalyzePinsThePolicy:
    """The reward side's half of "pinned before outcomes". Without these, the
    guard and the published block in ``analyze`` can both be deleted and the
    whole suite still passes — verified by mutation during review.
    """

    def _corpus(self, tmp_path: Path) -> Path:
        run = tmp_path / "runs" / "task-a"
        run.mkdir(parents=True)
        (run / "results.json").write_text(
            json.dumps(
                {
                    "task_id": "task-a",
                    "scores": {
                        "checkpoints_total": 2,
                        "task_score": 1.0,
                        "score_contract_version": 2,
                        "checkpoints": [],
                    },
                    "task_metadata": {"suite": "s", "difficulty": "medium"},
                    "config": {"mode": "baseline"},
                }
            )
        )
        return tmp_path / "runs"

    def test_the_declared_policy_is_published(self, tmp_path: Path) -> None:
        policy = AttemptPolicy(
            selection=SELECTION_EARLIEST_VALID, version=7, spec_path="/spec.json"
        )
        report = analyze([self._corpus(tmp_path)], tmp_path / "benchmarks", policy)
        assert report["attempt_policy"]["version"] == 7
        assert report["attempt_policy"]["spec_path"] == "/spec.json"
        assert report["total_results"] == 1

    def test_a_policy_the_code_cannot_apply_is_refused(self, tmp_path: Path) -> None:
        """A report may not name a rule load_all_results did not apply."""
        with pytest.raises(ValueError, match="highest_score"):
            analyze(
                [self._corpus(tmp_path)],
                tmp_path / "benchmarks",
                AttemptPolicy(
                    selection="highest_score", version=1, spec_path="/spec.json"
                ),
            )

    def test_an_unpinned_call_publishes_no_policy(self, tmp_path: Path) -> None:
        """Absent, not silently defaulted: an artifact that names a policy must
        have been produced under one."""
        report = analyze([self._corpus(tmp_path)], tmp_path / "benchmarks")
        assert report["attempt_policy"] is None


class TestParseResultFailsClosedOnJunk:
    def test_valid_json_that_is_not_an_object_is_skipped_not_a_crash(
        self, tmp_path: Path
    ) -> None:
        """A partial write or a serialization bug produces well-formed JSON of
        the wrong shape. Before this, data.get raised AttributeError and took
        down the whole load_all_results scan, not just this attempt."""
        for payload in ("null", "42", '"a string"', "[1, 2, 3]"):
            path = tmp_path / "results.json"
            path.write_text(payload)
            assert parse_result(path, tmp_path / "benchmarks") is None

    def test_one_junk_attempt_does_not_abort_the_scan(self, tmp_path: Path) -> None:
        junk = tmp_path / "runs" / "junk"
        junk.mkdir(parents=True)
        (junk / "results.json").write_text("[1, 2, 3]")

        good = tmp_path / "runs" / "task-a"
        good.mkdir(parents=True)
        (good / "results.json").write_text(
            json.dumps(
                {
                    "task_id": "task-a",
                    "scores": {
                        "checkpoints_total": 1,
                        "task_score": 1.0,
                        "score_contract_version": 2,
                        "checkpoints": [],
                    },
                    "task_metadata": {"suite": "s", "difficulty": "medium"},
                    "config": {"mode": "baseline"},
                }
            )
        )

        results = load_all_results([tmp_path / "runs"], tmp_path / "benchmarks")
        assert [r.task_id for r in results] == ["task-a"]


class TestModeSuffixesCoverEveryArm:
    """Three copies of the suffix list existed and every one had missed "cli"
    since that arm was wired, so a <task>_cli directory read as baseline."""

    @pytest.mark.parametrize("mode", ["baseline", "mcp_only", "hybrid", "cli"])
    def test_a_suffixed_batch_dir_resolves_to_its_arm(
        self, tmp_path: Path, mode: str
    ) -> None:
        path = tmp_path / "mcp_batch_v9" / f"task-a_{mode}" / "results.json"
        assert infer_mode(path, {}) == mode

    def test_config_mode_still_wins_over_the_path(self, tmp_path: Path) -> None:
        path = tmp_path / "mcp_batch_v9" / "task-a_baseline" / "results.json"
        assert infer_mode(path, {"config": {"mode": "cli"}}) == "cli"
