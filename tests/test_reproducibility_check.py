"""Tests for scripts/reproducibility_check.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Import from the scripts directory
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from reproducibility_check import (
    TaskInfo,
    TaskResult,
    TaskVarianceRecord,
    ReproducibilityReport,
    select_stratified_sample,
    collect_scores,
    compute_variance,
    generate_report,
    _extract_task_id_from_dir,
    _extract_task_score,
    _build_task_info_map,
    discover_tasks,
    auto_detect_results_dirs,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_tasks() -> list[TaskInfo]:
    """Create a representative set of tasks across suites and difficulties."""
    return [
        TaskInfo("dep-001", "dependency_management", "easy"),
        TaskInfo("dep-002", "dependency_management", "medium"),
        TaskInfo("dep-003", "dependency_management", "hard"),
        TaskInfo("dep-004", "dependency_management", "easy"),
        TaskInfo("dep-005", "dependency_management", "medium"),
        TaskInfo("inc-001", "incident_response", "easy"),
        TaskInfo("inc-002", "incident_response", "medium"),
        TaskInfo("inc-003", "incident_response", "hard"),
        TaskInfo("sec-001", "security_operations", "easy"),
        TaskInfo("sec-002", "security_operations", "medium"),
        TaskInfo("cust-001", "customer_escalation", "easy"),
        TaskInfo("cust-002", "customer_escalation", "medium"),
        TaskInfo("cust-003", "customer_escalation", "hard"),
        TaskInfo("cust-004", "customer_escalation", "easy"),
        TaskInfo("feat-001", "feature_delivery", "easy"),
        TaskInfo("feat-002", "feature_delivery", "medium"),
        TaskInfo("feat-003", "feature_delivery", "hard"),
        TaskInfo("feat-004", "feature_delivery", "easy"),
        TaskInfo("feat-005", "feature_delivery", "medium"),
        TaskInfo("feat-006", "feature_delivery", "hard"),
        TaskInfo("debt-001", "technical_debt", "easy"),
        TaskInfo("debt-002", "technical_debt", "medium"),
        TaskInfo("debt-003", "technical_debt", "hard"),
        TaskInfo("plat-001", "platform_engineering", "easy"),
        TaskInfo("plat-002", "platform_engineering", "medium"),
    ]


@pytest.fixture
def results_tree(tmp_path: Path) -> list[Path]:
    """Create a mock results directory tree with results.json files."""
    dirs = []
    for batch in ["run1", "run2", "run3"]:
        batch_dir = tmp_path / batch
        batch_dir.mkdir()
        dirs.append(batch_dir)

    # Task dep-001: consistent scores across 3 runs
    _write_result(dirs[0] / "dep-001", "dep-001", 0.8, "dependency_management", "easy")
    _write_result(dirs[1] / "dep-001", "dep-001", 0.8, "dependency_management", "easy")
    _write_result(dirs[2] / "dep-001", "dep-001", 0.8, "dependency_management", "easy")

    # Task dep-002: moderate variance
    _write_result(
        dirs[0] / "dep-002", "dep-002", 0.9, "dependency_management", "medium"
    )
    _write_result(
        dirs[1] / "dep-002", "dep-002", 0.7, "dependency_management", "medium"
    )
    _write_result(
        dirs[2] / "dep-002", "dep-002", 0.8, "dependency_management", "medium"
    )

    # Task inc-001: high variance (should be flagged at 0.15 threshold)
    _write_result(dirs[0] / "inc-001", "inc-001", 1.0, "incident_response", "easy")
    _write_result(dirs[1] / "inc-001", "inc-001", 0.0, "incident_response", "easy")
    _write_result(dirs[2] / "inc-001", "inc-001", 0.5, "incident_response", "easy")

    # Task with mode suffix
    _write_result(
        dirs[0] / "dep-003_hybrid", "dep-003", 0.6, "dependency_management", "hard"
    )
    _write_result(
        dirs[1] / "dep-003_mcp_only", "dep-003", 0.65, "dependency_management", "hard"
    )

    return dirs


def _write_result(
    dirpath: Path,
    task_id: str,
    score: float,
    suite: str,
    difficulty: str,
) -> None:
    """Write a mock results.json."""
    dirpath.mkdir(parents=True, exist_ok=True)
    data = {
        "task_id": task_id,
        "success": True,
        "scores": {
            "task_score": score,
            "checkpoints": [],
        },
        "task_metadata": {
            "suite": suite,
            "difficulty": difficulty,
        },
    }
    with open(dirpath / "results.json", "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# Tests: select_stratified_sample
# ---------------------------------------------------------------------------


class TestSelectStratifiedSample:
    """Tests for stratified sampling."""

    def test_returns_correct_count(self, sample_tasks: list[TaskInfo]) -> None:
        result = select_stratified_sample(sample_tasks, n=10)
        assert len(result) == 10

    def test_returns_all_when_n_exceeds_total(
        self, sample_tasks: list[TaskInfo]
    ) -> None:
        result = select_stratified_sample(sample_tasks, n=100)
        assert len(result) == len(sample_tasks)

    def test_returns_empty_for_zero(self, sample_tasks: list[TaskInfo]) -> None:
        result = select_stratified_sample(sample_tasks, n=0)
        assert result == []

    def test_covers_multiple_suites(self, sample_tasks: list[TaskInfo]) -> None:
        result = select_stratified_sample(sample_tasks, n=10)
        # Build a lookup
        task_map = {t.task_id: t for t in sample_tasks}
        suites_in_sample = {task_map[tid].suite for tid in result}
        # With 10 out of 25, we should cover most suites
        assert len(suites_in_sample) >= 3

    def test_deterministic(self, sample_tasks: list[TaskInfo]) -> None:
        r1 = select_stratified_sample(sample_tasks, n=10)
        r2 = select_stratified_sample(sample_tasks, n=10)
        assert r1 == r2

    def test_sorted_output(self, sample_tasks: list[TaskInfo]) -> None:
        result = select_stratified_sample(sample_tasks, n=10)
        assert result == sorted(result)

    def test_single_task(self) -> None:
        tasks = [TaskInfo("only-one", "suite_a", "easy")]
        result = select_stratified_sample(tasks, n=1)
        assert result == ["only-one"]

    def test_proportional_allocation(self) -> None:
        """Larger groups should get more slots."""
        tasks = [
            *[TaskInfo(f"big-{i}", "big_suite", "easy") for i in range(20)],
            TaskInfo("small-1", "small_suite", "easy"),
        ]
        result = select_stratified_sample(tasks, n=10)
        task_map = {t.task_id: t for t in tasks}
        big_count = sum(1 for tid in result if task_map[tid].suite == "big_suite")
        small_count = sum(1 for tid in result if task_map[tid].suite == "small_suite")
        assert big_count > small_count


# ---------------------------------------------------------------------------
# Tests: compute_variance
# ---------------------------------------------------------------------------


class TestComputeVariance:
    """Tests for variance computation."""

    def test_identical_scores(self) -> None:
        assert compute_variance([0.8, 0.8, 0.8]) == pytest.approx(0.0, abs=1e-15)

    def test_known_variance(self) -> None:
        # [0, 1] -> mean=0.5, var = ((0.25 + 0.25)/2) = 0.25
        assert compute_variance([0.0, 1.0]) == pytest.approx(0.25)

    def test_single_score(self) -> None:
        assert compute_variance([0.5]) == 0.0

    def test_empty_list(self) -> None:
        assert compute_variance([]) == 0.0

    def test_three_values(self) -> None:
        # [1.0, 0.0, 0.5] -> mean=0.5, var = (0.25+0.25+0)/3 = 0.1667
        result = compute_variance([1.0, 0.0, 0.5])
        assert result == pytest.approx(1 / 6, abs=1e-6)

    def test_small_differences(self) -> None:
        result = compute_variance([0.80, 0.81, 0.79])
        assert result < 0.001


# ---------------------------------------------------------------------------
# Tests: collect_scores
# ---------------------------------------------------------------------------


class TestCollectScores:
    """Tests for score collection from results directories."""

    def test_collects_from_multiple_dirs(self, results_tree: list[Path]) -> None:
        scores = collect_scores(["dep-001", "dep-002"], results_tree)
        assert len(scores["dep-001"]) == 3
        assert len(scores["dep-002"]) == 3

    def test_extracts_correct_scores(self, results_tree: list[Path]) -> None:
        scores = collect_scores(["dep-001"], results_tree)
        score_values = [r.task_score for r in scores["dep-001"]]
        assert all(s == 0.8 for s in score_values)

    def test_handles_mode_suffixed_dirs(self, results_tree: list[Path]) -> None:
        scores = collect_scores(["dep-003"], results_tree)
        assert len(scores["dep-003"]) == 2

    def test_missing_task_returns_empty(self, results_tree: list[Path]) -> None:
        scores = collect_scores(["nonexistent-task"], results_tree)
        assert scores["nonexistent-task"] == []

    def test_nonexistent_dir_warns(self, tmp_path: Path) -> None:
        scores = collect_scores(["dep-001"], [tmp_path / "nope"])
        assert scores["dep-001"] == []

    def test_populates_metadata(self, results_tree: list[Path]) -> None:
        scores = collect_scores(["dep-001"], results_tree)
        result = scores["dep-001"][0]
        assert result.suite == "dependency_management"
        assert result.difficulty == "easy"


# ---------------------------------------------------------------------------
# Tests: _extract_task_id_from_dir
# ---------------------------------------------------------------------------


class TestExtractTaskIdFromDir:
    """Tests for directory name parsing."""

    def test_strips_hybrid_suffix(self) -> None:
        assert _extract_task_id_from_dir("task-001_hybrid") == "task-001"

    def test_strips_mcp_only_suffix(self) -> None:
        assert _extract_task_id_from_dir("task-001_mcp_only") == "task-001"

    def test_strips_baseline_suffix(self) -> None:
        assert _extract_task_id_from_dir("task-001_baseline") == "task-001"

    def test_no_suffix_unchanged(self) -> None:
        assert _extract_task_id_from_dir("task-001") == "task-001"

    def test_complex_id(self) -> None:
        assert (
            _extract_task_id_from_dir("api-contract-grpc-metadata-001_hybrid")
            == "api-contract-grpc-metadata-001"
        )


# ---------------------------------------------------------------------------
# Tests: _extract_task_score
# ---------------------------------------------------------------------------


class TestExtractTaskScore:
    """Tests for score extraction from results dict."""

    def test_normal_score(self) -> None:
        data = {"scores": {"task_score": 2.5}}
        assert _extract_task_score(data) == 2.5

    def test_zero_score(self) -> None:
        data = {"scores": {"task_score": 0.0}}
        assert _extract_task_score(data) == 0.0

    def test_missing_scores_key(self) -> None:
        assert _extract_task_score({}) is None

    def test_missing_task_score(self) -> None:
        data = {"scores": {"checkpoints": []}}
        assert _extract_task_score(data) is None

    def test_non_dict_scores(self) -> None:
        data = {"scores": "invalid"}
        assert _extract_task_score(data) is None


# ---------------------------------------------------------------------------
# Tests: generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """Tests for report generation."""

    def test_basic_report_structure(self) -> None:
        task_info_map = {
            "t1": TaskInfo("t1", "suite_a", "easy"),
            "t2": TaskInfo("t2", "suite_b", "hard"),
        }
        scores_per_task = {
            "t1": [
                TaskResult("t1", "suite_a", "easy", 0.8, "/run1"),
                TaskResult("t1", "suite_a", "easy", 0.8, "/run2"),
            ],
            "t2": [
                TaskResult("t2", "suite_b", "hard", 1.0, "/run1"),
                TaskResult("t2", "suite_b", "hard", 0.0, "/run2"),
            ],
        }
        report = generate_report(
            scores_per_task, task_info_map, variance_threshold=0.15
        )

        assert report.tasks_sampled == 2
        assert report.tasks_with_multiple_runs == 2
        assert len(report.per_task) == 2

    def test_flags_high_variance(self) -> None:
        task_info_map = {"t1": TaskInfo("t1", "s", "e")}
        scores_per_task = {
            "t1": [
                TaskResult("t1", "s", "e", 1.0, "/r1"),
                TaskResult("t1", "s", "e", 0.0, "/r2"),
            ],
        }
        report = generate_report(
            scores_per_task, task_info_map, variance_threshold=0.15
        )
        assert report.tasks_flagged == 1
        assert report.per_task[0].flagged is True

    def test_does_not_flag_low_variance(self) -> None:
        task_info_map = {"t1": TaskInfo("t1", "s", "e")}
        scores_per_task = {
            "t1": [
                TaskResult("t1", "s", "e", 0.8, "/r1"),
                TaskResult("t1", "s", "e", 0.8, "/r2"),
            ],
        }
        report = generate_report(
            scores_per_task, task_info_map, variance_threshold=0.15
        )
        assert report.tasks_flagged == 0
        assert report.per_task[0].flagged is False

    def test_pass_when_few_flagged(self) -> None:
        task_info_map = {f"t{i}": TaskInfo(f"t{i}", "s", "e") for i in range(10)}
        scores_per_task = {
            f"t{i}": [
                TaskResult(f"t{i}", "s", "e", 0.8, "/r1"),
                TaskResult(f"t{i}", "s", "e", 0.8, "/r2"),
            ]
            for i in range(10)
        }
        # Make 1 out of 10 have high variance (10% < 20%)
        scores_per_task["t0"] = [
            TaskResult("t0", "s", "e", 1.0, "/r1"),
            TaskResult("t0", "s", "e", 0.0, "/r2"),
        ]
        report = generate_report(
            scores_per_task, task_info_map, variance_threshold=0.15
        )
        assert report.pass_ is True

    def test_fail_when_many_flagged(self) -> None:
        task_info_map = {f"t{i}": TaskInfo(f"t{i}", "s", "e") for i in range(5)}
        scores_per_task = {
            f"t{i}": [
                TaskResult(f"t{i}", "s", "e", 1.0, "/r1"),
                TaskResult(f"t{i}", "s", "e", 0.0, "/r2"),
            ]
            for i in range(5)
        }
        report = generate_report(
            scores_per_task, task_info_map, variance_threshold=0.15
        )
        # All 5 flagged = 100% > 20%
        assert report.pass_ is False

    def test_empty_scores(self) -> None:
        report = generate_report({}, {}, variance_threshold=0.15)
        assert report.tasks_sampled == 0
        assert report.pass_ is True

    def test_report_to_dict_uses_pass_key(self) -> None:
        report = generate_report({}, {}, variance_threshold=0.15)
        d = report.to_dict()
        assert "pass" in d
        assert "pass_" not in d

    def test_mean_and_max_variance(self) -> None:
        task_info_map = {
            "t1": TaskInfo("t1", "s", "e"),
            "t2": TaskInfo("t2", "s", "e"),
        }
        scores_per_task = {
            "t1": [
                TaskResult("t1", "s", "e", 0.8, "/r1"),
                TaskResult("t1", "s", "e", 0.8, "/r2"),
            ],
            "t2": [
                TaskResult("t2", "s", "e", 1.0, "/r1"),
                TaskResult("t2", "s", "e", 0.0, "/r2"),
            ],
        }
        report = generate_report(scores_per_task, task_info_map)
        # t1 var=0, t2 var=0.25, mean=0.125, max=0.25
        assert report.mean_variance == pytest.approx(0.125, abs=1e-4)
        assert report.max_variance == pytest.approx(0.25, abs=1e-4)


# ---------------------------------------------------------------------------
# Tests: discover_tasks
# ---------------------------------------------------------------------------


class TestDiscoverTasks:
    """Tests for task discovery from TOML files."""

    def test_discovers_tasks_from_dir(self, tmp_path: Path) -> None:
        suite_dir = tmp_path / "my_suite" / "task-001"
        suite_dir.mkdir(parents=True)
        toml_content = """
