#!/usr/bin/env python3
"""Generate configs/sg_indexing_list.json from configs/sg_mirrors/ and benchmarks/.

Consolidates all per-task mirror files into a single centralized repo index
with per-repo metadata and cross-references.

Usage:
    python scripts/generate_sg_index.py
"""

import json
import glob
import os
from collections import defaultdict
from datetime import date
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRRORS_DIR = os.path.join(ROOT, "configs", "sg_mirrors")
BENCHMARKS_DIR = os.path.join(ROOT, "benchmarks")
OUTPUT_PATH = os.path.join(ROOT, "configs", "sg_indexing_list.json")

# Language heuristics keyed by org/repo (without version suffix).
# Every repo in the index must have an entry here.
LANGUAGE_HINTS: dict[str, str] = {
    "FasterXML/jackson-databind": "Java",
    "LibreOffice/core": "C++",
    "NodeBB/NodeBB": "JavaScript",
    "angular/angular": "TypeScript",
    "ansible/ansible": "Python",
    "apache/beam": "Java/Python",
    "apache/camel": "Java",
    "apache/druid": "Java",
    "apache/kafka": "Java/Scala",
    "apache/logging-log4j2": "Java",
    "argoproj/argo-cd": "Go",
    "aws/aws-cli": "Python",
    "axios/axios": "JavaScript",
    "babel/babel": "JavaScript",
    "bitnami/charts": "YAML/Helm",
    "boto/boto3": "Python",
    "ceph/ceph": "C++",
    "curl/curl": "C",
    "discourse/discourse": "Ruby",
    "django/django": "Python",
    "dotnet/aspnetcore": "C#",
    "dropwizard/dropwizard": "Java",
    "element-hq/element-web": "TypeScript",
    "envoyproxy/envoy": "C++",
    "envoyproxy/go-control-plane": "Go",
    "eslint/eslint": "JavaScript",
    "etcd-io/etcd": "Go",
    "facebook/react": "JavaScript",
    "gcc-mirror/gcc": "C/C++",
    "getsentry/sentry": "Python",
    "gin-gonic/gin": "Go",
    "git/git": "C",
    "go-chi/chi": "Go",
    "goharbor/harbor": "Go",
    "gohugoio/hugo": "Go",
    "grafana/grafana": "Go/TypeScript",
    "grpc-ecosystem/go-grpc-middleware": "Go",
    "grpc/grpc-go": "Go",
    "grpc/grpc-node": "TypeScript",
    "hashicorp/consul": "Go",
    "hashicorp/terraform": "Go",
    "hashicorp/vault": "Go",
    "istio/istio": "Go",
    "jestjs/jest": "JavaScript",
    "keycloak/keycloak": "Java",
    "kubernetes-client/javascript": "TypeScript",
    "kubernetes/kubernetes": "Go",
    "llvm/llvm-project": "C++",
    "lodash/lodash": "JavaScript",
    "mattermost/mattermost": "Go",
    "microsoft/TypeScript": "TypeScript",
    "moby/moby": "Go",
    "mozilla/gecko-dev": "C++/Rust",
    "pallets/click": "Python",
    "pallets/flask": "Python",
    "pnpm/pnpm": "TypeScript",
    "projectcalico/calico": "Go",
    "prometheus/prometheus": "Go",
    "protocolbuffers/protobuf-go": "Go",
    "psf/requests": "Python",
    "qutebrowser/qutebrowser": "Python",
    "rust-lang/rust": "Rust",
    "spf13/cobra": "Go",
    "spring-projects/spring-boot": "Java",
    "stripe/stripe-go": "Go",
    "typescript-eslint/typescript-eslint": "TypeScript",
    "unknown/repo": "Unknown",
    "urllib3/urllib3": "Python",
    "vercel/next.js": "TypeScript",
    "webpack/webpack": "JavaScript",
    "zulip/zulip": "Python",
}

