#!/usr/bin/env python3
"""Cross-Repo Necessity Test (CRNT) validator.

Tests whether multi-repo benchmark tasks actually require multiple repos by
performing ablation analysis: for each repo, compute the maximum achievable
score if that repo were removed. A task passes CRNT if removing ANY single
repo drops the max score to ≤ threshold (default 60%).

Usage:
    python3 scripts/validation/crnt_validator.py benchmarks/.../task.toml
    python3 scripts/validation/crnt_validator.py benchmarks/.../task.toml --dry-run
    python3 scripts/validation/crnt_validator.py benchmarks/.../task.toml --output-dir /tmp/ablations
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
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


DEFAULT_THRESHOLD = 0.60


def parse_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML file using tomllib/tomli."""
    if tomllib is None:
        raise RuntimeError("No TOML parser available. Install tomli: pip install tomli")
    with open(path, "rb") as f:
        return tomllib.load(f)


@dataclass(frozen=True)
class RepoInfo:
    """Immutable representation of a repo entry from task.toml."""

    url: str
    rev: str
    path: str
    role: str = ""


@dataclass(frozen=True)
class CheckpointInfo:
    """Immutable representation of a checkpoint entry."""

    name: str
    weight: float
    verifier: str
    description: str = ""
    repo_deps: tuple[str, ...] = ()


@dataclass(frozen=True)
class AblatedConfig:
    """An ablation: the original task config with one repo removed."""

    task_id: str
    removed_repo: RepoInfo
    remaining_repos: tuple[RepoInfo, ...]
    original_config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Produce a modified task config dict with the repo removed."""
        import copy

        config = copy.deepcopy(self.original_config)
        config["repos"] = [
            r
            for r in config.get("repos", [])
            if r.get("path") != self.removed_repo.path
        ]
        return config


@dataclass(frozen=True)
class RepoAblationResult:
    """Result of ablating a single repo."""

    removed_repo: RepoInfo
    max_score_without: float
    lost_checkpoints: tuple[str, ...]
    passes_threshold: bool


@dataclass(frozen=True)
class CRNTResult:
    """Full CRNT evaluation result for a task."""

    task_id: str
    num_repos: int
    threshold: float
    repo_results: tuple[RepoAblationResult, ...]
    passes_crnt: bool


def extract_repos(config: dict[str, Any]) -> tuple[RepoInfo, ...]:
    """Extract repo list from parsed task config."""
    repos = config.get("repos", [])
    return tuple(
        RepoInfo(
            url=r.get("url", ""),
            rev=r.get("rev", ""),
            path=r.get("path", ""),
            role=r.get("role", ""),
        )
        for r in repos
    )


def extract_checkpoints(config: dict[str, Any]) -> tuple[CheckpointInfo, ...]:
    """Extract checkpoint list from parsed task config."""
    cps = config.get("checkpoints", [])
    return tuple(
        CheckpointInfo(
            name=c.get("name", ""),
            weight=c.get("weight", 0.0),
            verifier=c.get("verifier", ""),
            description=c.get("description", ""),
            repo_deps=tuple(c.get("repo_deps", [])),
        )
        for c in cps
    )


def map_checkpoints_to_repos(
    config: dict[str, Any],
) -> dict[str, set[str]]:
    """Map checkpoint names to the set of repo paths they depend on.

    Per-checkpoint anchoring: if a checkpoint has a non-empty repo_deps field,
    it is anchored ONLY to those repos. Otherwise, falls back to the
    ground_truth.required_files heuristic (all repos with required_files).
    If no ground_truth mapping exists, checkpoints without repo_deps are
    anchored to ALL repos (conservative: removing any repo loses them).
    """
    checkpoints = extract_checkpoints(config)
    gt = config.get("ground_truth", {})
    required_files = gt.get("required_files", [])

    # Build set of repos referenced in ground truth
    gt_repos: set[str] = {rf.get("repo", "") for rf in required_files if rf.get("repo")}

    # Fallback for checkpoints without repo_deps: use gt_repos if available,
    # otherwise anchor to all repos (conservative).
    all_repo_paths = {r.path for r in extract_repos(config)}
    fallback_repos = gt_repos if gt_repos else all_repo_paths

    # Per-checkpoint anchoring: if a checkpoint declares repo_deps, use those directly.
    # Otherwise fall back to the ground_truth heuristic (all repos with required_files,
    # or all repos if no ground_truth exists).
    checkpoint_repos: dict[str, set[str]] = {}
    for cp in checkpoints:
        if cp.repo_deps:
            checkpoint_repos[cp.name] = set(cp.repo_deps)
        else:
            checkpoint_repos[cp.name] = fallback_repos.copy()

    return checkpoint_repos


def compute_max_score_without_repo(
    config: dict[str, Any],
    removed_repo_path: str,
) -> tuple[float, tuple[str, ...]]:
    """Compute maximum achievable score if a repo is removed.

    Returns (max_score, lost_checkpoint_names).
    A checkpoint is "lost" if it depends on the removed repo.
    """
    checkpoints = extract_checkpoints(config)
    checkpoint_repos = map_checkpoints_to_repos(config)

    lost: list[str] = []
    score = 0.0

    for cp in checkpoints:
        deps = checkpoint_repos.get(cp.name, set())
        if removed_repo_path in deps:
            lost.append(cp.name)
        else:
            score += cp.weight

    return score, tuple(lost)


def generate_ablations(config: dict[str, Any]) -> tuple[AblatedConfig, ...]:
    """Generate one ablated config per repo in the task."""
    repos = extract_repos(config)
    task_id = config.get("task", {}).get("id", "unknown")

    ablations: list[AblatedConfig] = []
    for repo in repos:
        remaining = tuple(r for r in repos if r.path != repo.path)
        ablations.append(
            AblatedConfig(
                task_id=task_id,
                removed_repo=repo,
                remaining_repos=remaining,
                original_config=config,
            )
        )
    return tuple(ablations)


def evaluate_crnt(
    config: dict[str, Any],
    threshold: float = DEFAULT_THRESHOLD,
) -> CRNTResult:
    """Evaluate whether a task passes the Cross-Repo Necessity Test.

    A task passes CRNT if removing ANY single repo results in max score ≤ threshold.
    """
    repos = extract_repos(config)
    task_id = config.get("task", {}).get("id", "unknown")

    repo_results: list[RepoAblationResult] = []
    for repo in repos:
        max_score, lost_cps = compute_max_score_without_repo(config, repo.path)
        passes = max_score <= threshold
        repo_results.append(
            RepoAblationResult(
                removed_repo=repo,
                max_score_without=max_score,
                lost_checkpoints=lost_cps,
                passes_threshold=passes,
            )
        )

    # Task passes CRNT if ALL repo removals result in score ≤ threshold
    passes_crnt = all(r.passes_threshold for r in repo_results)

    return CRNTResult(
        task_id=task_id,
        num_repos=len(repos),
        threshold=threshold,
        repo_results=tuple(repo_results),
        passes_crnt=passes_crnt,
    )


def write_ablated_configs(
    ablations: tuple[AblatedConfig, ...],
    output_dir: Path,
) -> list[Path]:
    """Write ablated configs as TOML-like JSON files to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for ablation in ablations:
        filename = f"{ablation.task_id}_without_{ablation.removed_repo.path}.json"
        out_path = output_dir / filename
        with open(out_path, "w") as f:
            json.dump(ablation.to_dict(), f, indent=2)
        paths.append(out_path)
    return paths


