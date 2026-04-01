#!/usr/bin/env python3
"""Centralized failure classifier for EnterpriseBench task runs.

Scans results/runs/ for task result directories, classifies each into
triage categories using error fingerprints and checkpoint analysis.

Categories:
    pass      - Score > 0 (task produced useful signal)
    A_infra   - Infrastructure failure (Docker, OOM, network, API errors)
    B_setup   - Setup failure (image build, missing deps, clone failures)
    C_verifier- Verifier failure (checkpoint script bug, parse error)
    D_agent   - Agent quality failure (completed but score=0, or agent fingerprint)
    E_timeout - Task or agent timeout

Usage:
    python3 scripts/triage/triage_run.py
    python3 scripts/triage/triage_run.py --results-dir results/runs --format table
    python3 scripts/triage/triage_run.py --output triage.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR.parent))
sys.path.insert(0, str(_THIS_DIR))

from triage.status_fingerprints import match_fingerprint, Fingerprint

# ---------------------------------------------------------------------------
# Triage categories
# ---------------------------------------------------------------------------


class TriageCategory(str, Enum):
    """Triage classification categories."""

    PASS = "pass"
    A_INFRA = "A_infra"
    B_SETUP = "B_setup"
    C_VERIFIER = "C_verifier"
    D_AGENT = "D_agent"
    E_TIMEOUT = "E_timeout"


# Map fingerprint severity to triage category
_SEVERITY_TO_CATEGORY: dict[str, TriageCategory] = {
    "infra": TriageCategory.A_INFRA,
    "setup": TriageCategory.B_SETUP,
    "verifier": TriageCategory.C_VERIFIER,
    "agent": TriageCategory.D_AGENT,
    "timeout": TriageCategory.E_TIMEOUT,
}

# Directories to skip when scanning results/runs/
_SKIP_DIRS = frozenset({"_batch_summaries", "__pycache__"})

# Maximum bytes of log to read for fingerprinting (avoid reading huge logs)
_MAX_LOG_BYTES = 50_000


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------


def _read_log_tail(task_dir: Path, filename: str) -> str:
    """Read the last chunk of a log file for fingerprinting."""
    log_path = task_dir / filename
    if not log_path.is_file():
        return ""
    try:
        size = log_path.stat().st_size
        if size <= _MAX_LOG_BYTES:
            return log_path.read_text(errors="replace")
        with open(log_path, "r", errors="replace") as f:
            f.seek(max(0, size - _MAX_LOG_BYTES))
            return f.read()
    except OSError:
        return ""


def _agent_produced_output(task_dir: Path) -> bool:
    """Check if the agent produced meaningful output (result + cost > 0).

    Parses agent_stdout.log looking for a JSON object with a non-empty
    ``"result"`` field and ``"total_cost_usd"`` > 0.  Returns True when
    both conditions are met.
    """
    log_text = _read_log_tail(task_dir, "agent_stdout.log")
    if not log_text.strip():
        return False
    try:
        log_data = json.loads(log_text)
    except (json.JSONDecodeError, ValueError):
        return False
    result_field = log_data.get("result", "")
    cost = log_data.get("total_cost_usd", 0)
    return bool(result_field) and isinstance(cost, (int, float)) and cost > 0


def _gather_error_text(data: dict[str, Any], task_dir: Path) -> str:
    """Collect all error text sources into a single string for fingerprinting."""
    parts: list[str] = []

    error_field = data.get("error", "")
    if isinstance(error_field, dict):
        parts.append(json.dumps(error_field))
    elif error_field:
        parts.append(str(error_field))

    # Read log files
    for log_name in ("agent_stdout.log", "agent_stderr.log"):
        log_text = _read_log_tail(task_dir, log_name)
        if log_text:
            parts.append(log_text)

    return "\n".join(parts)


def _extract_checkpoints(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract checkpoint details from results data."""
    scores = data.get("scores", {})
    raw_checkpoints = scores.get("checkpoints", [])
    return [
        {
            "name": cp.get("name", "unknown"),
            "score": cp.get("score", 0.0),
            "passed": cp.get("passed", False),
            "weight": cp.get("weight", 1.0),
        }
        for cp in raw_checkpoints
    ]


