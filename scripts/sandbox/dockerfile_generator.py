#!/usr/bin/env python3
"""Generate Dockerfile variants for EnterpriseBench tasks.

Reads a task.toml and produces three Dockerfile variants:
  1. Dockerfile       -- standard local clone from sg-evals mirrors (baseline)
  2. Dockerfile.sg_only -- empty workspace, MCP mandatory, SOURCEGRAPH_REPOS set
  3. Dockerfile.hybrid  -- local clone + MCP available (both tools)

Adapted from CodeScaleBench's migrate_dockerfiles_to_mirrors.py and
inject_sg_repo_env.py, simplified for EnterpriseBench's task.toml format.

Usage:
    python3 scripts/sandbox/dockerfile_generator.py benchmarks/EXAMPLE_TASK.toml
    python3 scripts/sandbox/dockerfile_generator.py benchmarks/EXAMPLE_TASK.toml --output-dir /tmp/out
    python3 scripts/sandbox/dockerfile_generator.py benchmarks/ --all
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Reuse the TOML parser from create_sg_mirrors
sys.path.insert(0, str(REPO_ROOT / "scripts" / "infra"))
from create_sg_mirrors import parse_toml, find_task_files, ORG

sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
from validation import validate_repo_entry


# ═══════════════════════════════════════════════════════════════
#  MIRROR NAME GENERATION
# ═══════════════════════════════════════════════════════════════

def mirror_name_for_repo(url: str, rev: str) -> str:
    """Generate sg-evals mirror name for a repo entry."""
    upstream = url.replace("https://", "").replace("http://", "").rstrip("/")
    if upstream.endswith(".git"):
        upstream = upstream[:-4]
    repo_name = upstream.split("/")[-1]

    is_tag = not all(c in "0123456789abcdef" for c in rev.lower())
    ref_suffix = rev if is_tag else rev[:8]
    return f"{repo_name}--{ref_suffix}"


def sourcegraph_repos_value(repos: list[dict]) -> str:
    """Generate comma-separated SOURCEGRAPH_REPOS value."""
    mirrors = []
    for repo in repos:
        url = repo.get("url", "")
        rev = repo.get("rev", "")
        if url and rev:
            mirrors.append(f"{ORG}/{mirror_name_for_repo(url, rev)}")
    return ",".join(mirrors)


def sourcegraph_env_var(repos: list[dict]) -> tuple[str, str]:
    """Return (env_var_name, env_var_value) for Sourcegraph repo config."""
    mirrors = []
    for repo in repos:
        url = repo.get("url", "")
        rev = repo.get("rev", "")
        if url and rev:
            mirrors.append(f"{ORG}/{mirror_name_for_repo(url, rev)}")

    if len(mirrors) == 1:
        return "SOURCEGRAPH_REPO_NAME", mirrors[0]
    else:
        return "SOURCEGRAPH_REPOS", ",".join(mirrors)


# ═══════════════════════════════════════════════════════════════
#  DOCKERFILE GENERATION
# ═══════════════════════════════════════════════════════════════

def _base_image_for_languages(languages: list[str]) -> str:
    """Select Docker base image based on task's primary language."""
    if "go" in languages:
        return "golang:1.21-bookworm"
    if "python" in languages:
        return "python:3.11-bookworm"
    if "java" in languages:
        return "eclipse-temurin:17-jdk-jammy"
    if "rust" in languages:
        return "rust:1.75-bookworm"
    if "javascript" in languages or "typescript" in languages:
        return "node:20-bookworm"
    if "c++" in languages or "c" in languages:
        return "gcc:13-bookworm"
    if "csharp" in languages:
        return "mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim"
    return "ubuntu:22.04"


def generate_standard_dockerfile(task_data: dict) -> str:
    """Generate standard Dockerfile: local clone from sg-evals mirrors."""
    repos = task_data.get("repos", [])
    task_info = task_data.get("task", {})
    languages = task_data.get("metadata", {}).get("languages", [])

    # Choose base image based on primary language
    base_image = _base_image_for_languages(languages)

    lines = [
        f"# EnterpriseBench task: {task_info.get('id', 'unknown')}",
        f"# Standard Dockerfile: local clone from sg-evals mirrors",
        f"FROM {base_image}",
        "",
        "RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*",
        "",
        "WORKDIR /workspace",
        "",
    ]

    # Clone each repo from its sg-evals mirror
    for repo in repos:
        url = repo.get("url", "")
        rev = repo.get("rev", "")
        path = repo.get("path", "")
        role = repo.get("role", "")

        if not url or not rev or not path:
            continue

        mirror = mirror_name_for_repo(url, rev)
        mirror_url = f"https://github.com/{ORG}/{mirror}.git"

        lines.append(f"# {role}: {url} @ {rev}")
        lines.append(f"RUN git clone --depth 1 {mirror_url} /workspace/{path}")
        lines.append("")

    lines.append("WORKDIR /workspace")
    lines.append("")

    return "\n".join(lines)


