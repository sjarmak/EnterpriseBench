#!/usr/bin/env python3
"""Verifier grounding validator for EnterpriseBench ablation testing.

Reads a task.toml, checks that each repo has ground_truth.required_files,
and if ablation run results are provided, verifies that removing a repo
actually degrades the agent's score.

Usage:
    python3 scripts/validation/verify_grounding.py benchmarks/.../task_dir
    python3 scripts/validation/verify_grounding.py benchmarks/.../task_dir --json
    python3 scripts/validation/verify_grounding.py benchmarks/.../task_dir --results-dir results/runs/task-id/
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
    extract_repos,
    evaluate_crnt,
    parse_toml,
)


@dataclass(frozen=True)
class GroundingResult:
    """Result of evaluating grounding for one repo."""

    repo_path: str
    has_required_files: bool
    ablation_score: float | None
    grounding_valid: bool
    explanation: str


def evaluate_grounding(
    config: dict[str, Any],
    ablation_results: dict[str, float] | None = None,
) -> tuple[GroundingResult, ...]:
    """Evaluate grounding validity for each repo.

    Args:
        config: Parsed task.toml config dict.
        ablation_results: Optional dict mapping repo_path -> ablated_score.
            If None, performs static analysis only.

    Returns a tuple of GroundingResult objects.
    """
    crnt = evaluate_crnt(config)
    results: list[GroundingResult] = []

    for rc in crnt.repo_coverage:
        if ablation_results is not None and rc.repo_path in ablation_results:
            ablated = ablation_results[rc.repo_path]
            # Grounding is valid if removing the repo degrades the score
            valid = ablated < 1.0 if rc.has_coverage else True
            explanation = f"Ablated score={ablated:.2f} — " + (
                "score degraded as expected"
                if valid
                else "score NOT degraded, repo may be decorative"
            )
        else:
            ablated = None
            valid = rc.has_coverage
            explanation = (
                f"Repo has {rc.required_file_count} required_files (static analysis)"
                if rc.has_coverage
                else "Repo has no required_files — not structurally grounded"
            )

        results.append(
            GroundingResult(
                repo_path=rc.repo_path,
                has_required_files=rc.has_coverage,
                ablation_score=ablated,
                grounding_valid=valid,
                explanation=explanation,
            )
        )

    return tuple(results)


def format_grounding_report(results: tuple[GroundingResult, ...]) -> str:
    """Format grounding results as a human-readable table."""
    if not results:
        return "No repos found."

    lines: list[str] = []
    lines.append("Verifier Grounding Report")
    lines.append("=" * 60)
    lines.append("")

    total = len(results)
    valid = sum(1 for r in results if r.grounding_valid)
    lines.append(f"Total repos: {total}")
    lines.append(f"Grounded:    {valid}/{total}")
    lines.append("")

    lines.append(f"{'Repo':<25s} {'Files':<8s} {'Ablated':<10s} {'Valid':<6s}")
    lines.append("-" * 55)

    for r in results:
        files = "yes" if r.has_required_files else "NO"
        ablated = f"{r.ablation_score:.2f}" if r.ablation_score is not None else "n/a"
        valid_str = "OK" if r.grounding_valid else "BAD"
        lines.append(f"{r.repo_path:<25s} {files:<8s} {ablated:<10s} {valid_str:<6s}")

    return "\n".join(lines)


def format_grounding_json(results: tuple[GroundingResult, ...]) -> str:
    """Format grounding results as JSON."""
    total = len(results)
    valid = sum(1 for r in results if r.grounding_valid)

    output = {
        "summary": {
            "total_repos": total,
            "grounded_repos": valid,
            "all_grounded": total == valid,
        },
        "results": [
            {
                "repo": r.repo_path,
                "has_required_files": r.has_required_files,
                "ablation_score": r.ablation_score,
                "grounding_valid": r.grounding_valid,
                "explanation": r.explanation,
            }
            for r in results
        ],
    }
    return json.dumps(output, indent=2)


def load_ablation_results(results_dir: Path) -> dict[str, float]:
    """Load ablation results from the results directory structure.

    Expects layout: results_dir/ablate-{repo}/rep{N}/results.json
    Returns dict mapping repo_path -> mean_score across reps.
    """
    ablation_results: dict[str, list[float]] = {}

    if not results_dir.is_dir():
        return {}

    for ablation_dir in sorted(results_dir.iterdir()):
        if not ablation_dir.is_dir() or not ablation_dir.name.startswith("ablate-"):
            continue

        repo_name = ablation_dir.name[len("ablate-") :]
        scores: list[float] = []

        for rep_dir in sorted(ablation_dir.iterdir()):
            if not rep_dir.is_dir() or not rep_dir.name.startswith("rep"):
                continue

            results_file = rep_dir / "results.json"
            if not results_file.is_file():
                continue

            try:
                data = json.loads(results_file.read_text())
                sc = data.get("scores", {})
                cps = sc.get("checkpoints", [])
                if cps:
                    total = sum(c["weight"] * c["score"] for c in cps)
                    max_w = sum(c["weight"] for c in cps)
                    scores.append(total / max_w if max_w else 0.0)
            except (json.JSONDecodeError, OSError, ValueError, KeyError):
                continue

        if scores:
            ablation_results[repo_name] = sum(scores) / len(scores)

    return ablation_results


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify that repos are grounded in the task's required_files and ablation results",
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
    ablation_data = None
    if args.results_dir is not None:
        ablation_data = load_ablation_results(args.results_dir) or None
        if ablation_data is None:
            print(
                f"Warning: no ablation results found in {args.results_dir}, "
                "falling back to static analysis",
                file=sys.stderr,
            )

    results = evaluate_grounding(config, ablation_data)

    if args.json:
        print(format_grounding_json(results))
    else:
        print(format_grounding_report(results))

    all_valid = all(r.grounding_valid for r in results)
    return 0 if all_valid else 2


if __name__ == "__main__":
    sys.exit(main())
