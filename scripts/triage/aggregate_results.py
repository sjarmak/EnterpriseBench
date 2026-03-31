#!/usr/bin/env python3
"""Checkpoint-aware result aggregation for EnterpriseBench.

Consumes triage_run.py output (or runs triage internally from a results dir)
and produces structured JSON with per-group breakdowns by suite, task_type,
difficulty, and difficulty_stratum.

Usage:
    python3 scripts/triage/aggregate_results.py --triage-file triage.json
    python3 scripts/triage/aggregate_results.py --results-dir results/runs
    python3 scripts/triage/aggregate_results.py --results-dir results/runs --output report.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — allow importing triage_run when run as script
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR.parent))
sys.path.insert(0, str(_THIS_DIR))


# ---------------------------------------------------------------------------
# Histogram bins
# ---------------------------------------------------------------------------

_HISTOGRAM_BINS: list[tuple[str, float, float]] = [
    ("0", 0.0, 0.0),
    ("(0,1]", 0.001, 1.0),
    ("(1,2]", 1.001, 2.0),
    ("(2,3]", 2.001, 3.0),
    ("(3,5]", 3.001, 5.0),
    ("(5,+)", 5.001, float("inf")),
]


def compute_score_histogram(scores: list[float]) -> list[dict[str, Any]]:
    """Compute a histogram of scores using fixed bins.

    Returns:
        List of dicts with 'bin' (label) and 'count' keys.
    """
    result: list[dict[str, Any]] = []
    for label, lo, hi in _HISTOGRAM_BINS:
        if lo == 0.0 and hi == 0.0:
            count = sum(1 for s in scores if s == 0.0)
        elif hi == float("inf"):
            count = sum(1 for s in scores if s >= lo)
        else:
            count = sum(1 for s in scores if lo <= s <= hi)
        result.append({"bin": label, "count": count})
    return result


# ---------------------------------------------------------------------------
# Per-group statistics
# ---------------------------------------------------------------------------


def compute_group_stats(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate statistics for a group of classified tasks.

    Args:
        tasks: List of triage task dicts (from triage_run.classify_task output).

    Returns:
        Dict with count, pass_rate, score stats, checkpoint stats, category dist.
    """
    count = len(tasks)
    if count == 0:
        return {
            "count": 0,
            "pass_count": 0,
            "pass_rate": 0.0,
            "score_mean": 0.0,
            "score_median": 0.0,
            "score_min": 0.0,
            "score_max": 0.0,
            "checkpoints_passed_total": 0,
            "checkpoints_total": 0,
            "checkpoint_pass_rate": 0.0,
            "category_distribution": {},
        }

    scores = [t.get("score", 0.0) or 0.0 for t in tasks]
    pass_count = sum(1 for t in tasks if t.get("category") == "pass")

    cp_passed = sum(t.get("checkpoints_passed", 0) for t in tasks)
    cp_total = sum(t.get("checkpoints_total", 0) for t in tasks)

    # Category distribution
    categories = [t.get("category", "unknown") for t in tasks]
    cat_dist = dict(Counter(categories))

    return {
        "count": count,
        "pass_count": pass_count,
        "pass_rate": pass_count / count,
        "score_mean": statistics.mean(scores),
        "score_median": statistics.median(scores),
        "score_min": min(scores),
        "score_max": max(scores),
        "checkpoints_passed_total": cp_passed,
        "checkpoints_total": cp_total,
        "checkpoint_pass_rate": cp_passed / cp_total if cp_total > 0 else 0.0,
        "category_distribution": cat_dist,
    }


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------


def _group_by_key(
    tasks: list[dict[str, Any]], key_fn: Any
) -> dict[str, list[dict[str, Any]]]:
    """Group tasks by a key function into a dict of lists."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        key = key_fn(task)
        if not key:
            continue
        groups.setdefault(key, []).append(task)
    return groups


def _metadata_getter(field_name: str):
    """Return a function that extracts a metadata field from a task dict."""
    def getter(task: dict[str, Any]) -> str:
        meta = task.get("metadata", {})
        return meta.get(field_name, "") or ""
    return getter


# ---------------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------------


def aggregate(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate classified tasks into a structured report.

    Args:
        tasks: List of triage task dicts.

    Returns:
        Dict with overall stats, per-group breakdowns, histogram, and per_task.
    """
    overall = compute_group_stats(tasks)
    scores = [t.get("score", 0.0) or 0.0 for t in tasks]

    # Group by suite
    by_suite_groups = _group_by_key(tasks, _metadata_getter("suite"))
    by_suite = {k: compute_group_stats(v) for k, v in sorted(by_suite_groups.items())}

    # Group by task_type
    by_type_groups = _group_by_key(tasks, _metadata_getter("task_type"))
    by_type = {k: compute_group_stats(v) for k, v in sorted(by_type_groups.items())}

    # Group by difficulty
    by_diff_groups = _group_by_key(tasks, _metadata_getter("difficulty"))
    by_diff = {k: compute_group_stats(v) for k, v in sorted(by_diff_groups.items())}

    # Group by difficulty_stratum (may not be present in all tasks)
    by_stratum_groups = _group_by_key(tasks, _metadata_getter("difficulty_stratum"))
    by_stratum = {k: compute_group_stats(v) for k, v in sorted(by_stratum_groups.items())}

    result: dict[str, Any] = {
        "overall": overall,
        "by_suite": by_suite,
        "by_task_type": by_type,
        "by_difficulty": by_diff,
        "score_histogram": compute_score_histogram(scores),
        "per_task": tasks,
    }

    # Only include stratum breakdown if any tasks have it
    if by_stratum:
        result["by_difficulty_stratum"] = by_stratum

    return result


