#!/usr/bin/env python3
"""Unified task dispatcher CLI for EnterpriseBench.

Routes tasks to session-type-specific runners and collects results.

Usage:
    # Single task
    python3 scripts/run_benchmark.py benchmarks/customer_escalation/err-provenance-01/task.toml

    # All tasks in a suite
    python3 scripts/run_benchmark.py benchmarks/customer_escalation/

    # All tasks with filters
    python3 scripts/run_benchmark.py benchmarks/ --all --difficulty medium --limit 5

    # Parallel across 5 accounts (auto workers = one per account)
    python3 scripts/run_benchmark.py benchmarks/ --all --account 1-5 -j0

    # 3 parallel workers on accounts 1,3,5
    python3 scripts/run_benchmark.py benchmarks/ --all --account 1,3,5 -j3

    # Dry run (list matching tasks without executing)
    python3 scripts/run_benchmark.py benchmarks/ --all --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

# Support both tomllib (3.11+) and tomli
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redefine]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

logger = logging.getLogger("run_benchmark")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Session-type to runner script mapping
RUNNERS: dict[str, Path] = {
    "single": PROJECT_ROOT / "scripts" / "orchestration" / "run_task.py",
    "chain": PROJECT_ROOT / "scripts" / "orchestration" / "chain_runner.py",
    "event_replay": PROJECT_ROOT / "scripts" / "orchestration" / "event_replay.py",
}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskInfo:
    """Lightweight metadata parsed from a task.toml for filtering/routing."""

    task_id: str
    suite: str
    difficulty: str
    session_type: str
    task_type: str
    toml_path: Path


VALID_MODES = ("baseline", "mcp_only", "hybrid")


@dataclass
class TaskResult:
    task_id: str
    difficulty: str
    score: float | None = None
    duration_seconds: float = 0.0
    status: str = "pending"
    mode: str = "baseline"


# ---------------------------------------------------------------------------
# Discovery & Filtering
# ---------------------------------------------------------------------------

def discover_tasks(path: Path) -> list[TaskInfo]:
    """Find all task.toml files under *path* and parse their metadata."""
    if path.is_file() and path.name == "task.toml":
        toml_paths = [path]
    elif path.is_dir():
        toml_paths = sorted(path.rglob("task.toml"))
    else:
        logger.error("Path is neither a task.toml file nor a directory: %s", path)
        return []

    tasks: list[TaskInfo] = []
    for tp in toml_paths:
        info = _parse_task_meta(tp)
        if info is not None:
            tasks.append(info)
    return tasks


def _parse_task_meta(toml_path: Path) -> TaskInfo | None:
    if tomllib is None:
        logger.error("No TOML library available. Install tomli or use Python 3.11+.")
        sys.exit(1)

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", toml_path, exc)
        return None

    task = data.get("task", {})
    return TaskInfo(
        task_id=task.get("id", toml_path.parent.name),
        suite=task.get("suite", ""),
        difficulty=task.get("difficulty", ""),
        session_type=task.get("session_type", "single"),
        task_type=task.get("task_type", ""),
        toml_path=toml_path.resolve(),
    )


def filter_tasks(
    tasks: list[TaskInfo],
    *,
    difficulty: str | None = None,
    session_type: str | None = None,
    task_type: str | None = None,
    limit: int | None = None,
) -> list[TaskInfo]:
    """Return a new list filtered by the given criteria."""
    result = list(tasks)
    if difficulty:
        result = [t for t in result if t.difficulty == difficulty]
    if session_type:
        result = [t for t in result if t.session_type == session_type]
    if task_type:
        result = [t for t in result if t.task_type == task_type]
    if limit is not None and limit > 0:
        result = result[:limit]
    return result


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def run_task(
    task: TaskInfo,
    *,
    passthrough_args: Sequence[str],
    dry_run: bool = False,
    mode: str = "baseline",
) -> TaskResult:
    """Dispatch a single task to the appropriate runner."""
    result = TaskResult(task_id=task.task_id, difficulty=task.difficulty, mode=mode)

    if task.session_type == "resume":
        logger.info("[skip] %s — session_type 'resume' not yet implemented", task.task_id)
        result.status = "skipped"
        return result

    runner = RUNNERS.get(task.session_type)
    if runner is None:
        logger.error("[skip] %s — unknown session_type '%s'", task.task_id, task.session_type)
        result.status = "skipped"
        return result

    cmd = [sys.executable, str(runner), str(task.toml_path), *passthrough_args]

    if dry_run:
        logger.info("[dry-run] would run: %s", " ".join(cmd))
        result.status = "dry-run"
        return result

    logger.info("[run] %s (session_type=%s)", task.task_id, task.session_type)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        result.duration_seconds = time.monotonic() - t0

        if proc.returncode != 0:
            logger.warning(
                "[error] %s exited %d\nstdout: %s\nstderr: %s",
                task.task_id, proc.returncode,
                proc.stdout[-500:] if proc.stdout else "",
                proc.stderr[-500:] if proc.stderr else "",
            )
            result.status = "error"
            return result

        # Try to read results.json from the run output directory
        for results_file in [
            PROJECT_ROOT / "results" / "runs" / task.task_id / mode / "results.json",
            PROJECT_ROOT / "results" / "runs" / task.task_id / "results.json",
            task.toml_path.parent / "results.json",
        ]:
            if results_file.exists():
                try:
                    rdata = json.loads(results_file.read_text())
                    result.score = rdata.get("scores", {}).get("task_score",
                                  rdata.get("score"))
                    break
                except (json.JSONDecodeError, OSError):
                    pass

        result.status = "completed"

    except subprocess.TimeoutExpired:
        result.duration_seconds = time.monotonic() - t0
        result.status = "timeout"
        logger.warning("[timeout] %s", task.task_id)
    except Exception as exc:
        result.duration_seconds = time.monotonic() - t0
        result.status = "error"
        logger.error("[error] %s — %s", task.task_id, exc)

    return result


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def write_summary(results: list[TaskResult], run_id: str) -> Path:
    """Write results/runs/<run_id>/summary.json and return the path."""
    out_dir = PROJECT_ROOT / "results" / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.json"

    payload = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "completed": sum(1 for r in results if r.status == "completed"),
        "errors": sum(1 for r in results if r.status == "error"),
        "skipped": sum(1 for r in results if r.status == "skipped"),
        "tasks": [asdict(r) for r in results],
    }
    summary_path.write_text(json.dumps(payload, indent=2) + "\n")
    return summary_path


def print_summary_table(results: list[TaskResult]) -> None:
    """Print a human-readable summary table to stdout."""
    header = f"{'task_id':<45} {'mode':<12} {'difficulty':<10} {'score':>6} {'duration':>10} {'status':<10}"
    print("\n" + header)
    print("-" * len(header))
    for r in results:
        score_str = f"{r.score:.2f}" if r.score is not None else "—"
        dur_str = f"{r.duration_seconds:.1f}s" if r.duration_seconds > 0 else "—"
        print(f"{r.task_id:<45} {r.mode:<12} {r.difficulty:<10} {score_str:>6} {dur_str:>10} {r.status:<10}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EnterpriseBench unified task dispatcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to a task.toml file or a directory containing tasks",
    )

    # Filter flags
    filter_group = parser.add_argument_group("filters")
    filter_group.add_argument("--all", action="store_true", help="Run all tasks under path")
    filter_group.add_argument("--difficulty", choices=["medium", "hard", "expert"])
    filter_group.add_argument("--session-type", choices=["single", "chain", "event_replay", "resume"])
    filter_group.add_argument("--task-type")
    filter_group.add_argument("--limit", type=int, default=None, help="Max number of tasks to run")

    # Passthrough flags for runners
    runner_group = parser.add_argument_group("runner options (passed through)")
    runner_group.add_argument("--source", choices=["mirror", "upstream"])
    runner_group.add_argument("--agent", type=str)
    runner_group.add_argument("--timeout", type=int)
    runner_group.add_argument(
        "--account",
        type=str,
        default=None,
        help=(
            "OAuth account(s): single number (1), range (1-5), or "
            "comma-separated (1,3,5). Tasks are distributed round-robin "
            "across accounts when multiple are given."
        ),
    )
    runner_group.add_argument("--dry-run", action="store_true", help="List tasks without running")
    runner_group.add_argument(
        "--mode",
        choices=list(VALID_MODES),
        default="baseline",
        help="Tool-access mode (default: baseline)",
    )
    runner_group.add_argument(
        "--modes",
        type=str,
        default=None,
        help=(
            "Comma-separated list of modes to run each task in "
            "(e.g. 'baseline,mcp_only,hybrid'). Overrides --mode."
        ),
    )

    # Parallelism
    parallel_group = parser.add_argument_group("parallelism")
    parallel_group.add_argument(
        "--parallel", "-j",
        type=int,
        default=1,
        metavar="N",
        help="Max parallel tasks (default: 1). Set to 0 for auto (one per account).",
    )

    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def parse_accounts(account_str: str | None) -> list[int]:
    """Parse account spec into a list of account numbers.

    Supports: "1", "1-5", "1,3,5", "1-3,5".
    Returns an empty list if account_str is None.
    """
    if not account_str:
        return []
    accounts: list[int] = []
    for part in account_str.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            accounts.extend(range(int(lo), int(hi) + 1))
        else:
            accounts.append(int(part))
    return accounts


def collect_passthrough_args(
    args: argparse.Namespace,
    *,
    account_override: int | None = None,
    mode_override: str | None = None,
) -> list[str]:
    """Build list of flags to pass through to underlying runner scripts.

    If *account_override* is given it replaces whatever --account was on the CLI
    (used by the parallel dispatcher to rotate accounts per task).
    If *mode_override* is given it replaces the --mode flag.
    """
    result: list[str] = []
    if args.source:
        result.extend(["--source", args.source])
    if args.agent:
        result.extend(["--agent", args.agent])
    if args.timeout:
        result.extend(["--timeout", str(args.timeout)])
    if account_override is not None:
        result.extend(["--account", str(account_override)])
    elif args.account is not None:
        # Single-account legacy path
        accounts = parse_accounts(args.account)
        if len(accounts) == 1:
            result.extend(["--account", str(accounts[0])])
    # Mode passthrough
    mode = mode_override if mode_override is not None else args.mode
    result.extend(["--mode", mode])
    if args.dry_run:
        result.append("--dry-run")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    path = args.path.resolve()

    # Require --all when pointing at a directory (safety guard)
    if path.is_dir() and not path.name.endswith("task.toml") and not args.all:
        # If pointing at a single task dir (contains task.toml), allow it
        if (path / "task.toml").exists():
            path = path / "task.toml"
        else:
            parser.error("Pass --all to run all tasks in a directory")

    tasks = discover_tasks(path)
    if not tasks:
        logger.error("No tasks found at %s", path)
        return 1

    tasks = filter_tasks(
        tasks,
        difficulty=args.difficulty,
        session_type=args.session_type,
        task_type=args.task_type,
        limit=args.limit,
    )

    logger.info("Matched %d task(s)", len(tasks))

    if args.limit == 0:
        # --limit 0 means list only, run nothing
        for t in discover_tasks(path):
            filtered = filter_tasks(
                [t],
                difficulty=args.difficulty,
                session_type=args.session_type,
                task_type=args.task_type,
            )
            if filtered:
                print(f"  {t.task_id:<45} {t.difficulty:<10} {t.session_type:<15} {t.task_type}")
        return 0

    if not tasks:
        logger.info("No tasks match the given filters.")
        return 0

    # Resolve modes list
    if args.modes:
        modes = [m.strip() for m in args.modes.split(",")]
        for m in modes:
            if m not in VALID_MODES:
                parser.error(
                    f"Invalid mode '{m}' in --modes. "
                    f"Valid modes: {', '.join(VALID_MODES)}"
                )
    else:
        modes = [args.mode]

    logger.info("Tool-access mode(s): %s", ", ".join(modes))

    # Execute
    accounts = parse_accounts(args.account)
    workers = args.parallel
    if workers == 0:
        # Auto: one worker per account, minimum 1
        workers = max(len(accounts), 1)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results: list[TaskResult] = []

    for current_mode in modes:
        if len(modes) > 1:
            logger.info("--- Running mode: %s ---", current_mode)

        # When using multi-mode, set output-dir to include mode subdirectory
        mode_passthrough_extra: list[str] = []
        if len(modes) > 1:
            # Tell runners to use mode-specific output directories
            for task in tasks:
                pass  # output-dir override handled per-task below

        if workers <= 1 or args.dry_run:
            # Sequential execution
            for task in tasks:
                account_id = accounts[0] if len(accounts) == 1 else None
                passthrough = collect_passthrough_args(
                    args,
                    account_override=account_id,
                    mode_override=current_mode,
                )
                # For multi-mode runs, use mode-specific output directory
                if len(modes) > 1:
                    mode_output = (
                        PROJECT_ROOT / "results" / "runs"
                        / task.task_id / current_mode
                    )
                    passthrough.extend(["--output-dir", str(mode_output)])
                result = run_task(
                    task,
                    passthrough_args=passthrough,
                    dry_run=args.dry_run,
                    mode=current_mode,
                )
                results.append(result)
        else:
            # Parallel execution with round-robin account distribution
            logger.info(
                "Parallel mode: %d workers, %d account(s)",
                workers, len(accounts) or 1,
            )

            def _run_with_account(
                task: TaskInfo,
                account_id: int | None,
                mode: str = current_mode,
            ) -> TaskResult:
                pt = collect_passthrough_args(
                    args,
                    account_override=account_id,
                    mode_override=mode,
                )
                if len(modes) > 1:
                    mode_output = (
                        PROJECT_ROOT / "results" / "runs"
                        / task.task_id / mode
                    )
                    pt.extend(["--output-dir", str(mode_output)])
                return run_task(task, passthrough_args=pt, mode=mode)

            # Build (task, account) pairs via round-robin
            task_assignments: list[tuple[TaskInfo, int | None]] = []
            for i, task in enumerate(tasks):
                acct = accounts[i % len(accounts)] if accounts else None
                task_assignments.append((task, acct))

            # Submit all tasks to the pool
            # Use (task_id, mode) as key to handle multi-mode runs
            result_map: dict[str, TaskResult] = {}
            with ProcessPoolExecutor(max_workers=workers) as pool:
                future_to_task = {
                    pool.submit(_run_with_account, task, acct): task
                    for task, acct in task_assignments
                }
                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        r = future.result()
                    except Exception as exc:
                        r = TaskResult(
                            task_id=task.task_id,
                            difficulty=task.difficulty,
                            status="error",
                            mode=current_mode,
                        )
                        logger.error("[error] %s — %s", task.task_id, exc)
                    result_map[task.task_id] = r
                    logger.info(
                        "[done] %s [%s]  score=%s  %s  (%.0fs)",
                        r.task_id,
                        r.mode,
                        f"{r.score:.2f}" if r.score is not None else "—",
                        r.status,
                        r.duration_seconds,
                    )

            # Preserve original task order in results
            results.extend(result_map[t.task_id] for t in tasks)

    # Summary
    print_summary_table(results)
    if not args.dry_run:
        summary_path = write_summary(results, run_id)
        logger.info("Summary written to %s", summary_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