# Approximate LOC estimates for each repo.
# Sources: GitHub language stats, cloc estimates from public analyses, and
# well-known project size data. These are order-of-magnitude estimates for
# tier classification; precision beyond 10% is not required.
LOC_HINTS: dict[str, int] = {
    "FasterXML/jackson-databind": 120_000,
    "LibreOffice/core": 9_500_000,
    "NodeBB/NodeBB": 150_000,
    "angular/angular": 700_000,
    "ansible/ansible": 600_000,
    "apache/beam": 1_200_000,
    "apache/camel": 2_000_000,
    "apache/druid": 600_000,
    "apache/kafka": 800_000,
    "apache/logging-log4j2": 250_000,
    "argoproj/argo-cd": 300_000,
    "aws/aws-cli": 400_000,
    "axios/axios": 15_000,
    "babel/babel": 200_000,
    "bitnami/charts": 300_000,
    "boto/boto3": 100_000,
    "ceph/ceph": 2_500_000,
    "curl/curl": 250_000,
    "discourse/discourse": 350_000,
    "django/django": 350_000,
    "dotnet/aspnetcore": 1_500_000,
    "dropwizard/dropwizard": 120_000,
    "element-hq/element-web": 200_000,
    "envoyproxy/envoy": 800_000,
    "envoyproxy/go-control-plane": 80_000,
    "eslint/eslint": 120_000,
    "etcd-io/etcd": 300_000,
    "facebook/react": 250_000,
    "gcc-mirror/gcc": 12_000_000,
    "getsentry/sentry": 500_000,
    "gin-gonic/gin": 20_000,
    "git/git": 400_000,
    "go-chi/chi": 5_000,
    "goharbor/harbor": 200_000,
    "gohugoio/hugo": 150_000,
    "grafana/grafana": 1_800_000,
    "grpc-ecosystem/go-grpc-middleware": 15_000,
    "grpc/grpc-go": 200_000,
    "grpc/grpc-node": 100_000,
    "hashicorp/consul": 500_000,
    "hashicorp/terraform": 500_000,
    "hashicorp/vault": 600_000,
    "istio/istio": 500_000,
    "jestjs/jest": 150_000,
    "keycloak/keycloak": 700_000,
    "kubernetes-client/javascript": 80_000,
    "kubernetes/kubernetes": 3_500_000,
    "llvm/llvm-project": 8_000_000,
    "lodash/lodash": 30_000,
    "mattermost/mattermost": 500_000,
    "microsoft/TypeScript": 400_000,
    "moby/moby": 500_000,
    "mozilla/gecko-dev": 15_000_000,
    "pallets/click": 25_000,
    "pallets/flask": 15_000,
    "pnpm/pnpm": 200_000,
    "projectcalico/calico": 300_000,
    "prometheus/prometheus": 250_000,
    "protocolbuffers/protobuf-go": 100_000,
    "psf/requests": 15_000,
    "qutebrowser/qutebrowser": 100_000,
    "rust-lang/rust": 5_000_000,
    "spf13/cobra": 10_000,
    "spring-projects/spring-boot": 350_000,
    "stripe/stripe-go": 80_000,
    "typescript-eslint/typescript-eslint": 150_000,
    "unknown/repo": 10_000,
    "urllib3/urllib3": 20_000,
    "vercel/next.js": 400_000,
    "webpack/webpack": 150_000,
    "zulip/zulip": 350_000,
}


def compute_tier(loc: int) -> str:
    """Classify repo tier based on LOC estimate.

    A = >500K LOC (very large/complex)
    B = 100K-500K LOC (large)
    C = <100K LOC (medium)
    """
    if loc > 500_000:
        return "A"
    if loc >= 100_000:
        return "B"
    return "C"


def load_mirrors() -> dict[str, Any]:
    """Load all per-task mirror definitions."""
    mirrors: dict[str, Any] = {}
    for path in sorted(glob.glob(os.path.join(MIRRORS_DIR, "*.json"))):
        with open(path) as f:
            data = json.load(f)
        mirrors[data["task_id"]] = data
    return mirrors


def load_task_suites() -> dict[str, str]:
    """Map task_id -> suite from benchmarks directory structure."""
    task_suites: dict[str, str] = {}
    for toml_path in glob.glob(os.path.join(BENCHMARKS_DIR, "*/*/task.toml")):
        parts = toml_path.split(os.sep)
        idx = parts.index("benchmarks")
        suite = parts[idx + 1]
        task_id = parts[idx + 2]
        if suite.startswith("_"):
            continue
        task_suites[task_id] = suite
    return task_suites


