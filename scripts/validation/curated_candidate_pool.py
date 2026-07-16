#!/usr/bin/env python3
"""Emit the retrieval-necessity candidate pool for the rryas 3-arm curated set.

The rryas study (MCP vs baseline vs CLI) only measures anything if the arm's
tool access is a genuine, load-bearing variable. The 2026-07-15 shakeout made the
failure mode concrete: on ``technical_debt/calibration-001`` (single local repo,
dead-code audit) the cli agent did 41 turns of real work but made 0 sgx calls —
it solved the task with local grep/read and never needed retrieval, so the run
was (correctly) gated ``infra_sgx_unused``. A single-local-repo task cannot
separate the arms.

So the first, hard filter for the curated set is *retrieval necessity*: prefer
MULTI-REPO tasks where every declared repo is structurally required (the
Cross-Repo Necessity Test — see ``crnt_validator.py``). This tool sweeps the
active corpus and emits the CRNT-passing multi-repo pool with the metadata a
curator needs (suite, type, stratum, repo count), as a table or JSON.

This is a STRUCTURAL pre-filter only. It does NOT prove an agent needs the repo
(that is the per-arm empirical pilot: does baseline underperform, does cli/mcp
actually call its tool >0 times) or that the task's scoring is prompt-echo
resistant. See docs/internal/rryas_curated_dataset_handoff.md for the full gate.

Usage:
    python3 scripts/validation/curated_candidate_pool.py            # table
    python3 scripts/validation/curated_candidate_pool.py --json     # JSON array
    python3 scripts/validation/curated_candidate_pool.py --min-repos 3
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - py<3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXCLUDED_TOP_DIRS = {"_archived", "mined"}


def _repo_names(repos: list[dict[str, Any]]) -> set[str]:
    """The set of declared repo identifiers, matching how ground_truth.repo names them."""
    names: set[str] = set()
    for r in repos:
        name = r.get("path") or r.get("url", "").rstrip("/").split("/")[-1]
        if name:
            names.add(name)
    return names


def _crnt_pass(task: dict[str, Any]) -> bool:
    """True when the task is multi-repo AND every declared repo has a required_file.

    Mirrors crnt_validator's structural rule: a repo with no required_file is not
    provably necessary, so the task cannot claim to force cross-repo retrieval.
    """
    repos = task.get("repos", [])
    if len(repos) < 2:
        return False
    required = task.get("ground_truth", {}).get("required_files", [])
    req_repos = {rf.get("repo") for rf in required if rf.get("repo")}
    if not req_repos:
        return False
    return _repo_names(repos).issubset(req_repos)


def scan(min_repos: int) -> list[dict[str, Any]]:
    """Return the CRNT-passing candidate rows across the active corpus."""
    rows: list[dict[str, Any]] = []
    for f in sorted(glob.glob(str(REPO_ROOT / "benchmarks" / "*" / "*" / "task.toml"))):
        parts = Path(f).relative_to(REPO_ROOT).parts  # benchmarks/<suite>/<task>/task.toml
        suite, task_id = parts[1], parts[2]
        if suite in EXCLUDED_TOP_DIRS:
            continue
        try:
            with open(f, "rb") as fh:
                task = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        repos = task.get("repos", [])
        if len(repos) < min_repos or not _crnt_pass(task):
            continue
        rows.append(
            {
                "suite": suite,
                "task_id": task_id,
                "repos": len(repos),
                "stratum": task.get("difficulty_stratum", "?"),
                "task_type": task.get("task", {}).get("task_type", "?"),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit a JSON array")
    ap.add_argument(
        "--min-repos", type=int, default=2, help="minimum declared repos (default 2)"
    )
    args = ap.parse_args(argv)

    rows = scan(args.min_repos)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    print(f"Retrieval-necessity candidate pool: {len(rows)} tasks (>= {args.min_repos} repos, CRNT-pass)\n")
    for label, key in (("stratum", "stratum"), ("task_type", "task_type"), ("suite", "suite")):
        counts = collections.Counter(r[key] for r in rows)
        print(f"by {label:<10}: {dict(sorted(counts.items()))}")
    print()
    for r in rows:
        print(f"  {r['suite']}/{r['task_id']:<44} repos={r['repos']} {r['stratum']:<12} {r['task_type']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
