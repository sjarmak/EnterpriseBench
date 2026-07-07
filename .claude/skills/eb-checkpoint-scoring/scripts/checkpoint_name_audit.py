#!/usr/bin/env python3
"""Read-only diagnostic: checkpoint-name divergence between the two scorers.

For every active task under benchmarks/ (skipping _archived/ and mined/),
compares three name sets:

  1. task.toml [[checkpoints]].name        -> used by the LIBRARY scorer
     (lib/eb_verify/runner.py) and required as expected_solution.json keys
     by scripts/validation/validate_expected_solutions.py gate C1.
  2. checks/*.sh filenames, "check_" prefix stripped -> used by the
     PRODUCTION scorer (run_task.py copies checks/check_<x>.sh to
     /workspace/.verifiers/<x>.sh; test_runner.sh names checkpoints by
     filename).
  3. expected_solution.json "checkpoints" keys (when the file exists).

Production Tier-2 (_apply_llm_judge) matches set 3 keys against set 2
names. Any set-2 name absent from set 3 means the LLM-judge ceiling is
silently skipped for that checkpoint in production runs.

Usage (from the repo root):
    python3 .claude/skills/eb-checkpoint-scoring/scripts/checkpoint_name_audit.py
    python3 .claude/skills/eb-checkpoint-scoring/scripts/checkpoint_name_audit.py --verbose

Exit code: always 0 (diagnostic only; makes no judgment and writes nothing).
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    """Walk up from `start` until a directory containing benchmarks/ is found."""
    for candidate in [start, *start.parents]:
        if (candidate / "benchmarks").is_dir() and (candidate / "schemas").is_dir():
            return candidate
    sys.exit("error: could not locate repo root (no benchmarks/ + schemas/ found)")


def filename_derived_names(task_dir: Path) -> set[str]:
    """Checkpoint names as production sees them: checks/*.sh, check_ stripped."""
    checks = task_dir / "checks"
    if not checks.is_dir():
        return set()
    names = set()
    for script in checks.glob("*.sh"):
        name = script.stem
        if name.startswith("check_"):
            name = name[len("check_") :]
        names.add(name)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verbose", action="store_true", help="print per-task mismatch detail"
    )
    args = parser.parse_args()

    root = find_repo_root(Path.cwd().resolve())
    skip_parts = {"_archived", "mined"}

    total = 0
    toml_vs_file_mismatch = 0
    curator_tasks = 0
    judge_zero = []  # production judge matches no checkpoint at all
    judge_partial = []  # production judge misses some checkpoints

    for task_toml in sorted((root / "benchmarks").glob("*/*/task.toml")):
        if skip_parts & set(task_toml.parts):
            continue
        total += 1
        task_dir = task_toml.parent
        try:
            with open(task_toml, "rb") as f:
                data = tomllib.load(f)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            print(f"WARN unparseable {task_toml}: {exc}", file=sys.stderr)
            continue

        toml_names = {
            c["name"]
            for c in data.get("checkpoints", [])
            if isinstance(c, dict) and "name" in c
        }
        prod_names = filename_derived_names(task_dir)
        mismatched = toml_names != prod_names
        if mismatched:
            toml_vs_file_mismatch += 1
            if args.verbose:
                print(f"{task_dir.relative_to(root)}:")
                print(f"  task.toml only : {sorted(toml_names - prod_names)}")
                print(f"  checks/ only   : {sorted(prod_names - toml_names)}")

        es_path = task_dir / "expected_solution.json"
        modes = data.get("verification_modes", [])
        if "llm_curator" in modes and es_path.exists():
            curator_tasks += 1
            try:
                es_keys = set(
                    (json.loads(es_path.read_text()).get("checkpoints") or {}).keys()
                )
            except (json.JSONDecodeError, OSError) as exc:
                print(f"WARN unparseable {es_path}: {exc}", file=sys.stderr)
                continue
            covered = prod_names & es_keys
            if prod_names and not covered:
                judge_zero.append(task_dir.name)
            elif prod_names - es_keys:
                judge_partial.append(task_dir.name)

    print(f"active tasks scanned                 : {total}")
    print(f"task.toml vs checks/ name mismatch   : {toml_vs_file_mismatch}")
    print(f"llm_curator + expected_solution.json : {curator_tasks}")
    print(f"  prod judge matches ZERO checkpoints: {len(judge_zero)}")
    print(f"  prod judge matches only SOME       : {len(judge_partial)}")
    if args.verbose:
        if judge_zero:
            print("\nTier-2 complete no-op in production:")
            for t in judge_zero:
                print(f"  - {t}")
        if judge_partial:
            print("\nTier-2 partial coverage in production:")
            for t in judge_partial:
                print(f"  - {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
