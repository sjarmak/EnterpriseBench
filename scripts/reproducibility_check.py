#!/usr/bin/env python3
"""Reproducibility validation for EnterpriseBench benchmark tasks.

Selects a stratified sample of tasks, compares scores across multiple runs,
computes per-task variance, flags tasks with high variance, and generates
a reproducibility report.

Usage:
    python scripts/reproducibility_check.py
    python scripts/reproducibility_check.py --sample-size 10 --variance-threshold 0.2
    python scripts/reproducibility_check.py --results-dir results/runs --results-dir results/mcp_batch
    python scripts/reproducibility_check.py --output results/repro_report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from lib.shared import discover_results_dirs, strip_mode_suffix

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskInfo:
    """Minimal task metadata for stratified sampling."""

    task_id: str
    suite: str
    difficulty: str


@dataclass(frozen=True)
class TaskResult:
    """A single run result for a task."""

    task_id: str
    suite: str
    difficulty: str
    task_score: float
    source_dir: str


@dataclass(frozen=True)
class TaskVarianceRecord:
    """Aggregated reproducibility data for one task."""

    task_id: str
    suite: str
    difficulty: str
    num_runs: int
    scores: list[float]
    mean_score: float
    variance: float
    flagged: bool


@dataclass(frozen=True)
class ReproducibilityReport:
    """Full reproducibility report."""

    generated_at: str
    sample_size: int
    variance_threshold: float
    tasks_sampled: int
    tasks_with_multiple_runs: int
    tasks_flagged: int
    mean_variance: float
    max_variance: float
    pass_: bool  # "pass" is a keyword
    per_task: list[TaskVarianceRecord]

    def to_dict(self) -> dict:
        """Serialize to dict with 'pass' instead of 'pass_'."""
        d: dict = {}
        for key, val in asdict(self).items():
            out_key = "pass" if key == "pass_" else key
            d[out_key] = val
        return d


# ---------------------------------------------------------------------------
# Task discovery
# ---------------------------------------------------------------------------


def discover_tasks(benchmarks_dir: Path | None = None) -> list[TaskInfo]:
    """Discover all task definitions from task.toml files under benchmarks/."""
    benchmarks_dir = benchmarks_dir or ROOT / "benchmarks"
    tasks: list[TaskInfo] = []
    for toml_path in sorted(benchmarks_dir.rglob("task.toml")):
        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
            task_section = data.get("task", {})
            task_id = task_section.get("id", "")
            suite = task_section.get("suite", "")
            difficulty = task_section.get("difficulty", "")
            if task_id and suite and difficulty:
                tasks.append(
                    TaskInfo(
                        task_id=task_id,
                        suite=suite,
                        difficulty=difficulty,
                    )
                )
        except Exception:
            logger.warning("Failed to parse %s", toml_path)
    return tasks


# ---------------------------------------------------------------------------
# Stratified sampling
# ---------------------------------------------------------------------------


def select_stratified_sample(
    tasks: Sequence[TaskInfo],
    n: int = 25,
) -> list[str]:
    """Select n tasks stratified by suite and difficulty.

    Groups tasks by (suite, difficulty), then allocates proportionally.
    Returns a list of task_ids.
    """
    if n <= 0:
        return []
    if n >= len(tasks):
        return [t.task_id for t in tasks]

    # Group by (suite, difficulty)
    groups: dict[tuple[str, str], list[TaskInfo]] = {}
    for t in tasks:
        key = (t.suite, t.difficulty)
        groups.setdefault(key, []).append(t)

    total = len(tasks)
    selected: list[str] = []

    # Proportional allocation using largest-remainder method
    allocations: dict[tuple[str, str], int] = {}
    remainders: list[tuple[tuple[str, str], float]] = []

    for key, members in groups.items():
        proportion = len(members) / total * n
        base = int(proportion)
        allocations[key] = base
        remainders.append((key, proportion - base))

    allocated_total = sum(allocations.values())

    # Distribute remaining slots to groups with largest remainders
    if allocated_total < n:
        remainders.sort(key=lambda x: -x[1])
        for key, _ in remainders:
            if allocated_total >= n:
                break
            if allocations[key] < len(groups[key]):
                allocations[key] += 1
                allocated_total += 1

    # Safety: trim if rounding somehow over-allocated
    if allocated_total > n:
        remainders.sort(key=lambda x: x[1])
        for key, _ in remainders:
            if allocated_total <= n:
                break
            if allocations[key] > 0:
                allocations[key] -= 1
                allocated_total -= 1

    # Pick from each group (deterministic: sorted by task_id)
    for key, count in allocations.items():
        members = sorted(groups[key], key=lambda t: t.task_id)
        selected.extend(t.task_id for t in members[:count])

    return sorted(selected)


# ---------------------------------------------------------------------------
# Score collection
# ---------------------------------------------------------------------------


def _extract_task_id_from_dir(dirname: str) -> str:
    """Extract task_id from a directory name, stripping mode suffixes."""
    task_id, _ = strip_mode_suffix(dirname)
    return task_id


def collect_scores(
    task_ids: Sequence[str],
    results_dirs: Sequence[Path],
) -> dict[str, list[TaskResult]]:
    """Gather all scores for each task_id across results directories.

    Scans each results_dir for subdirectories containing results.json.
    Matches task_ids by the task_id field in the JSON (preferred) or
    by parsing the directory name.
    """
    task_id_set = set(task_ids)
    scores: dict[str, list[TaskResult]] = {tid: [] for tid in task_ids}

    for results_dir in results_dirs:
        if not results_dir.is_dir():
            logger.warning("Results directory does not exist: %s", results_dir)
            continue
        for subdir in sorted(results_dir.iterdir()):
            if not subdir.is_dir():
                continue
            results_file = subdir / "results.json"
            if not results_file.exists():
                continue
            try:
                with open(results_file) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to read %s", results_file)
                continue

            # Extract task_id from JSON (preferred) or dirname
            tid = data.get("task_id", "")
            if not tid:
                tid = _extract_task_id_from_dir(subdir.name)

            if tid not in task_id_set:
                continue

            task_score = _extract_task_score(data)
            if task_score is None:
                continue

            metadata = data.get("task_metadata", {})
            scores[tid].append(
                TaskResult(
                    task_id=tid,
                    suite=metadata.get("suite", ""),
                    difficulty=metadata.get("difficulty", ""),
                    task_score=task_score,
                    source_dir=str(results_dir),
                )
            )

    return scores


def _extract_task_score(data: dict) -> float | None:
    """Extract task_score from a results.json dict."""
    scores = data.get("scores", {})
    if isinstance(scores, dict):
        raw = scores.get("task_score")
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None
    return None


# ---------------------------------------------------------------------------
# Variance computation
# ---------------------------------------------------------------------------


def compute_variance(scores: list[float]) -> float:
    """Compute population variance for a list of scores.

    Returns 0.0 for fewer than 2 scores.
    """
    if len(scores) < 2:
        return 0.0
    mean = sum(scores) / len(scores)
    return sum((s - mean) ** 2 for s in scores) / len(scores)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _build_task_info_map(tasks: Sequence[TaskInfo]) -> dict[str, TaskInfo]:
    """Build a lookup from task_id to TaskInfo."""
    return {t.task_id: t for t in tasks}


def generate_report(
    scores_per_task: dict[str, list[TaskResult]],
    task_info_map: dict[str, TaskInfo],
    variance_threshold: float = 0.15,
    sample_size: int = 25,
) -> ReproducibilityReport:
    """Build a reproducibility report from collected scores."""
    per_task_records: list[TaskVarianceRecord] = []
    variances: list[float] = []
    tasks_with_multiple = 0
    tasks_flagged = 0

    for tid in sorted(scores_per_task.keys()):
        results = scores_per_task[tid]
        task_info = task_info_map.get(tid)
        suite = task_info.suite if task_info else ""
        difficulty = task_info.difficulty if task_info else ""

        # Override suite/difficulty from results if available
        if results:
            if results[0].suite:
                suite = results[0].suite
            if results[0].difficulty:
                difficulty = results[0].difficulty

        score_values = [r.task_score for r in results]
        num_runs = len(score_values)

        if num_runs >= 2:
            tasks_with_multiple += 1

        var = compute_variance(score_values)
        mean_score = sum(score_values) / len(score_values) if score_values else 0.0
        flagged = var >= variance_threshold

        if flagged:
            tasks_flagged += 1

        variances.append(var)
        per_task_records.append(
            TaskVarianceRecord(
                task_id=tid,
                suite=suite,
                difficulty=difficulty,
                num_runs=num_runs,
                scores=score_values,
                mean_score=round(mean_score, 4),
                variance=round(var, 6),
                flagged=flagged,
            )
        )

    mean_var = sum(variances) / len(variances) if variances else 0.0
    max_var = max(variances) if variances else 0.0
    tasks_sampled = len(scores_per_task)

    # Pass if fewer than 20% of sampled tasks are flagged
    pass_threshold = 0.20
    pass_result = (
        tasks_flagged / tasks_sampled < pass_threshold if tasks_sampled > 0 else True
    )

    return ReproducibilityReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        sample_size=sample_size,
        variance_threshold=variance_threshold,
        tasks_sampled=tasks_sampled,
        tasks_with_multiple_runs=tasks_with_multiple,
        tasks_flagged=tasks_flagged,
        mean_variance=round(mean_var, 6),
        max_variance=round(max_var, 6),
        pass_=pass_result,
        per_task=per_task_records,
    )


def write_report(report: ReproducibilityReport, output_path: Path) -> None:
    """Write the reproducibility report to a JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)
    logger.info("Report written to %s", output_path)