def classify_task(task_dir: Path) -> Optional[dict[str, Any]]:
    """Classify a single task directory into a triage category.

    Args:
        task_dir: Path to task result directory containing results.json.

    Returns:
        Classification dict, or None if results.json is missing/corrupt.
    """
    results_path = task_dir / "results.json"
    if not results_path.is_file():
        return None

    try:
        data = json.loads(results_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    task_id = data.get("task_id", task_dir.name)
    scores = data.get("scores", {})
    task_score = scores.get("task_score", 0.0)
    checkpoints = _extract_checkpoints(data)
    phase = data.get("phase", "")
    success = data.get("success", False)

    # Gather all error text for fingerprinting
    error_text = _gather_error_text(data, task_dir)

    # Try fingerprint matching
    fp: Optional[Fingerprint] = (
        match_fingerprint(error_text) if error_text.strip() else None
    )
    fingerprint_id = fp.id if fp else None
    fingerprint_severity = fp.severity if fp else None

    # Check whether the agent actually produced meaningful output
    has_agent_output = _agent_produced_output(task_dir)

    # Classification logic:
    # 1. If score > 0 => pass
    if task_score is not None and task_score > 0:
        category = TriageCategory.PASS
    # 2. If agent produced output (result + cost > 0) but score = 0 => agent quality
    #    The agent ran and answered; the answer was simply wrong.
    elif has_agent_output:
        category = TriageCategory.D_AGENT
    # 3. If fingerprint matched => use severity mapping
    elif fp is not None:
        category = _SEVERITY_TO_CATEGORY.get(
            fingerprint_severity, TriageCategory.D_AGENT  # type: ignore[arg-type]
        )
    # 4. Phase-based heuristics for unfingerprinted failures
    elif phase in ("build",) and not success:
        category = TriageCategory.B_SETUP
    elif phase in ("scoring",) and not success:
        category = TriageCategory.C_VERIFIER
    # 5. Completed with score=0 and no fingerprint => agent quality
    else:
        category = TriageCategory.D_AGENT

    return {
        "task_id": task_id,
        "category": category,
        "score": task_score,
        "phase": phase,
        "success": success,
        "fingerprint_id": fingerprint_id,
        "fingerprint_severity": fingerprint_severity,
        "fingerprint_label": fp.label if fp else None,
        "fingerprint_advice": fp.advice if fp else None,
        "checkpoints": checkpoints,
        "checkpoints_passed": scores.get("checkpoints_passed", 0),
        "checkpoints_total": scores.get("checkpoints_total", 0),
        "metadata": data.get("task_metadata", {}),
    }


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------


def scan_results_dir(results_dir: Path) -> list[dict[str, Any]]:
    """Scan a results directory and classify all tasks.

    Skips _batch_summaries and other non-task directories.

    Returns:
        List of classification dicts (one per task with valid results.json).
    """
    classified: list[dict[str, Any]] = []

    if not results_dir.is_dir():
        return classified

    for entry in sorted(results_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in _SKIP_DIRS:
            continue
        # Skip timestamp-named batch dirs (all digits + underscores)
        if entry.name.replace("_", "").isdigit():
            continue

        result = classify_task(entry)
        if result is not None:
            classified.append(result)

    return classified


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------


def build_report(tasks: list[dict[str, Any]], results_dir: str) -> dict[str, Any]:
    """Build a structured triage report from classified tasks.

    Returns:
        Report dict with summary counts and per-task details.
    """
    summary: dict[str, int] = {
        "total": len(tasks),
        "pass": 0,
        "A_infra": 0,
        "B_setup": 0,
        "C_verifier": 0,
        "D_agent": 0,
        "E_timeout": 0,
    }

    for task in tasks:
        cat = task["category"]
        if isinstance(cat, TriageCategory):
            key = cat.value
        else:
            key = str(cat)
        if key in summary:
            summary[key] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results_dir": results_dir,
        "summary": summary,
        "per_task": [
            {
                **task,
                "category": (
                    task["category"].value
                    if isinstance(task["category"], TriageCategory)
                    else task["category"]
                ),
            }
            for task in tasks
        ],
    }


# ---------------------------------------------------------------------------
# Table formatting
# ---------------------------------------------------------------------------


def _format_table(report: dict[str, Any]) -> str:
    """Format report as a human-readable table."""
    lines: list[str] = []

    # Summary
    summary = report["summary"]
    lines.append("=== Triage Summary ===")
    lines.append(f"Total tasks: {summary['total']}")
    for key in ("pass", "A_infra", "B_setup", "C_verifier", "D_agent", "E_timeout"):
        count = summary.get(key, 0)
        if count > 0:
            lines.append(f"  {key:12s}: {count}")
    lines.append("")

    # Per-task table
    header = f"{'Task ID':<45s} {'Category':<12s} {'Score':>6s} {'Phase':<10s} {'Fingerprint'}"
    lines.append(header)
    lines.append("-" * len(header))

    for task in report["per_task"]:
        cat = task["category"]
        score = task.get("score")
        score_str = f"{score:.2f}" if score is not None else "N/A"
        fp_id = task.get("fingerprint_id", "") or ""
        phase = task.get("phase", "") or ""
        lines.append(
            f"{task['task_id']:<45s} {cat:<12s} {score_str:>6s} {phase:<10s} {fp_id}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def filter_tasks(
    tasks: list[dict[str, Any]],
    *,
    suite: str | None = None,
    task_type: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Filter classified tasks by suite, task_type, or category.

    Args:
        tasks: List of classification dicts from classify_task.
        suite: Filter to tasks in this suite (substring match).
        task_type: Filter to tasks of this type (substring match).
        category: Filter to this triage category (exact match on value).

    Returns:
        Filtered list of task dicts.
    """
    filtered = list(tasks)

    if suite:
        suite_lower = suite.lower()
        filtered = [
            t
            for t in filtered
            if suite_lower in (t.get("metadata", {}).get("suite", "") or "").lower()
        ]

    if task_type:
        type_lower = task_type.lower()
        filtered = [
            t
            for t in filtered
            if type_lower in (t.get("metadata", {}).get("task_type", "") or "").lower()
        ]

    if category:
        cat_lower = category.lower()
        filtered = [
            t
            for t in filtered
            if (
                t["category"].value
                if isinstance(t["category"], TriageCategory)
                else t["category"]
            ).lower()
            == cat_lower
        ]

    return filtered


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Triage EnterpriseBench task results into failure categories.",
    )
    parser.add_argument(
        "--results-dir",
        default="results/runs",
        help="Path to results directory (default: results/runs)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write JSON report to file (default: stdout)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--suite",
        default=None,
        help="Filter to tasks in this suite (substring match)",
    )
    parser.add_argument(
        "--task-type",
        default=None,
        help="Filter to tasks of this type (substring match)",
    )
    parser.add_argument(
        "--category",
        default=None,
        choices=["pass", "A_infra", "B_setup", "C_verifier", "D_agent", "E_timeout"],
        help="Filter to this triage category",
    )
    return parser.parse_args(argv)


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    results_dir = Path(args.results_dir)

    if not results_dir.is_dir():
        print(f"Error: results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    tasks = scan_results_dir(results_dir)
    tasks = filter_tasks(
        tasks, suite=args.suite, task_type=args.task_type, category=args.category
    )
    report = build_report(tasks, str(results_dir))

    if args.format == "table":
        output = _format_table(report)
    else:
        output = json.dumps(report, indent=2)

    if args.output:
        Path(args.output).write_text(output + "\n")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