def generate_sg_only_dockerfile(task_data: dict) -> str:
    """Generate Dockerfile.sg_only: empty workspace, MCP mandatory."""
    repos = task_data.get("repos", [])
    task_info = task_data.get("task", {})

    env_name, env_value = sourcegraph_env_var(repos)

    lines = [
        f"# EnterpriseBench task: {task_info.get('id', 'unknown')}",
        f"# SG-only Dockerfile: empty workspace, Sourcegraph MCP mandatory",
        f"FROM ubuntu:22.04",
        "",
        f"ENV {env_name}={env_value}",
        "",
        "RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*",
        "",
        "WORKDIR /workspace",
        "",
        "# No repos cloned -- agent must use Sourcegraph MCP for all code access",
        "",
    ]

    return "\n".join(lines)


def generate_hybrid_dockerfile(task_data: dict) -> str:
    """Generate Dockerfile.hybrid: local clone + MCP available."""
    repos = task_data.get("repos", [])
    task_info = task_data.get("task", {})
    languages = task_data.get("metadata", {}).get("languages", [])

    env_name, env_value = sourcegraph_env_var(repos)

    # Same base image logic as standard
    base_image = _base_image_for_languages(languages)

    lines = [
        f"# EnterpriseBench task: {task_info.get('id', 'unknown')}",
        f"# Hybrid Dockerfile: local clone + Sourcegraph MCP available",
        f"FROM {base_image}",
        "",
        f"ENV {env_name}={env_value}",
        "",
        "RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*",
        "",
        "WORKDIR /workspace",
        "",
    ]

    for repo in repos:
        url = repo.get("url", "")
        rev = repo.get("rev", "")
        path = repo.get("path", "")
        role = repo.get("role", "")

        if not url or not rev or not path:
            continue

        mirror = mirror_name_for_repo(url, rev)
        mirror_url = f"https://github.com/{ORG}/{mirror}.git"

        lines.append(f"# {role}: {url} @ {rev}")
        lines.append(f"RUN git clone --depth 1 {mirror_url} /workspace/{path}")
        lines.append("")

    lines.append("# MCP also available via SOURCEGRAPH_REPOS env var")
    lines.append("WORKDIR /workspace")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def generate_for_task(task_file: Path, output_dir: Path | None = None) -> dict[str, Path]:
    """Generate all Dockerfile variants for a single task.

    Returns dict of variant name -> output path.
    """
    task_data = parse_toml(task_file)

    for repo in task_data.get("repos", []):
        validate_repo_entry(repo)

    if output_dir is None:
        output_dir = task_file.parent / "environment"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Standard
    content = generate_standard_dockerfile(task_data)
    path = output_dir / "Dockerfile"
    path.write_text(content)
    results["standard"] = path

    # SG-only
    content = generate_sg_only_dockerfile(task_data)
    path = output_dir / "Dockerfile.sg_only"
    path.write_text(content)
    results["sg_only"] = path

    # Hybrid
    content = generate_hybrid_dockerfile(task_data)
    path = output_dir / "Dockerfile.hybrid"
    path.write_text(content)
    results["hybrid"] = path

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Generate Dockerfile variants for EnterpriseBench tasks"
    )
    parser.add_argument("path", type=Path,
                        help="Path to a task.toml file or directory containing tasks")
    parser.add_argument("--output-dir", "-o", type=Path, default=None,
                        help="Output directory for Dockerfiles (default: alongside task.toml)")
    parser.add_argument("--all", action="store_true",
                        help="Process all task files in directory")
    args = parser.parse_args()

    if not args.path.exists():
        print(f"ERROR: {args.path} does not exist", file=sys.stderr)
        sys.exit(1)

    if args.all or args.path.is_dir():
        task_files = find_task_files(args.path)
    else:
        task_files = [args.path]

    if not task_files:
        print(f"ERROR: No .toml files found in {args.path}", file=sys.stderr)
        sys.exit(1)

    total_generated = 0

    for task_file in task_files:
        print(f"\nProcessing: {task_file}")
        try:
            results = generate_for_task(task_file, args.output_dir)
            for variant, path in results.items():
                print(f"  {variant:12s} -> {path}")
            total_generated += len(results)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)

    print(f"\nGenerated {total_generated} Dockerfiles from {len(task_files)} task(s)")


if __name__ == "__main__":
    main()
