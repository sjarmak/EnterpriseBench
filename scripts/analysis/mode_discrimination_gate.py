#!/usr/bin/env python3
"""Mode discrimination gate for Phase 2 scaling.

Reads Phase 1 pilot results, computes Cohen's d for hybrid vs baseline
per task, and reports whether enough tasks show a meaningful effect size
to justify scaling to Phase 2.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskGateResult:
    """Per-task discrimination result."""

    task_id: str
    cohens_d: float | None
    baseline_n: int
    hybrid_n: int
    baseline_mean: float | None
    hybrid_mean: float | None
    passes_threshold: bool


@dataclass(frozen=True)
class GateVerdict:
    """Overall gate verdict."""

    passed: bool
    tasks_passing: int
    tasks_total: int
    threshold: float
    min_tasks_required: int
    per_task: tuple[TaskGateResult, ...]


# ---------------------------------------------------------------------------
# Cohen's d computation
# ---------------------------------------------------------------------------


def cohens_d(group1: list[float], group2: list[float]) -> float | None:
    """Compute Cohen's d (independent samples) for group1 vs group2.

    Returns None if either group has fewer than 2 observations or
    pooled standard deviation is zero.

    Uses the pooled standard deviation formula:
        pooled_sd = sqrt(((n1-1)*s1^2 + (n2-1)*s2^2) / (n1+n2-2))
        d = (mean2 - mean1) / pooled_sd

    Positive d means group2 (hybrid) scores higher than group1 (baseline).
    """
    n1, n2 = len(group1), len(group2)
    if n1 < 2 or n2 < 2:
        return None

    mean1 = sum(group1) / n1
    mean2 = sum(group2) / n2

    var1 = sum((x - mean1) ** 2 for x in group1) / (n1 - 1)
    var2 = sum((x - mean2) ** 2 for x in group2) / (n2 - 1)

    pooled_var = ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)
    pooled_sd = math.sqrt(pooled_var)

    if pooled_sd == 0.0:
        return None

    return (mean2 - mean1) / pooled_sd


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

# Type alias: task_id -> mode -> list of scores
ResultsMap = dict[str, dict[str, list[float]]]


def load_results_csv(csv_path: Path) -> ResultsMap:
    """Load results from summary.csv.

    Rows with empty or non-numeric score values are skipped.
    """
    results: ResultsMap = defaultdict(lambda: defaultdict(list))
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            task_id = row["task_id"]
            mode = row["mode"]
            score_raw = row.get("score", "").strip()
            if not score_raw:
                continue
            try:
                score = float(score_raw)
            except (ValueError, TypeError):
                continue
            results[task_id][mode].append(score)
    return dict(results)


def load_results_manifest(manifest_path: Path) -> ResultsMap:
    """Load results from run_manifest.json.

    Entries with null or non-numeric score values are skipped.
    """
    results: ResultsMap = defaultdict(lambda: defaultdict(list))
    with open(manifest_path) as f:
        manifest = json.load(f)
    for entry in manifest.get("entries", []):
        task_id = entry.get("task_id", "")
        mode = entry.get("mode", "")
        score = entry.get("score")
        if score is None:
            continue
        try:
            score_val = float(score)
        except (ValueError, TypeError):
            continue
        results[task_id][mode].append(score_val)
    return dict(results)


def load_results(results_dir: Path) -> ResultsMap:
    """Load results from the best available source in results_dir.

    Prefers summary.csv; falls back to run_manifest.json.
    """
    csv_path = results_dir / "summary.csv"
    manifest_path = results_dir / "run_manifest.json"

    results: ResultsMap = {}

    if csv_path.exists():
        results = load_results_csv(csv_path)
        if results:
            logger.info("Loaded results from %s", csv_path)
            return results
        logger.info("summary.csv had no scored rows, trying manifest")

    if manifest_path.exists():
        results = load_results_manifest(manifest_path)
        if results:
            logger.info("Loaded results from %s", manifest_path)
            return results

    return results


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------


def evaluate_gate(
    results: ResultsMap,
    *,
    threshold: float = 0.5,
    min_tasks: int = 2,
) -> GateVerdict:
    """Evaluate mode discrimination gate.

    For each task, computes Cohen's d between hybrid and baseline scores.
    A task passes if d > threshold. The gate passes if at least min_tasks
    tasks pass.
    """
    per_task: list[TaskGateResult] = []
    task_ids = sorted(results.keys())

    for task_id in task_ids:
        mode_scores = results[task_id]
        baseline_scores = mode_scores.get("baseline", [])
        hybrid_scores = mode_scores.get("hybrid", [])

        d = cohens_d(baseline_scores, hybrid_scores)

        baseline_mean = (
            sum(baseline_scores) / len(baseline_scores) if baseline_scores else None
        )
        hybrid_mean = sum(hybrid_scores) / len(hybrid_scores) if hybrid_scores else None

        passes = d is not None and d > threshold

        per_task.append(
            TaskGateResult(
                task_id=task_id,
                cohens_d=d,
                baseline_n=len(baseline_scores),
                hybrid_n=len(hybrid_scores),
                baseline_mean=baseline_mean,
                hybrid_mean=hybrid_mean,
                passes_threshold=passes,
            )
        )

    tasks_passing = sum(1 for t in per_task if t.passes_threshold)

    return GateVerdict(
        passed=tasks_passing >= min_tasks,
        tasks_passing=tasks_passing,
        tasks_total=len(per_task),
        threshold=threshold,
        min_tasks_required=min_tasks,
        per_task=tuple(per_task),
    )


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_human(verdict: GateVerdict) -> str:
    """Format verdict as human-readable text."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("Mode Discrimination Gate — Phase 2 Scaling Decision")
    lines.append("=" * 60)
    lines.append("")

    lines.append(
        f"Threshold: Cohen's d > {verdict.threshold}  |  "
        f"Required: {verdict.min_tasks_required}/{verdict.tasks_total} tasks"
    )
    lines.append("")

    lines.append(f"{'Task':<45} {'d':>8} {'Pass?':>6}")
    lines.append("-" * 60)

    for t in verdict.per_task:
        d_str = f"{t.cohens_d:.3f}" if t.cohens_d is not None else "N/A"
        pass_str = "YES" if t.passes_threshold else "no"
        lines.append(f"{t.task_id:<45} {d_str:>8} {pass_str:>6}")

    lines.append("-" * 60)
    lines.append(f"Tasks passing: {verdict.tasks_passing}/{verdict.tasks_total}")
    lines.append("")

    status = "PASS" if verdict.passed else "FAIL"
    lines.append(f"Gate verdict: {status}")
    lines.append("")

    if verdict.passed:
        lines.append("Phase 2 scaling is approved.")
    else:
        lines.append(
            "Phase 2 scaling is NOT approved. Insufficient mode discrimination."
        )

    return "\n".join(lines)


