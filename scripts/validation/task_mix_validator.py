#!/usr/bin/env python3
"""Task mix validator for EnterpriseBench PRD targets.

Scans all active benchmarks/*/task.toml files and validates:
- Strict multi-repo >= 45% of total tasks
- All 10 task types have >= 2 multi-repo variants
- No single ecosystem > 40% of multi-repo tasks

Usage:
    python3 scripts/validation/task_mix_validator.py
    python3 scripts/validation/task_mix_validator.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


# Multi-repo strata (dual_repo, tri_repo, multi_repo count as strict multi-repo)
STRICT_MULTI_REPO_STRATA = frozenset({"dual_repo", "tri_repo", "multi_repo"})

# All strata that are NOT calibration or large_single (includes monorepo_cross_package)
ALL_MULTI_REPO_STRATA = STRICT_MULTI_REPO_STRATA | {"monorepo_cross_package"}

# The 10 expected task types
EXPECTED_TASK_TYPES = frozenset(
    {
        "api_contract",
        "config_drift",
        "db_schema_evolution",
        "dead_code_necropsy",
        "dependency_graph",
        "error_provenance",
        "incident_investigation",
        "monorepo_boundary",
        "refactor_orchestration",
        "support_code_mapping",
    }
)

# Targets
MIN_STRICT_MULTI_REPO_PCT = 0.45
MIN_MULTI_REPO_PER_TYPE = 2
MAX_SINGLE_ECOSYSTEM_PCT = 0.40

# Project root (assumes script is at scripts/validation/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def parse_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML file."""
    if tomllib is None:
        raise RuntimeError("No TOML parser available. Install tomli: pip install tomli")
    with open(path, "rb") as f:
        return tomllib.load(f)


@dataclass(frozen=True)
class TaskInfo:
    """Immutable summary of a single task."""

    task_id: str
    suite: str
    task_type: str
    difficulty_stratum: str
    multi_repo_pattern: str
    num_repos: int
    languages: tuple[str, ...]
    frameworks: tuple[str, ...]
    repos: tuple[tuple[str, str], ...]  # (url, rev) pairs


def extract_task_info(config: dict[str, Any]) -> TaskInfo:
    """Extract relevant fields from a parsed task.toml."""
    task_section = config.get("task", {})
    metadata = config.get("metadata", {})
    repos_list = config.get("repos", [])

    return TaskInfo(
        task_id=task_section.get("id", "unknown"),
        suite=task_section.get("suite", ""),
        task_type=task_section.get("task_type", ""),
        difficulty_stratum=config.get("difficulty_stratum", ""),
        multi_repo_pattern=metadata.get("multi_repo_pattern", ""),
        num_repos=len(repos_list),
        languages=tuple(metadata.get("languages", [])),
        frameworks=tuple(metadata.get("frameworks", [])),
        repos=tuple(
            (r.get("url", ""), r.get("rev", ""))
            for r in repos_list
            if r.get("url") and r.get("rev")
        ),
    )


def collect_active_tasks(benchmarks_dir: Path) -> list[TaskInfo]:
    """Scan all active task.toml files (excluding _archived/)."""
    tasks: list[TaskInfo] = []
    for task_file in sorted(benchmarks_dir.rglob("task.toml")):
        if "_archived" in str(task_file):
            continue
        config = parse_toml(task_file)
        tasks.append(extract_task_info(config))
    return tasks


def compute_ecosystem(task: TaskInfo) -> list[str]:
    """Derive ecosystem labels from a task's languages and frameworks."""
    ecosystems: list[str] = []
    ecosystems.extend(task.languages)
    ecosystems.extend(task.frameworks)
    return ecosystems


@dataclass(frozen=True)
class ValidationResult:
    """Immutable result of task mix validation."""

    total_tasks: int
    stratum_counts: dict[str, int]
    type_counts: dict[str, int]
    type_multi_repo_counts: dict[str, int]
    ecosystem_counts: dict[str, int]
    investigate_count: int
    total_multi_repo_tasks: int
    strict_multi_repo_count: int
    strict_multi_repo_pct: float
    all_types_have_min_multi_repo: bool
    types_below_min: list[str]
    max_ecosystem_name: str
    max_ecosystem_pct: float
    no_ecosystem_over_limit: bool
    all_pass: bool
    failures: list[str]


