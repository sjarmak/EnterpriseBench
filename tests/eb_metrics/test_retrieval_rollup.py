"""Tests for the per-config retrieval rollup (co-4cb.1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from eb_metrics.ir_metrics import compute_ir_scores
from eb_metrics.retrieval_rollup import (
    MeanRetrieval,
    RunRetrieval,
    aggregate_retrieval,
    iter_run_retrievals,
)


# ---------------------------------------------------------------------------
# aggregate_retrieval — pure, fixture-free (uses synthetic IRScores)
# ---------------------------------------------------------------------------


def _scores(task_id: str, config: str, retrieved: list[str], relevant: list[str]) -> RunRetrieval:
    return RunRetrieval(
        config=config,
        task_id=task_id,
        scores=compute_ir_scores(retrieved, relevant, task_id, config),
    )


class TestAggregateMeans:
    def test_mean_over_tasks_per_config(self) -> None:
        runs = [
            # baseline: task A recall 1.0, task B recall 0.0  -> mean 0.5
            _scores("A", "baseline", ["x.py"], ["x.py"]),
            _scores("B", "baseline", ["z.py"], ["y.py"]),
            _scores("A", "mcp_only", ["x.py"], ["x.py"]),
            _scores("B", "mcp_only", ["y.py"], ["y.py"]),
        ]
        out = aggregate_retrieval(runs)
        assert out["per_config"]["baseline"]["mean_file_recall"] == 0.5
        assert out["per_config"]["mcp_only"]["mean_file_recall"] == 1.0
        assert out["matched_task_count"] == 2

    def test_repeats_average_into_one_task_cell(self) -> None:
        # Two repeats of (baseline, A): recall 1.0 and 0.0 -> cell mean 0.5;
        # config mean over the single task = 0.5 (repeats do not double-weight).
        runs = [
            _scores("A", "baseline", ["x.py"], ["x.py"]),
            _scores("A", "baseline", ["z.py"], ["x.py"]),
            _scores("A", "mcp_only", ["x.py"], ["x.py"]),
        ]
        out = aggregate_retrieval(runs)
        assert out["per_config"]["baseline"]["mean_file_recall"] == 0.5
        assert out["per_config"]["baseline"]["n_runs"] == 2
        assert out["per_config"]["baseline"]["n_tasks_matched"] == 1


class TestMatchedTelemetry:
    def test_matched_only_drops_unshared_tasks(self) -> None:
        runs = [
            _scores("A", "baseline", ["x.py"], ["x.py"]),
            _scores("B", "baseline", ["x.py"], ["x.py"]),  # only baseline has B
            _scores("A", "mcp_only", ["z.py"], ["x.py"]),  # A recall 0.0 here
        ]
        out = aggregate_retrieval(runs)
        assert out["matched_task_ids"] == ["A"]
        # baseline mean over matched {A} = 1.0 (B excluded)
        assert out["per_config"]["baseline"]["mean_file_recall"] == 1.0
        assert out["per_config"]["baseline"]["n_tasks_matched"] == 1
        assert out["per_config"]["baseline"]["n_tasks_observed"] == 2
        assert out["dropped"]["unmatched_by_config"]["baseline"] == ["B"]

    def test_all_mode_keeps_every_task(self) -> None:
        runs = [
            _scores("A", "baseline", ["x.py"], ["x.py"]),
            _scores("B", "baseline", ["z.py"], ["x.py"]),
            _scores("A", "mcp_only", ["x.py"], ["x.py"]),
        ]
        out = aggregate_retrieval(runs, matched_only=False)
        # baseline mean over {A:1.0, B:0.0} = 0.5
        assert out["per_config"]["baseline"]["mean_file_recall"] == 0.5
        assert out["per_config"]["baseline"]["n_tasks_matched"] == 2

    def test_empty_runs(self) -> None:
        out = aggregate_retrieval([])
        assert out["configs"] == []
        assert out["matched_task_count"] == 0
        assert out["per_config"] == {}


class TestMeanRetrievalShape:
    def test_to_dict_has_headline_and_at_k(self) -> None:
        s = compute_ir_scores(["x.py"], ["x.py"], "A", "baseline")
        d = MeanRetrieval.from_scores(s).to_dict()
        for key in (
            "mean_file_recall", "mean_context_efficiency", "mean_mrr", "mean_map",
            "mean_recall_at_k", "mean_f1_at_k", "mean_ndcg_at_k",
        ):
            assert key in d
        assert set(d["mean_recall_at_k"]) == {"1", "3", "5", "10"}


# ---------------------------------------------------------------------------
# iter_run_retrievals — walks a results/ tree, with the drop-reason ledger
# ---------------------------------------------------------------------------


def _make_run(
    root: Path,
    run_name: str,
    *,
    task_id: str,
    mode: str | None,
    with_trace: bool = True,
    n_records: int = 1,
) -> None:
    run_dir = root / run_name
    run_dir.mkdir(parents=True)
    record: dict[str, Any] = {
        "task_id": task_id,
        "success": True,
        "phase": "complete",
        "config": {"mode": mode} if mode is not None else {},
        "task_metadata": {"suite": "platform_engineering"},
    }
    payload: Any = record if n_records == 1 else [record for _ in range(n_records)]
    (run_dir / "results.json").write_text(json.dumps(payload))
    if with_trace:
        trace = {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Read",
                 "input": {"file_path": "/workspace/repo/pkg/x.py"}}
            ]},
        }
        (run_dir / "agent_trace.jsonl").write_text(json.dumps(trace) + "\n")


def _make_benchmarks(root: Path, task_id: str, required: list[str]) -> None:
    tdir = root / "platform_engineering" / task_id
    tdir.mkdir(parents=True)
    (tdir / "ground_truth.json").write_text(
        json.dumps({"required_files": [{"repo": "repo", "path": p} for p in required]})
    )


class TestIterRunRetrievals:
    def test_walks_and_scores_by_mode(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / "results"
        bench_dir = tmp_path / "benchmarks"
        _make_benchmarks(bench_dir, "task-a", ["pkg/x.py"])
        _make_run(runs_dir, "run_base", task_id="task-a", mode="baseline")
        _make_run(runs_dir, "run_mcp", task_id="task-a", mode="mcp_only")

        dropped: dict[str, int] = {}
        runs = list(iter_run_retrievals(runs_dir, bench_dir, dropped=dropped))
        configs = sorted(r.config for r in runs)
        assert configs == ["baseline", "mcp_only"]
        # both retrieved pkg/x.py (the required file) -> recall 1.0
        assert all(r.scores.file_recall == 1.0 for r in runs)

    def test_drops_are_counted(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / "results"
        bench_dir = tmp_path / "benchmarks"
        _make_benchmarks(bench_dir, "task-a", ["pkg/x.py"])
        _make_run(runs_dir, "no_mode", task_id="task-a", mode=None)
        _make_run(runs_dir, "no_trace", task_id="task-a", mode="baseline", with_trace=False)
        _make_run(runs_dir, "multi", task_id="task-a", mode="baseline", n_records=2)
        _make_run(runs_dir, "no_gt", task_id="task-missing", mode="baseline")

        dropped: dict[str, int] = {}
        runs = list(iter_run_retrievals(runs_dir, bench_dir, dropped=dropped))
        assert runs == []
        assert dropped["no_config"] == 1
        assert dropped["no_single_trace"] == 2  # no_trace + multi-record
        assert dropped["no_ground_truth"] == 1

    def test_config_from_run_name(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / "results"
        bench_dir = tmp_path / "benchmarks"
        _make_benchmarks(bench_dir, "task-a", ["pkg/x.py"])
        _make_run(runs_dir, "arm_X", task_id="task-a", mode=None)
        runs = list(iter_run_retrievals(runs_dir, bench_dir, config_from="run_name"))
        assert [r.config for r in runs] == ["arm_X"]


def test_end_to_end_rollup(tmp_path: Path) -> None:
    """Walk a small tree and roll it up in one shot."""
    runs_dir = tmp_path / "results"
    bench_dir = tmp_path / "benchmarks"
    _make_benchmarks(bench_dir, "task-a", ["pkg/x.py"])
    _make_run(runs_dir, "base_a", task_id="task-a", mode="baseline")
    _make_run(runs_dir, "mcp_a", task_id="task-a", mode="mcp_only")

    dropped: dict[str, int] = {}
    runs = list(iter_run_retrievals(runs_dir, bench_dir, dropped=dropped))
    out = aggregate_retrieval(runs, dropped=dropped)
    assert out["matched_task_count"] == 1
    assert out["per_config"]["baseline"]["mean_file_recall"] == 1.0
    assert out["per_config"]["mcp_only"]["mean_file_recall"] == 1.0
