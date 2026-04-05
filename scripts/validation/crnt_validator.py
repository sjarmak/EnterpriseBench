#!/usr/bin/env python3
"""Cross-Repo Necessity Test (CRNT) validator.

Validates that multi-repo benchmark tasks structurally require each declared
repo by checking that ground_truth.required_files are distributed across repos.

A task passes CRNT if every declared repo has at least one required_file entry.
This is a structural check — empirical validation (does an agent actually need
the repo?) is done separately via cognitive ablation.

Usage:
    python3 scripts/validation/crnt_validator.py benchmarks/.../task.toml
    python3 scripts/validation/crnt_validator.py benchmarks/.../task.toml --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


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
class RepoFileCoverage:
    """Coverage of required_files for a single repo."""

    repo_path: str
    required_file_count: int
    has_coverage: bool


@dataclass(frozen=True)
class CRNTResult:
    """Full CRNT evaluation result for a task."""

    task_id: str
    num_repos: int
    repo_coverage: tuple[RepoFileCoverage, ...]
    passes_crnt: bool
    uncovered_repos: tuple[str, ...]


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
        )
        for c in cps
    )


def evaluate_crnt(config: dict[str, Any]) -> CRNTResult:
    """Evaluate whether a task passes the Cross-Repo Necessity Test.

    A task passes CRNT if every declared repo has at least one entry in
    ground_truth.required_files. This is a structural check ensuring the
    task definition claims each repo is necessary.
    """
    repos = extract_repos(config)
    task_id = config.get("task", {}).get("id", "unknown")
    repo_paths = {r.path for r in repos}

    gt = config.get("ground_truth", {})
    required_files = gt.get("required_files", [])

    # Count required_files per repo
    files_per_repo: dict[str, int] = {rp: 0 for rp in repo_paths}
    for rf in required_files:
        repo = rf.get("repo", "")
        if repo in files_per_repo:
            files_per_repo[repo] += 1

    coverage = tuple(
        RepoFileCoverage(
            repo_path=rp,
            required_file_count=files_per_repo[rp],
            has_coverage=files_per_repo[rp] > 0,
        )
        for rp in sorted(repo_paths)
    )

    uncovered = tuple(c.repo_path for c in coverage if not c.has_coverage)
    passes = len(uncovered) == 0 and len(repos) >= 2

    return CRNTResult(
        task_id=task_id,
        num_repos=len(repos),
        repo_coverage=coverage,
        passes_crnt=passes,
        uncovered_repos=uncovered,
    )


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
    lines.append(f"CRNT {status}: {result.task_id} ({result.num_repos} repos)")
    lines.append("")

    for rc in result.repo_coverage:
        marker = "ok" if rc.has_coverage else "MISSING"
        lines.append(
            f"  {rc.repo_path:20s} required_files={rc.required_file_count} [{marker}]"
        )

    if result.uncovered_repos:
        lines.append("")
        lines.append(f"  Repos without required_files: {list(result.uncovered_repos)}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-Repo Necessity Test (CRNT) validator for EnterpriseBench tasks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s benchmarks/dependency_management/dep-traversal-001/task.toml
  %(prog)s benchmarks/dependency_management/dep-traversal-001/task.toml --json
""",
    )
    parser.add_argument(
        "task_toml",
        type=Path,
        help="Path to task.toml file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write ablated configs (for cognitive ablation runs)",
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

    # Write ablated configs if requested (for cognitive ablation)
    if args.output_dir is not None:
        ablations = generate_ablations(config)
        written = write_ablated_configs(ablations, args.output_dir)
        for p in written:
            print(f"Wrote: {p}")
        print()

    result = evaluate_crnt(config)

    if args.json:
        output = {
            "task_id": result.task_id,
            "num_repos": result.num_repos,
            "passes_crnt": result.passes_crnt,
            "repo_coverage": [
                {
                    "repo": rc.repo_path,
                    "required_file_count": rc.required_file_count,
                    "has_coverage": rc.has_coverage,
                }
                for rc in result.repo_coverage
            ],
            "uncovered_repos": list(result.uncovered_repos),
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_result(result))

    return 0 if result.passes_crnt else 2


if __name__ == "__main__":
    sys.exit(main())