def validate_task_mix(tasks: list[TaskInfo]) -> ValidationResult:
    """Validate the task mix against PRD targets."""
    total = len(tasks)

    # Per-stratum counts
    stratum_counter: Counter[str] = Counter()
    for t in tasks:
        stratum_counter[t.difficulty_stratum] += 1

    # Per-type counts
    type_counter: Counter[str] = Counter()
    for t in tasks:
        type_counter[t.task_type] += 1

    # Per-type multi-repo counts (tasks with stratum in ALL_MULTI_REPO_STRATA)
    type_multi_repo: Counter[str] = Counter()
    for t in tasks:
        if t.difficulty_stratum in ALL_MULTI_REPO_STRATA:
            type_multi_repo[t.task_type] += 1

    # Strict multi-repo count
    strict_multi_repo = sum(
        1 for t in tasks if t.difficulty_stratum in STRICT_MULTI_REPO_STRATA
    )
    strict_multi_repo_pct = strict_multi_repo / total if total > 0 else 0.0

    # Total multi-repo (including monorepo_cross_package)
    total_multi_repo = sum(
        1 for t in tasks if t.difficulty_stratum in ALL_MULTI_REPO_STRATA
    )

    # Ecosystem distribution (over multi-repo tasks only)
    ecosystem_counter: Counter[str] = Counter()
    for t in tasks:
        if t.difficulty_stratum in ALL_MULTI_REPO_STRATA:
            for eco in compute_ecosystem(t):
                ecosystem_counter[eco] += 1

    # Find max ecosystem
    max_eco_name = ""
    max_eco_pct = 0.0
    if ecosystem_counter and total_multi_repo > 0:
        max_eco_name, max_eco_count = ecosystem_counter.most_common(1)[0]
        max_eco_pct = max_eco_count / total_multi_repo

    # Investigate pattern count (among multi-repo tasks)
    investigate_count = sum(
        1
        for t in tasks
        if t.difficulty_stratum in ALL_MULTI_REPO_STRATA
        and t.multi_repo_pattern == "investigate"
    )

    # Check targets
    failures: list[str] = []

    # Target 1: strict multi-repo >= 45%
    if strict_multi_repo_pct < MIN_STRICT_MULTI_REPO_PCT:
        failures.append(
            f"Strict multi-repo is {strict_multi_repo_pct:.1%} "
            f"({strict_multi_repo}/{total}), need >= {MIN_STRICT_MULTI_REPO_PCT:.0%}"
        )

    # Target 2: all 10 types have >= 2 multi-repo variants
    types_below: list[str] = []
    for tt in sorted(EXPECTED_TASK_TYPES):
        count = type_multi_repo.get(tt, 0)
        if count < MIN_MULTI_REPO_PER_TYPE:
            types_below.append(tt)
            failures.append(
                f"Task type '{tt}' has {count} multi-repo variant(s), need >= {MIN_MULTI_REPO_PER_TYPE}"
            )

    # Target 3: no single ecosystem > 40% of multi-repo tasks
    no_eco_over = max_eco_pct <= MAX_SINGLE_ECOSYSTEM_PCT
    if not no_eco_over:
        failures.append(
            f"Ecosystem '{max_eco_name}' is {max_eco_pct:.1%} of multi-repo tasks, "
            f"limit is {MAX_SINGLE_ECOSYSTEM_PCT:.0%}"
        )

    return ValidationResult(
        total_tasks=total,
        stratum_counts=dict(stratum_counter),
        type_counts=dict(type_counter),
        type_multi_repo_counts=dict(type_multi_repo),
        ecosystem_counts=dict(ecosystem_counter),
        investigate_count=investigate_count,
        total_multi_repo_tasks=total_multi_repo,
        strict_multi_repo_count=strict_multi_repo,
        strict_multi_repo_pct=strict_multi_repo_pct,
        all_types_have_min_multi_repo=len(types_below) == 0,
        types_below_min=types_below,
        max_ecosystem_name=max_eco_name,
        max_ecosystem_pct=max_eco_pct,
        no_ecosystem_over_limit=no_eco_over,
        all_pass=len(failures) == 0,
        failures=failures,
    )