# ---------------------------------------------------------------------------
# AggregateReport — typed wrapper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregateReport:
    """Immutable aggregate report with serialization helpers."""

    overall: dict[str, Any]
    by_suite: dict[str, Any]
    by_task_type: dict[str, Any]
    by_difficulty: dict[str, Any]
    score_histogram: list[dict[str, Any]]
    per_task: list[dict[str, Any]]
    by_difficulty_stratum: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""

    @classmethod
    def from_tasks(cls, tasks: list[dict[str, Any]]) -> AggregateReport:
        """Create an AggregateReport from a list of classified tasks."""
        data = aggregate(tasks)
        return cls(
            overall=data["overall"],
            by_suite=data["by_suite"],
            by_task_type=data["by_task_type"],
            by_difficulty=data["by_difficulty"],
            score_histogram=data["score_histogram"],
            per_task=data["per_task"],
            by_difficulty_stratum=data.get("by_difficulty_stratum", {}),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict suitable for JSON serialization."""
        result: dict[str, Any] = {
            "generated_at": self.generated_at or datetime.now(timezone.utc).isoformat(),
            "overall": self.overall,
            "by_suite": self.by_suite,
            "by_task_type": self.by_task_type,
            "by_difficulty": self.by_difficulty,
            "score_histogram": self.score_histogram,
            "per_task": self.per_task,
        }
        if self.by_difficulty_stratum:
            result["by_difficulty_stratum"] = self.by_difficulty_stratum
        return result

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


def _load_triage_file(path: Path) -> list[dict[str, Any]]:
    """Load tasks from a triage JSON file (output of triage_run.py)."""
    data = json.loads(path.read_text())
    return data.get("per_task", [])


def _load_from_results_dir(results_dir: Path) -> list[dict[str, Any]]:
    """Run triage classification on a results directory."""
    from triage.triage_run import scan_results_dir, TriageCategory

    raw_tasks = scan_results_dir(results_dir)
    # Normalize TriageCategory enums to strings for downstream processing
    normalized: list[dict[str, Any]] = []
    for task in raw_tasks:
        t = dict(task)
        cat = t.get("category")
        if isinstance(cat, TriageCategory):
            t["category"] = cat.value
        normalized.append(t)
    return normalized


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Aggregate EnterpriseBench results with checkpoint-aware breakdowns.",
    )
    parser.add_argument(
        "--triage-file",
        default=None,
        help="Path to triage JSON file (output of triage_run.py). Mutually exclusive with --results-dir.",
    )
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Path to results directory to triage and aggregate (default: results/runs).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write JSON report to file (default: stdout).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    args = parse_args(argv)

    # Determine input source
    if args.triage_file:
        triage_path = Path(args.triage_file)
        if not triage_path.is_file():
            print(f"Error: triage file not found: {triage_path}", file=sys.stderr)
            sys.exit(1)
        tasks = _load_triage_file(triage_path)
    elif args.results_dir:
        results_dir = Path(args.results_dir)
        if not results_dir.is_dir():
            print(f"Error: results directory not found: {results_dir}", file=sys.stderr)
            sys.exit(1)
        tasks = _load_from_results_dir(results_dir)
    else:
        # Default to results/runs
        results_dir = Path("results/runs")
        if not results_dir.is_dir():
            print(f"Error: default results directory not found: {results_dir}", file=sys.stderr)
            sys.exit(1)
        tasks = _load_from_results_dir(results_dir)

    report = AggregateReport.from_tasks(tasks)
    output = report.to_json()

    if args.output:
        Path(args.output).write_text(output + "\n")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
