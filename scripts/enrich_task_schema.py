#!/usr/bin/env python3
"""Enrich all task.toml files with new schema fields.

Adds the following fields to each task:
- mcp_suite: benchmark suite identifier (always "eb_v1")
- repo_set_id: semantic repo grouping based on actual repos used
- org_scale: boolean for enterprise-complexity tasks
- verification_modes: array of verification strategies

This script reads each task.toml, determines appropriate values for the new
fields, and writes them back by appending TOML lines (preserving existing content).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Repo URL -> repo_set_id mapping
# Derived from analyzing actual repo usage across all 111 tasks
_REPO_SET_RULES: list[tuple[set[str], str]] = [
    # Kubernetes ecosystem (k8s, etcd, grpc-go, cobra, protobuf-go, calico)
    (
        {
            "kubernetes/kubernetes",
            "etcd-io/etcd",
            "grpc/grpc-go",
            "spf13/cobra",
            "protocolbuffers/protobuf-go",
            "grpc-ecosystem/go-grpc-middleware",
            "projectcalico/calico",
        },
        "kubernetes-ecosystem",
    ),
    # Envoy/Istio service mesh ecosystem
    (
        {"envoyproxy/envoy", "envoyproxy/go-control-plane", "istio/istio"},
        "envoy-ecosystem",
    ),
    # gRPC standalone (grpc-go only, grpc-node)
    (
        {"grpc/grpc-go", "grpc/grpc-node", "kubernetes-client/javascript"},
        "grpc-ecosystem",
    ),
    # Hashicorp ecosystem
    (
        {"hashicorp/terraform", "hashicorp/consul", "hashicorp/vault"},
        "hashicorp-ecosystem",
    ),
    # Observability (grafana, prometheus)
    ({"grafana/grafana", "prometheus/prometheus"}, "observability-ecosystem"),
    # Python web (flask, click, requests)
    ({"pallets/flask", "pallets/click", "psf/requests"}, "python-web-ecosystem"),
    # Python HTTP (urllib3, requests, boto3, aws-cli)
    (
        {"urllib3/urllib3", "psf/requests", "boto/boto3", "aws/aws-cli"},
        "python-http-ecosystem",
    ),
    # JS tooling (babel, pnpm, next.js)
    ({"babel/babel"}, "babel-ecosystem"),
    ({"pnpm/pnpm"}, "pnpm-ecosystem"),
    ({"vercel/next.js"}, "nextjs-ecosystem"),
    # JS libraries (lodash, webpack, jest)
    ({"lodash/lodash", "webpack/webpack", "jestjs/jest"}, "js-toolchain-ecosystem"),
    ({"axios/axios"}, "js-http-ecosystem"),
    # React ecosystem
    ({"facebook/react"}, "react-ecosystem"),
    # Rust compiler
    ({"rust-lang/rust"}, "rust-compiler-ecosystem"),
    # Java ecosystem (spring, jackson, kafka, log4j, dropwizard, camel)
    (
        {
            "FasterXML/jackson-databind",
            "spring-projects/spring-boot",
            "dropwizard/dropwizard",
        },
        "java-enterprise-ecosystem",
    ),
    (
        {"spring-projects/spring-boot", "apache/kafka", "apache/logging-log4j2"},
        "java-enterprise-ecosystem",
    ),
    ({"apache/camel"}, "java-enterprise-ecosystem"),
    # Go HTTP (chi, hugo)
    ({"go-chi/chi", "gohugoio/hugo"}, "go-http-ecosystem"),
    # Web platforms (zulip, discourse, sentry, mattermost)
    ({"zulip/zulip"}, "zulip-platform"),
    ({"discourse/discourse"}, "discourse-platform"),
    ({"getsentry/sentry"}, "sentry-platform"),
    ({"mattermost/mattermost"}, "mattermost-platform"),
    # Angular/TypeScript
    ({"angular/angular"}, "angular-ecosystem"),
    ({"microsoft/TypeScript"}, "typescript-ecosystem"),
    # Keycloak
    ({"keycloak/keycloak"}, "keycloak-ecosystem"),
    # Harbor
    ({"goharbor/harbor"}, "harbor-ecosystem"),
    # Bitnami/Argo platform engineering
    ({"bitnami/charts"}, "helm-ecosystem"),
    ({"argoproj/argo-cd"}, "argocd-ecosystem"),
    # C/C++ systems
    ({"curl/curl", "git/git"}, "c-systems-ecosystem"),
    ({"gcc-mirror/gcc"}, "gcc-ecosystem"),
    ({"llvm/llvm-project"}, "llvm-ecosystem"),
    ({"ceph/ceph"}, "ceph-ecosystem"),
    # Ansible
    ({"ansible/ansible"}, "ansible-ecosystem"),
    # Docker/Moby
    ({"moby/moby"}, "docker-ecosystem"),
    # .NET
    ({"dotnet/aspnetcore"}, "dotnet-ecosystem"),
    # Apache Beam
    ({"apache/beam"}, "beam-ecosystem"),
    # Apache Kafka (standalone)
    ({"apache/kafka"}, "kafka-ecosystem"),
    # Apache Druid
    ({"apache/druid"}, "druid-ecosystem"),
    # Browser/desktop apps
    ({"mozilla/gecko-dev"}, "mozilla-ecosystem"),
    ({"LibreOffice/core"}, "libreoffice-ecosystem"),
    ({"qutebrowser/qutebrowser"}, "qutebrowser-ecosystem"),
    # Element/Matrix
    ({"element-hq/element-web"}, "matrix-ecosystem"),
    # NodeBB
    ({"NodeBB/NodeBB"}, "nodebb-ecosystem"),
]


def _extract_org_repo(url: str) -> str:
    """Extract org/repo from a URL like https://github.com/org/repo."""
    m = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else url


