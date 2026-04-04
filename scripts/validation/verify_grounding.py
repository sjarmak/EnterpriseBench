#!/usr/bin/env python3
"""Verifier grounding validator for EnterpriseBench ablation testing.

Reads a task.toml, extracts checkpoint-to-repo dependencies, and reports
which checkpoints are expected to fail when each repo is ablated (removed).
This validates that verifiers are properly "grounded" — i.e., they actually
test things that require the repo they claim to depend on.

Usage:
    python3 scripts/validation/verify_grounding.py benchmarks/.../task_dir
    python3 scripts/validation/verify_grounding.py benchmarks/.../task_dir --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Reuse parsing utilities from crnt_validator
sys.path.insert(0, str(Path(__file__).resolve().parent))
from crnt_validator import (
    extract_checkpoints,
    extract_repos,
    map_checkpoints_to_repos,
    parse_toml,
)


@dataclass(frozen=True)
class GroundingExpectation:
    """A single expectation: checkpoint X should fail when repo Y is removed."""

    checkpoint_name: str
    checkpoint_weight: float
    anchored_repo: str
    expected_to_fail: bool


@dataclass(frozen=True)
class GroundingResult:
    """Result of evaluating one grounding expectation against ablation data."""

    checkpoint_name: str
    anchored_repo: str
    expected_to_fail: bool
    actually_failed: bool
    grounding_valid: bool
    explanation: str


def extract_checkpoint_repo_deps(config: dict[str, Any]) -> dict[str, set[str]]:
    """Extract the repo dependencies for each checkpoint.

    Returns a dict mapping checkpoint name to set of repo paths it depends on.
    Uses the same logic as crnt_validator.map_checkpoints_to_repos.
    """
    return map_checkpoints_to_repos(config)


def identify_grounding_expectations(
    config: dict[str, Any],
) -> tuple[GroundingExpectation, ...]:
    """Identify all grounding expectations for a task.

    For each repo that appears in any checkpoint's dependencies, generates
    an expectation that the checkpoint should fail when that repo is removed.

    Returns a tuple of GroundingExpectation objects.
    """
    checkpoint_deps = extract_checkpoint_repo_deps(config)
    checkpoints = extract_checkpoints(config)
    checkpoint_weights = {cp.name: cp.weight for cp in checkpoints}

    expectations: list[GroundingExpectation] = []
    for cp_name, repo_deps in checkpoint_deps.items():
        weight = checkpoint_weights.get(cp_name, 0.0)
        for repo_path in sorted(repo_deps):
            expectations.append(
                GroundingExpectation(
                    checkpoint_name=cp_name,
                    checkpoint_weight=weight,
                    anchored_repo=repo_path,
                    expected_to_fail=True,
                )
            )

    return tuple(expectations)


def evaluate_grounding(
    config: dict[str, Any],
    ablation_results: dict[str, dict[str, bool]] | None = None,
) -> tuple[GroundingResult, ...]:
    """Evaluate grounding validity for all checkpoint-repo pairs.

    Args:
        config: Parsed task.toml config dict.
        ablation_results: Optional dict mapping repo_path -> {checkpoint_name: failed}.
            If None, performs static analysis only (assumes expectations hold).

    Returns a tuple of GroundingResult objects.
    """
    expectations = identify_grounding_expectations(config)
    results: list[GroundingResult] = []

    for exp in expectations:
        if ablation_results is not None:
            repo_results = ablation_results.get(exp.anchored_repo, {})
            actually_failed = repo_results.get(exp.checkpoint_name, False)
            grounding_valid = exp.expected_to_fail == actually_failed
            if grounding_valid:
                explanation = (
                    f"Checkpoint '{exp.checkpoint_name}' correctly failed "
                    f"when repo '{exp.anchored_repo}' was removed"
                )
            else:
                explanation = (
                    f"Checkpoint '{exp.checkpoint_name}' did NOT fail "
                    f"when repo '{exp.anchored_repo}' was removed — "
                    f"verifier may not be properly grounded to this repo"
                )
        else:
            # Static analysis mode — no ablation data available
            actually_failed = True  # Assume expectation holds
            grounding_valid = True
            explanation = (
                f"Checkpoint '{exp.checkpoint_name}' is anchored to "
                f"repo '{exp.anchored_repo}' (static analysis, no ablation data)"
            )

        results.append(
            GroundingResult(
                checkpoint_name=exp.checkpoint_name,
                anchored_repo=exp.anchored_repo,
                expected_to_fail=exp.expected_to_fail,
                actually_failed=actually_failed,
                grounding_valid=grounding_valid,
                explanation=explanation,
            )
        )

    return tuple(results)


def format_grounding_report(results: tuple[GroundingResult, ...]) -> str:
    """Format grounding results as a human-readable table."""
    if not results:
        return (
            "No grounding expectations found (single-repo task or no checkpoint deps)."
        )

    lines: list[str] = []
    lines.append("Verifier Grounding Report")
    lines.append("=" * 60)
    lines.append("")

    # Summary
    total = len(results)
    valid = sum(1 for r in results if r.grounding_valid)
    lines.append(f"Total expectations: {total}")
    lines.append(f"Valid groundings:   {valid}/{total}")
    lines.append("")

    # Header
    lines.append(
        f"{'Checkpoint':<30s} {'Repo Removed':<20s} {'Expected':<10s} "
        f"{'Actual':<10s} {'Valid':<6s}"
    )
    lines.append("-" * 80)

    for r in results:
        expected = "FAIL" if r.expected_to_fail else "PASS"
        actual = "FAIL" if r.actually_failed else "PASS"
        valid_str = "OK" if r.grounding_valid else "BAD"
        lines.append(
            f"{r.checkpoint_name:<30s} {r.anchored_repo:<20s} {expected:<10s} "
            f"{actual:<10s} {valid_str:<6s}"
        )

    return "\n".join(lines)


def format_grounding_json(results: tuple[GroundingResult, ...]) -> str:
    """Format grounding results as JSON."""
    total = len(results)
    valid = sum(1 for r in results if r.grounding_valid)

    output = {
        "summary": {
            "total_expectations": total,
            "valid_groundings": valid,
            "all_grounded": total == valid,
        },
        "results": [
            {
                "checkpoint": r.checkpoint_name,
                "anchored_repo": r.anchored_repo,
                "expected_to_fail": r.expected_to_fail,
                "actually_failed": r.actually_failed,
                "grounding_valid": r.grounding_valid,
                "explanation": r.explanation,
            }
            for r in results
        ],
    }
    return json.dumps(output, indent=2)


def load_ablation_results(results_dir: Path) -> dict[str, dict[str, bool]]:
    """Load ablation results from the results directory structure.

    Expects layout: results_dir/ablate-{repo}/rep{N}/results.json
    Each results.json should have a "scores" dict mapping checkpoint names
    to numeric scores (0.0 = failed, >0.0 = passed).

    Returns dict mapping repo_path -> {checkpoint_name: failed_bool}.
    """
    ablation_results: dict[str, dict[str, bool]] = {}

    if not results_dir.is_dir():
        return ablation_results

    for ablation_dir in sorted(results_dir.iterdir()):
        if not ablation_dir.is_dir() or not ablation_dir.name.startswith("ablate-"):
            continue

        repo_name = ablation_dir.name[len("ablate-") :]
        checkpoint_failures: dict[str, list[bool]] = {}

        for rep_dir in sorted(ablation_dir.iterdir()):
            if not rep_dir.is_dir() or not rep_dir.name.startswith("rep"):
                continue

            results_file = rep_dir / "results.json"
            if not results_file.is_file():
                continue

            try:
                data = json.loads(results_file.read_text())
                scores = data.get("scores", {})
                for cp_name, score in scores.items():
                    if cp_name not in checkpoint_failures:
                        checkpoint_failures[cp_name] = []
                    checkpoint_failures[cp_name].append(float(score) == 0.0)
            except (json.JSONDecodeError, OSError, ValueError):
                continue

        # A checkpoint "failed" if it failed in ALL reps (conservative)
        repo_result: dict[str, bool] = {}
        for cp_name, failures in checkpoint_failures.items():
            repo_result[cp_name] = all(failures) if failures else False

        ablation_results[repo_name] = repo_result

    return ablation_results


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify that checkpoint verifiers are grounded to their declared repo dependencies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s benchmarks/dependency_management/dep-traversal-001/
  %(prog)s benchmarks/dependency_management/dep-traversal-001/ --json
  %(prog)s benchmarks/incident_response/incident-inv-001/ --results-dir results/runs/incident-inv-001/
""",
    )
    parser.add_argument(
        "task_dir",
        type=Path,
        help="Path to task directory (containing task.toml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="Directory containing ablation run results (if available)",
    )

    args = parser.parse_args(argv)

    task_toml = args.task_dir / "task.toml"
    if not task_toml.exists():
        print(f"Error: {task_toml} not found", file=sys.stderr)
        return 1

    config = parse_toml(task_toml)
    repos = extract_repos(config)

    if len(repos) < 2:
        print(
            f"Task has {len(repos)} repo(s) — grounding analysis only applies to multi-repo tasks."
        )
        return 0

    # Load ablation results if available
    ablation_results = None
    if args.results_dir is not None:
        ablation_results = load_ablation_results(args.results_dir)
        if not ablation_results:
            print(
                f"Warning: no ablation results found in {args.results_dir}, "
                "falling back to static analysis",
                file=sys.stderr,
            )

    results = evaluate_grounding(config, ablation_results)

    if args.json:
        print(format_grounding_json(results))
    else:
        print(format_grounding_report(results))

    # Exit with non-zero if any grounding is invalid
    all_valid = all(r.grounding_valid for r in results)
    return 0 if all_valid else 2


if __name__ == "__main__":
    sys.exit(main())