def format_json(verdict: GateVerdict) -> str:
    """Format verdict as JSON."""
    data: dict[str, Any] = {
        "gate": "mode_discrimination",
        "passed": verdict.passed,
        "tasks_passing": verdict.tasks_passing,
        "tasks_total": verdict.tasks_total,
        "threshold": verdict.threshold,
        "min_tasks_required": verdict.min_tasks_required,
        "per_task": [asdict(t) for t in verdict.per_task],
    }
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mode discrimination gate for Phase 2 scaling.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "phase1_pilot",
        help="Directory containing summary.csv or run_manifest.json",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Cohen's d threshold for a task to pass (default: 0.5)",
    )
    parser.add_argument(
        "--min-tasks",
        type=int,
        default=2,
        help="Minimum tasks that must pass (default: 2)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output machine-readable JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    results = load_results(args.results_dir)

    if not results:
        msg = (
            f"No scored results found in {args.results_dir}. "
            "Ensure summary.csv or run_manifest.json contains numeric scores."
        )
        if args.json_output:
            print(
                json.dumps(
                    {
                        "gate": "mode_discrimination",
                        "passed": False,
                        "error": msg,
                    },
                    indent=2,
                )
            )
        else:
            logger.error(msg)
        return 1

    verdict = evaluate_gate(
        results,
        threshold=args.threshold,
        min_tasks=args.min_tasks,
    )

    if args.json_output:
        print(format_json(verdict))
    else:
        print(format_human(verdict))

    return 0 if verdict.passed else 1


if __name__ == "__main__":
    sys.exit(main())