def format_report(result: ValidationResult) -> str:
    """Format a human-readable validation report."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("EnterpriseBench Task Mix Validation Report")
    lines.append("=" * 70)
    lines.append("")

    # Total count
    lines.append(f"Total active tasks: {result.total_tasks}")
    lines.append("")

    # Per-stratum
    lines.append("--- Difficulty Stratum Distribution ---")
    for stratum in sorted(result.stratum_counts.keys()):
        count = result.stratum_counts[stratum]
        pct = count / result.total_tasks * 100 if result.total_tasks > 0 else 0
        lines.append(f"  {stratum:25s} {count:3d}  ({pct:5.1f}%)")
    lines.append("")

    # Per-type with multi-repo breakdown
    lines.append("--- Task Type Distribution ---")
    lines.append(f"  {'Type':30s} {'Total':>5s}  {'Multi-repo':>10s}  {'MR %':>6s}")
    lines.append(f"  {'-'*30} {'-'*5}  {'-'*10}  {'-'*6}")
    for tt in sorted(EXPECTED_TASK_TYPES):
        total = result.type_counts.get(tt, 0)
        mr = result.type_multi_repo_counts.get(tt, 0)
        mr_pct = mr / total * 100 if total > 0 else 0
        marker = " *" if tt in result.types_below_min else ""
        lines.append(f"  {tt:30s} {total:5d}  {mr:10d}  {mr_pct:5.1f}%{marker}")
    lines.append("")

    # Ecosystem distribution
    lines.append("--- Ecosystem Distribution (multi-repo tasks) ---")
    for eco, count in sorted(result.ecosystem_counts.items(), key=lambda x: -x[1]):
        pct = (
            count / result.total_multi_repo_tasks * 100
            if result.total_multi_repo_tasks > 0
            else 0
        )
        marker = " !" if pct > MAX_SINGLE_ECOSYSTEM_PCT * 100 else ""
        lines.append(f"  {eco:25s} {count:3d}  ({pct:5.1f}%){marker}")
    lines.append("")

    # Investigate pattern
    inv_pct = (
        result.investigate_count / result.total_multi_repo_tasks * 100
        if result.total_multi_repo_tasks > 0
        else 0
    )
    lines.append(
        f"Investigate pattern: {result.investigate_count}/{result.total_multi_repo_tasks} "
        f"multi-repo tasks ({inv_pct:.1f}%)"
    )
    lines.append("")

    # Summary
    lines.append("--- Validation Targets ---")
    strict_status = (
        "PASS" if result.strict_multi_repo_pct >= MIN_STRICT_MULTI_REPO_PCT else "FAIL"
    )
    lines.append(
        f"  [{strict_status}] Strict multi-repo >= 45%: "
        f"{result.strict_multi_repo_pct:.1%} ({result.strict_multi_repo_count}/{result.total_tasks})"
    )

    types_status = "PASS" if result.all_types_have_min_multi_repo else "FAIL"
    lines.append(f"  [{types_status}] All 10 types >= 2 multi-repo variants")
    if result.types_below_min:
        for tt in result.types_below_min:
            lines.append(
                f"         Missing: {tt} ({result.type_multi_repo_counts.get(tt, 0)} variants)"
            )

    eco_status = "PASS" if result.no_ecosystem_over_limit else "FAIL"
    lines.append(
        f"  [{eco_status}] No ecosystem > 40%: "
        f"max is '{result.max_ecosystem_name}' at {result.max_ecosystem_pct:.1%}"
    )
    lines.append("")

    if result.all_pass:
        lines.append("RESULT: ALL TARGETS MET")
    else:
        lines.append("RESULT: TARGETS NOT MET")
        for failure in result.failures:
            lines.append(f"  - {failure}")

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate EnterpriseBench task mix against PRD targets",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--benchmarks-dir",
        type=Path,
        default=PROJECT_ROOT / "benchmarks",
        help="Path to benchmarks directory",
    )
    args = parser.parse_args(argv)

    if not args.benchmarks_dir.exists():
        print(f"Error: {args.benchmarks_dir} not found", file=sys.stderr)
        return 1

    tasks = collect_active_tasks(args.benchmarks_dir)
    if not tasks:
        print("Error: no active tasks found", file=sys.stderr)
        return 1

    result = validate_task_mix(tasks)

    if args.json:
        output = {
            "total_tasks": result.total_tasks,
            "stratum_counts": result.stratum_counts,
            "type_counts": result.type_counts,
            "type_multi_repo_counts": result.type_multi_repo_counts,
            "ecosystem_counts": result.ecosystem_counts,
            "investigate_count": result.investigate_count,
            "total_multi_repo_tasks": result.total_multi_repo_tasks,
            "strict_multi_repo_count": result.strict_multi_repo_count,
            "strict_multi_repo_pct": round(result.strict_multi_repo_pct, 4),
            "all_types_have_min_multi_repo": result.all_types_have_min_multi_repo,
            "types_below_min": result.types_below_min,
            "max_ecosystem_name": result.max_ecosystem_name,
            "max_ecosystem_pct": round(result.max_ecosystem_pct, 4),
            "no_ecosystem_over_limit": result.no_ecosystem_over_limit,
            "all_pass": result.all_pass,
            "failures": result.failures,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_report(result))

    return 0 if result.all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