def _determine_repo_set_id(repo_urls: list[str]) -> str:
    """Determine repo_set_id from the set of repo URLs in a task."""
    org_repos = {_extract_org_repo(u) for u in repo_urls}

    # Try matching rules in order; pick the first rule where any repo matches
    best_match = ""
    best_overlap = 0
    for rule_repos, set_id in _REPO_SET_RULES:
        overlap = len(org_repos & rule_repos)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = set_id

    if best_match:
        return best_match

    # Fallback: use the primary repo's org as the ecosystem name
    if org_repos:
        first = sorted(org_repos)[0]
        org = first.split("/")[0]
        return f"{org.lower()}-ecosystem"

    return "unknown-ecosystem"


def _determine_org_scale(
    difficulty_stratum: str | None,
    difficulty: str | None,
    repo_count: int,
    total_loc: int | None,
) -> bool:
    """Determine if a task represents enterprise-scale complexity."""
    # Calibration tasks are NOT enterprise scale
    if difficulty_stratum == "calibration":
        return False
    # Multi-repo and monorepo tasks are enterprise scale
    if difficulty_stratum in ("multi_repo", "monorepo_cross_package", "tri_repo"):
        return True
    # Dual-repo is enterprise scale
    if difficulty_stratum == "dual_repo":
        return True
    # Large single repo with expert difficulty
    if difficulty_stratum == "large_single" and difficulty == "expert":
        return True
    # Large single repo with high LOC
    if difficulty_stratum == "large_single" and total_loc and total_loc >= 100_000:
        return True
    # Hard difficulty with large codebase
    if difficulty in ("hard", "expert") and total_loc and total_loc >= 100_000:
        return True
    # Default: false for calibration-like tasks, true for everything else that's hard+
    if difficulty in ("hard", "expert"):
        return True
    return False


def _determine_verification_modes(checkpoints: list[dict]) -> list[str]:
    """Determine verification modes from checkpoint verifier scripts."""
    modes: set[str] = set()
    for cp in checkpoints:
        verifier = cp.get("verifier", "")
        # All current tasks use shell-script verifiers = deterministic
        if verifier.endswith(".sh"):
            modes.add("deterministic")
        elif verifier.endswith(".py"):
            # Python verifiers might be LLM-based or structural
            modes.add("structural_match")
        else:
            modes.add("deterministic")

    if not modes:
        modes.add("deterministic")

    return sorted(modes)


