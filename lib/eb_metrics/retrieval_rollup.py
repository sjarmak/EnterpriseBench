"""Per-config retrieval rollup for the EnterpriseBench tool-access study.

codeprobe's ``quality_metrics`` block surfaces per-row retrieval detail and a
``low_recall`` flag *count*, but it does not mean-aggregate retrieval quality by
config. The 3-arm study (baseline / stock-MCP / CLI) needs exactly that: the
mean ``file_recall``, ``context_efficiency``, and ``MRR`` per config, computed
over **matched telemetry only** — the tasks observed in *every* arm — so the
arms are compared on the same task set rather than on whatever each arm happened
to complete.

This module walks ``results/<run>/results.json`` files, joins each single-record
run's ``agent_trace.jsonl`` with its task ground truth via the shared
:mod:`eb_metrics.retrieval_extraction` machinery, groups the resulting
:class:`~eb_metrics.ir_metrics.IRScores` by config, and mean-aggregates.

Weighting: repeats of one (config, task) are averaged into a single cell first,
then the config mean is an equal-weight average over its matched cells — so each
task counts once regardless of how many times it was repeated.

ZFC compliance: pure structural walk + deterministic arithmetic mean over the
already-computed IR scalars. No model call, no judgment.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from eb_metrics.ir_metrics import IRScores
from eb_metrics.retrieval_extraction import compute_run_ir_scores, resolve_ground_truth

logger = logging.getLogger(__name__)

__all__ = [
    "RunRetrieval",
    "MeanRetrieval",
    "iter_run_retrievals",
    "aggregate_retrieval",
]

_SCALAR_FIELDS = ("file_recall", "context_efficiency", "mrr", "map_score")
_DICT_FIELDS = ("recall", "f1", "ndcg", "precision")


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


@dataclass(frozen=True)
class RunRetrieval:
    """One run's retrieval scores plus the config bucket it belongs to."""

    config: str
    task_id: str
    scores: IRScores


@dataclass(frozen=True)
class MeanRetrieval:
    """Equal-weight mean of a set of retrieval units (runs, or task cells).

    ``n`` is the number of underlying units averaged (runs for a cell, matched
    tasks for a config summary).
    """

    file_recall: float
    context_efficiency: float
    mrr: float
    map_score: float
    recall: dict[int, float]
    f1: dict[int, float]
    ndcg: dict[int, float]
    precision: dict[int, float]
    n: int

    @classmethod
    def from_scores(cls, s: IRScores) -> "MeanRetrieval":
        return cls(
            file_recall=s.file_recall,
            context_efficiency=s.context_efficiency,
            mrr=s.mrr,
            map_score=s.map_score,
            recall=dict(s.recall),
            f1=dict(s.f1),
            ndcg=dict(s.ndcg),
            precision=dict(s.precision),
            n=1,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "mean_file_recall": self.file_recall,
            "mean_context_efficiency": self.context_efficiency,
            "mean_mrr": self.mrr,
            "mean_map": self.map_score,
            "mean_recall_at_k": {str(k): v for k, v in sorted(self.recall.items())},
            "mean_f1_at_k": {str(k): v for k, v in sorted(self.f1.items())},
            "mean_ndcg_at_k": {str(k): v for k, v in sorted(self.ndcg.items())},
            "mean_precision_at_k": {str(k): v for k, v in sorted(self.precision.items())},
        }


def _combine(units: list[MeanRetrieval]) -> MeanRetrieval:
    """Equal-weight mean of several MeanRetrieval units.

    ``@k`` dicts are meaned key-wise over the union of keys (every unit shares
    :data:`~eb_metrics.ir_metrics.DEFAULT_K_VALUES`, so the union is stable).
    """
    if not units:
        return MeanRetrieval(0.0, 0.0, 0.0, 0.0, {}, {}, {}, {}, 0)

    scalars = {f: _mean([getattr(u, f) for u in units]) for f in _SCALAR_FIELDS}
    dicts: dict[str, dict[int, float]] = {}
    for field in _DICT_FIELDS:
        ks = sorted({k for u in units for k in getattr(u, field)})
        dicts[field] = {k: _mean([getattr(u, field).get(k, 0.0) for u in units]) for k in ks}

    return MeanRetrieval(
        file_recall=scalars["file_recall"],
        context_efficiency=scalars["context_efficiency"],
        mrr=scalars["mrr"],
        map_score=scalars["map_score"],
        recall=dicts["recall"],
        f1=dicts["f1"],
        ndcg=dicts["ndcg"],
        precision=dicts["precision"],
        n=len(units),
    )


def _config_of(record: Mapping[str, Any], run_name: str, config_from: str) -> str | None:
    """Derive the config bucket for a record. ``None`` → skip (unattributable)."""
    if config_from == "run_name":
        return run_name
    mode = record.get("config", {}).get("mode") if isinstance(record.get("config"), Mapping) else None
    return mode if isinstance(mode, str) and mode else None