def format_result(result: CRNTResult) -> str:
    """Format a CRNT result for human-readable output."""
    lines: list[str] = []
    status = "PASS" if result.passes_crnt else "FAIL"
    lines.append(
        f"CRNT {status}: {result.task_id} ({result.num_repos} repos, threshold={result.threshold:.0%})"
    )
    lines.append("")

    for rr in result.repo_results:
        repo_status = "drop" if rr.passes_threshold else "SURVIVES"
        lines.append(
            f"  Remove {rr.removed_repo.path:20s} → max_score={rr.max_score_without:.2f} "
            f"[{repo_status}] lost={list(rr.lost_checkpoints)}"
        )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-Repo Necessity Test (CRNT) validator for EnterpriseBench tasks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s benchmarks/dependency_management/dep-traversal-001/task.toml
  %(prog)s benchmarks/dependency_management/dep-traversal-001/task.toml --dry-run
  %(prog)s benchmarks/dependency_management/dep-traversal-001/task.toml --output-dir /tmp/ablations
  %(prog)s benchmarks/dependency_management/dep-traversal-001/task.toml --threshold 0.5
""",
    )
    parser.add_argument(
        "task_toml",
        type=Path,
        help="Path to task.toml file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what ablations would be created without writing files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write ablated configs (default: temp directory)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"CRNT pass threshold (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args(argv)

    if not args.task_toml.exists():
        print(f"Error: {args.task_toml} not found", file=sys.stderr)
        return 1

    config = parse_toml(args.task_toml)
    repos = extract_repos(config)

    if len(repos) < 2:
        print(f"Task has {len(repos)} repo(s) — CRNT only applies to multi-repo tasks.")
        return 0

    ablations = generate_ablations(config)

    if args.dry_run:
        task_id = config.get("task", {}).get("id", "unknown")
        print(f"Dry run for {task_id} ({len(repos)} repos):")
        print()
        for abl in ablations:
            remaining_paths = [r.path for r in abl.remaining_repos]
            print(
                f"  Ablation: remove '{abl.removed_repo.path}' ({abl.removed_repo.role})"
            )
            print(f"    Remaining repos: {remaining_paths}")
            max_score, lost = compute_max_score_without_repo(
                config, abl.removed_repo.path
            )
            print(f"    Estimated max score: {max_score:.2f}")
            print(f"    Lost checkpoints: {list(lost)}")
            print()
        return 0

    # Write ablated configs if requested
    if args.output_dir is not None:
        written = write_ablated_configs(ablations, args.output_dir)
        for p in written:
            print(f"Wrote: {p}")
        print()

    # Evaluate CRNT
    result = evaluate_crnt(config, threshold=args.threshold)

    if args.json:
        output = {
            "task_id": result.task_id,
            "num_repos": result.num_repos,
            "threshold": result.threshold,
            "passes_crnt": result.passes_crnt,
            "repo_results": [
                {
                    "removed_repo": rr.removed_repo.path,
                    "max_score_without": rr.max_score_without,
                    "lost_checkpoints": list(rr.lost_checkpoints),
                    "passes_threshold": rr.passes_threshold,
                }
                for rr in result.repo_results
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_result(result))

    return 0 if result.passes_crnt else 2


if __name__ == "__main__":
    sys.exit(main())