def build_index(mirrors: dict[str, Any], task_suites: dict[str, str]) -> dict[str, Any]:
    """Build the consolidated index structure."""
    # Collect unique repos and their task usage
    repo_tasks: dict[str, list[str]] = defaultdict(list)
    repo_info: dict[str, dict[str, str]] = {}

    for task_id, mirror_data in mirrors.items():
        for m in mirror_data.get("mirrors", []):
            mid = m["mirror_id"]
            repo_tasks[mid].append(task_id)
            if mid not in repo_info:
                repo_info[mid] = {
                    "repo": m["repo"],
                    "rev": m["rev"],
                }

    # Determine suites per repo
    repo_suites: dict[str, set[str]] = defaultdict(set)
    for mid, tasks in repo_tasks.items():
        for tid in tasks:
            suite = task_suites.get(tid)
            if suite:
                repo_suites[mid].add(suite)

    # Build per-suite summaries
    suite_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"repos": 0, "tasks": 0}
    )
    for mid, suites in repo_suites.items():
        for s in suites:
            suite_stats[s]["repos"] += 1
    for tid, suite in task_suites.items():
        if tid in mirrors:
            suite_stats[suite]["tasks"] += 1

    # Build flat repo list (sorted by sg_name for determinism)
    repos_list: list[dict[str, Any]] = []
    for mid in sorted(repo_info.keys()):
        info = repo_info[mid]
        github_repo = info["repo"].replace("github.com/", "")

        entry: dict[str, Any] = {
            "sg_name": f"sg-evals/{mid}",
            "github_repo": github_repo,
            "commit": info["rev"],
        }

        lang = LANGUAGE_HINTS.get(github_repo)
        if lang:
            entry["_language"] = lang

        loc = LOC_HINTS.get(github_repo)
        if loc:
            entry["_loc_estimate"] = loc
            entry["_tier"] = compute_tier(loc)

        entry["_indexed"] = False
        entry["_task_count"] = len(repo_tasks[mid])

        suites = sorted(repo_suites.get(mid, []))
        if suites:
            entry["_suites"] = suites

        repos_list.append(entry)

    # Build per-suite repo lists from the flat repos list
    suite_repo_entries: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in repos_list:
        github_repo = entry["github_repo"]
        for s in entry.get("_suites", []):
            suite_repo_entries[s].append(
                {
                    "name": github_repo,
                    "url": f"https://github.com/{github_repo}",
                    "_indexed": entry.get("_indexed", False),
                }
            )

    # Build suite summary section
    suites_summary: dict[str, Any] = {}
    for suite_name in sorted(suite_stats.keys()):
        stats = suite_stats[suite_name]
        suite_repos = suite_repo_entries.get(suite_name, [])
        indexed_count = sum(1 for r in suite_repos if r["_indexed"])
        suites_summary[suite_name] = {
            "_status": "pending_verification",
            "_indexed_count": indexed_count,
            "_repo_count": stats["repos"],
            "_task_count": stats["tasks"],
            "repos": suite_repos,
        }

    index: dict[str, Any] = {
        "_description": (
            "Centralized repo index for EnterpriseBench. "
            "Consolidates configs/sg_mirrors/ into a single index. "
            "Each entry maps an sg-evals mirror name to its source GitHub repo, "
            "pinned commit, and metadata."
        ),
        "_generated": str(date.today()),
        "_total_unique_repos": len(repo_info),
        "_total_mirror_files": len(mirrors),
        "suites": suites_summary,
        "repos": repos_list,
    }

    return index


def main() -> None:
    mirrors = load_mirrors()
    task_suites = load_task_suites()
    index = build_index(mirrors, task_suites)

    with open(OUTPUT_PATH, "w") as f:
        json.dump(index, f, indent=2)
        f.write("\n")

    print(f"Generated {OUTPUT_PATH}")
    print(f"  Total unique repos: {index['_total_unique_repos']}")
    print(f"  Total mirror files: {index['_total_mirror_files']}")
    print(f"  Suites:")
    for name, info in index["suites"].items():
        print(f"    {name}: {info['_repo_count']} repos, {info['_task_count']} tasks")


if __name__ == "__main__":
    main()