[task]
id = "task-001"
suite = "my_suite"
difficulty = "easy"
"""
        (suite_dir / "task.toml").write_text(toml_content)
        tasks = discover_tasks(tmp_path)
        assert len(tasks) == 1
        assert tasks[0].task_id == "task-001"
        assert tasks[0].suite == "my_suite"
        assert tasks[0].difficulty == "easy"

    def test_skips_incomplete_toml(self, tmp_path: Path) -> None:
        suite_dir = tmp_path / "suite" / "task-bad"
        suite_dir.mkdir(parents=True)
        (suite_dir / "task.toml").write_text("[task]\nid = 'bad'\n")
        tasks = discover_tasks(tmp_path)
        assert len(tasks) == 0


# ---------------------------------------------------------------------------
# Tests: integration (collect + generate)
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests combining collection and report generation."""

    def test_end_to_end_with_mock_dirs(
        self, results_tree: list[Path], sample_tasks: list[TaskInfo]
    ) -> None:
        task_ids = ["dep-001", "dep-002", "inc-001"]
        scores = collect_scores(task_ids, results_tree)
        task_info_map = _build_task_info_map(sample_tasks)
        scores_with_data = {tid: r for tid, r in scores.items() if r}
        report = generate_report(
            scores_with_data, task_info_map, variance_threshold=0.15
        )

        assert report.tasks_sampled >= 2
        # inc-001 has high variance, should be flagged
        flagged_ids = [r.task_id for r in report.per_task if r.flagged]
        assert "inc-001" in flagged_ids

    def test_report_json_serialization(
        self, results_tree: list[Path], sample_tasks: list[TaskInfo]
    ) -> None:
        task_ids = ["dep-001"]
        scores = collect_scores(task_ids, results_tree)
        task_info_map = _build_task_info_map(sample_tasks)
        scores_with_data = {tid: r for tid, r in scores.items() if r}
        report = generate_report(scores_with_data, task_info_map)

        # Should serialize without error
        d = report.to_dict()
        json_str = json.dumps(d, indent=2)
        parsed = json.loads(json_str)
        assert "pass" in parsed
        assert "per_task" in parsed
        assert len(parsed["per_task"]) == 1