def _read_task_toml(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_toml_value(content: str, key: str) -> str | None:
    """Simple TOML value extraction for top-level keys."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key} = ") or stripped.startswith(f"{key}="):
            # Extract the value after =
            _, _, val = stripped.partition("=")
            return val.strip().strip('"').strip("'")
    return None


def _parse_repos(content: str) -> list[str]:
    """Extract repo URLs from [[repos]] sections."""
    urls: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("url = "):
            val = stripped.split("=", 1)[1].strip().strip('"')
            urls.append(val)
    return urls


def _parse_task_field(content: str, field: str) -> str | None:
    """Extract a field from the [task] section."""
    in_task = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[task]":
            in_task = True
            continue
        if in_task:
            if stripped.startswith("[") and not stripped.startswith("[["):
                break
            if stripped.startswith(f"{field} = ") or stripped.startswith(f"{field}="):
                _, _, val = stripped.partition("=")
                return val.strip().strip('"').strip("'")
    return None


def _parse_metadata_loc(content: str) -> int | None:
    """Extract total_loc from [metadata] section."""
    in_metadata = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[metadata]":
            in_metadata = True
            continue
        if in_metadata:
            if stripped.startswith("[") and not stripped.startswith("[["):
                break
            if stripped.startswith("total_loc"):
                _, _, val = stripped.partition("=")
                val = val.strip().replace("_", "")
                try:
                    return int(val)
                except ValueError:
                    return None
    return None


def _parse_checkpoints(content: str) -> list[dict]:
    """Extract checkpoint verifier paths."""
    checkpoints: list[dict] = []
    current: dict | None = None
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[[checkpoints]]":
            if current is not None:
                checkpoints.append(current)
            current = {}
            continue
        if current is not None:
            if stripped.startswith("[") and stripped != "[[checkpoints]]":
                checkpoints.append(current)
                current = None
                continue
            if stripped.startswith("verifier = "):
                _, _, val = stripped.partition("=")
                current["verifier"] = val.strip().strip('"')
    if current is not None:
        checkpoints.append(current)
    return checkpoints


def _has_field(content: str, field: str) -> bool:
    """Check if a top-level field already exists."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{field} = ") or stripped.startswith(f"{field}="):
            # Make sure it's a top-level field (not inside a section that would
            # have the same name as a nested key)
            return True
    return False


def enrich_task(task_path: Path, *, dry_run: bool = False) -> dict[str, str]:
    """Add new fields to a task.toml file. Returns dict of field->value added."""
    content = _read_task_toml(task_path)
    additions: dict[str, str] = {}

    # Parse needed info
    difficulty_stratum = _parse_toml_value(content, "difficulty_stratum")
    difficulty = _parse_task_field(content, "difficulty")
    repo_urls = _parse_repos(content)
    total_loc = _parse_metadata_loc(content)
    checkpoints = _parse_checkpoints(content)

    # Determine values
    mcp_suite = "eb_v1"
    repo_set_id = _determine_repo_set_id(repo_urls)
    org_scale = _determine_org_scale(
        difficulty_stratum,
        difficulty,
        len(repo_urls),
        total_loc,
    )
    verification_modes = _determine_verification_modes(checkpoints)

    # Build lines to insert
    lines_to_add: list[str] = []

    if not _has_field(content, "mcp_suite"):
        lines_to_add.append(f'mcp_suite = "{mcp_suite}"')
        additions["mcp_suite"] = mcp_suite

    if not _has_field(content, "repo_set_id"):
        lines_to_add.append(f'repo_set_id = "{repo_set_id}"')
        additions["repo_set_id"] = repo_set_id

    if not _has_field(content, "org_scale"):
        lines_to_add.append(f"org_scale = {'true' if org_scale else 'false'}")
        additions["org_scale"] = str(org_scale).lower()

    if not _has_field(content, "verification_modes"):
        modes_str = ", ".join(f'"{m}"' for m in verification_modes)
        lines_to_add.append(f"verification_modes = [{modes_str}]")
        additions["verification_modes"] = str(verification_modes)

    if not lines_to_add:
        return additions

    if dry_run:
        return additions

    # Insert after difficulty_stratum line (or after the first comment block)
    output_lines = content.splitlines()
    insert_idx = 0

    # Find the best insertion point: after difficulty_stratum if present,
    # otherwise just before [task]
    for i, line in enumerate(output_lines):
        stripped = line.strip()
        if stripped.startswith("difficulty_stratum"):
            insert_idx = i + 1
            break
        if stripped == "[task]":
            insert_idx = i
            break

    # Insert the new lines
    for j, new_line in enumerate(lines_to_add):
        output_lines.insert(insert_idx + j, new_line)

    new_content = "\n".join(output_lines)
    if not new_content.endswith("\n"):
        new_content += "\n"

    task_path.write_text(new_content, encoding="utf-8")
    return additions


def main() -> None:
    root = Path(__file__).parent.parent
    benchmarks_dir = root / "benchmarks"

    dry_run = "--dry-run" in sys.argv

    task_files = sorted(benchmarks_dir.rglob("task.toml"))
    task_files = [
        f
        for f in task_files
        if f.relative_to(benchmarks_dir).parts[0] not in ("mined", "_archived")
        and "EXAMPLE" not in f.name
    ]

    print(f"Found {len(task_files)} task files")
    if dry_run:
        print("DRY RUN — no files will be modified")

    enriched = 0
    for tf in task_files:
        rel = tf.relative_to(benchmarks_dir)
        additions = enrich_task(tf, dry_run=dry_run)
        if additions:
            enriched += 1
            print(f"  {rel}: added {list(additions.keys())}")

    print(f"\nEnriched {enriched}/{len(task_files)} tasks")


if __name__ == "__main__":
    main()