# ---------------------------------------------------------------------------
# Auto-detect results directories
# ---------------------------------------------------------------------------


def auto_detect_results_dirs(results_root: Path | None = None) -> list[Path]:
    """Auto-detect results directories under results/."""
    results_root = results_root or ROOT / "results"
    return discover_results_dirs(results_root)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Reproducibility validation for EnterpriseBench tasks.",
    )
    parser.add_argument(
        "--results-dir",
        action="append",
        type=Path,
        default=None,
        dest="results_dirs",
        help="Results directory to scan (repeatable). Auto-detects if not provided.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=25,
        help="Number of tasks to sample (default: 25).",
    )
    parser.add_argument(
        "--variance-threshold",
        type=float,
        default=0.15,
        help="Variance threshold for flagging tasks (default: 0.15).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "reproducibility_report.json",
        help="Output path for the report JSON.",
    )
    parser.add_argument(
        "--benchmarks-dir",
        type=Path,
        default=None,
        help="Benchmarks directory (default: benchmarks/).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the reproducibility check."""
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Discover tasks
    tasks = discover_tasks(args.benchmarks_dir)
    if not tasks:
        logger.error("No tasks found in benchmarks directory.")
        return 1
    logger.info("Discovered %d tasks", len(tasks))

    # Stratified sample
    sampled_ids = select_stratified_sample(tasks, n=args.sample_size)
    logger.info("Sampled %d tasks", len(sampled_ids))

    # Determine results directories
    results_dirs = args.results_dirs or auto_detect_results_dirs()
    if not results_dirs:
        logger.error("No results directories found.")
        return 1
    logger.info("Scanning %d results directories", len(results_dirs))

    # Collect scores
    scores_per_task = collect_scores(sampled_ids, results_dirs)
    task_info_map = _build_task_info_map(tasks)

    # Filter to tasks that have at least 1 run
    scores_with_data = {
        tid: results for tid, results in scores_per_task.items() if results
    }
    if not scores_with_data:
        logger.warning("No scores found for any sampled task.")

    # Generate report
    report = generate_report(
        scores_with_data,
        task_info_map,
        variance_threshold=args.variance_threshold,
        sample_size=args.sample_size,
    )

    # Write report
    write_report(report, args.output)

    # Summary
    status = "PASS" if report.pass_ else "FAIL"
    logger.info(
        "Reproducibility check: %s — %d/%d tasks flagged (threshold: %.0f%%)",
        status,
        report.tasks_flagged,
        report.tasks_sampled,
        args.variance_threshold * 100,
    )
    logger.info(
        "Mean variance: %.6f, Max variance: %.6f",
        report.mean_variance,
        report.max_variance,
    )

    return 0 if report.pass_ else 1


if __name__ == "__main__":
    sys.exit(main())