def iter_run_retrievals(
    runs_dir: Path,
    benchmarks_dir: Path,
    *,
    pattern: str = "**/results.json",
    config_from: str = "mode",
    trace_name: str = "agent_trace.jsonl",
    dropped: dict[str, int] | None = None,
) -> Iterator[RunRetrieval]:
    """Yield a :class:`RunRetrieval` for every scorable single-record run.

    A run is scorable when its ``results.json`` holds exactly one record, has a
    sibling ``<trace_name>``, resolves to a config bucket, and produces a
    non-``None`` :class:`IRScores` (real retrieval signal). ``dropped``, when
    passed, is incremented with counts of the skip reasons for transparency.
    """
    runs_dir = Path(runs_dir)
    benchmarks_dir = Path(benchmarks_dir)
    if not runs_dir.is_dir():
        raise FileNotFoundError(f"runs_dir not found: {runs_dir}")
    counts = dropped if dropped is not None else {}

    def _bump(key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    for results_path in sorted(runs_dir.glob(pattern)):
        if not results_path.is_file():
            continue
        try:
            payload = json.loads(results_path.read_text())
        except (OSError, json.JSONDecodeError) as err:
            logger.warning("skipping %s: %s", results_path, err)
            _bump("unreadable")
            continue

        records = payload if isinstance(payload, list) else [payload]
        run_name = results_path.parent.name
        trace_path = results_path.parent / trace_name
        # One sibling trace cannot be attributed to several tasks.
        if len(records) != 1 or not trace_path.is_file():
            _bump("no_single_trace")
            continue

        record = records[0]
        if not isinstance(record, Mapping):
            continue
        task_id = record.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            _bump("no_task_id")
            continue

        config = _config_of(record, run_name, config_from)
        if config is None:
            _bump("no_config")
            continue

        suite = None
        meta = record.get("task_metadata")
        if isinstance(meta, Mapping) and isinstance(meta.get("suite"), str):
            suite = meta["suite"]
        gt_path = resolve_ground_truth(benchmarks_dir, task_id, suite)
        if gt_path is None:
            _bump("no_ground_truth")
            continue

        scores = compute_run_ir_scores(trace_path, gt_path, task_id, config)
        if scores is None:
            _bump("no_retrieval_signal")
            continue

        yield RunRetrieval(config=config, task_id=task_id, scores=scores)


def aggregate_retrieval(
    runs: Iterable[RunRetrieval],
    *,
    matched_only: bool = True,
    config_key: str = "mode",
    dropped: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Roll up per-run retrieval scores into a per-config mean summary.

    Repeats of one (config, task) are averaged into a cell; the config mean is
    then an equal-weight average over its (matched) cells. When
    ``matched_only`` is set, the mean is taken over only the tasks observed in
    *every* config, and the per-config task ids dropped for being unmatched are
    reported under ``dropped['unmatched_by_config']``.
    """
    # (config, task_id) -> list of per-run IRScores
    cells: dict[tuple[str, str], list[IRScores]] = defaultdict(list)
    for r in runs:
        cells[(r.config, r.task_id)].append(r.scores)

    cell_means: dict[tuple[str, str], MeanRetrieval] = {
        key: _combine([MeanRetrieval.from_scores(s) for s in scores])
        for key, scores in cells.items()
    }
    n_runs: dict[str, int] = defaultdict(int)
    tasks_by_config: dict[str, set[str]] = defaultdict(set)
    for (config, task_id), scores in cells.items():
        n_runs[config] += len(scores)
        tasks_by_config[config].add(task_id)

    configs = sorted(tasks_by_config)
    if matched_only and configs:
        matched: set[str] = set.intersection(*(tasks_by_config[c] for c in configs))
    else:
        matched = set().union(*tasks_by_config.values()) if tasks_by_config else set()

    per_config: dict[str, Any] = {}
    unmatched: dict[str, list[str]] = {}
    for config in configs:
        selected = sorted(t for t in tasks_by_config[config] if t in matched)
        summary = _combine([cell_means[(config, t)] for t in selected])
        entry = summary.to_dict()
        entry["n_tasks_matched"] = len(selected)
        entry["n_tasks_observed"] = len(tasks_by_config[config])
        entry["n_runs"] = n_runs[config]
        per_config[config] = entry
        missed = sorted(tasks_by_config[config] - matched)
        if missed:
            unmatched[config] = missed

    out_dropped = dict(dropped) if dropped else {}
    if unmatched:
        out_dropped["unmatched_by_config"] = unmatched

    return {
        "schema_version": 1,
        "config_key": config_key,
        "matched_only": matched_only,
        "configs": configs,
        "matched_task_count": len(matched),
        "matched_task_ids": sorted(matched),
        "per_config": per_config,
        "dropped": out_dropped,
    }
