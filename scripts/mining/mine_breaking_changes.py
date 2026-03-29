#!/usr/bin/env python3
"""
mine_breaking_changes.py — Discover breaking changes in OSS dependency chains.

This script searches for breaking changes in known dependency chains by:
1. Querying GitHub releases/tags for major version bumps
2. Searching issue trackers for "breaking change" mentions
3. Cross-referencing downstream repos for fix commits

Usage:
    python mine_breaking_changes.py --chain <chain_name> [--github-token <token>]

Chains supported:
    grpc-go-etcd        — grpc-go breaking changes affecting etcd
    urllib3-requests     — urllib3 2.0 breaking changes affecting requests/boto
    eslint-typescript    — ESLint major version breaking typescript-eslint

Requires: PyGithub (pip install PyGithub)

This is a semi-automated tool. It produces candidate breaking changes that
must be manually validated by extract_task.py and validate_candidate.py.
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from typing import Optional

# Try to import github; fall back to manual mode if unavailable
try:
    from github import Github
    HAS_GITHUB = True
except ImportError:
    HAS_GITHUB = False


@dataclass
class BreakingChangeCandidate:
    """A candidate breaking change discovered from OSS history."""
    chain_name: str
    upstream_repo: str
    upstream_breaking_version: str
    upstream_previous_version: str
    downstream_repo: str
    downstream_affected_version: str  # version before fix
    downstream_fix_version: str       # version with fix
    fix_pr_url: Optional[str]
    fix_commit: Optional[str]
    issue_url: Optional[str]
    description: str
    breaking_api_changes: list[str]
    affected_files: list[str]
    confidence: str  # "high", "medium", "low"
    notes: str


# Known breaking change database — curated from manual research.
# This is the core knowledge base that drives the mining pipeline.
# Each entry represents a verified historical breaking change.
KNOWN_CHAINS = {
    "grpc-go-etcd": [
        BreakingChangeCandidate(
            chain_name="grpc-go-etcd",
            upstream_repo="github.com/grpc/grpc-go",
            upstream_breaking_version="v1.27.0",
            upstream_previous_version="v1.26.0",
            downstream_repo="github.com/etcd-io/etcd",
            downstream_affected_version="v3.4.7",
            downstream_fix_version="v3.4.8",
            fix_pr_url="https://github.com/etcd-io/etcd/pull/11564",
            fix_commit="4258cdd2efdf79a145067ae426f93b9f220c05f1",
            issue_url="https://github.com/etcd-io/etcd/issues/11563",
            description="grpc-go v1.27.0 removed backward-compat type aliases for balancer/resolver APIs, breaking etcd clientv3",
            breaking_api_changes=[
                "resolver.BuildOption removed (was deprecated alias)",
                "resolver.ResolveNowOption removed (was deprecated alias)",
                "balancer.PickOptions removed (was deprecated alias)",
            ],
            affected_files=[
                "clientv3/balancer/resolver/endpoint/endpoint.go",
                "clientv3/balancer/picker/err.go",
                "clientv3/balancer/picker/roundrobin_balanced.go",
                "clientv3/balancer/utils.go",
            ],
            confidence="high",
            notes="Well-documented breaking change. Fix is self-contained in 4 files. "
                  "Good benchmark candidate: clear problem, verifiable fix, medium difficulty.",
        ),
        BreakingChangeCandidate(
            chain_name="grpc-go-etcd",
            upstream_repo="github.com/grpc/grpc-go",
            upstream_breaking_version="v1.32.0",
            upstream_previous_version="v1.31.1",
            downstream_repo="github.com/etcd-io/etcd",
            downstream_affected_version="v3.4.13",
            downstream_fix_version="v3.5.0",
            fix_pr_url="https://github.com/etcd-io/etcd/pull/12671",
            fix_commit=None,
            issue_url="https://github.com/etcd-io/etcd/pull/12398",
            description="grpc-go v1.32.0 removed naming interface support, requiring etcd to replace custom balancer with upstream grpc solution",
            breaking_api_changes=[
                "naming interface removed from grpc-go",
                "Custom balancer API incompatible",
            ],
            affected_files=[
                "clientv3/balancer/ (entire package replaced)",
            ],
            confidence="medium",
            notes="Large refactor — replaced entire custom balancer with upstream grpc solution. "
                  "May be too complex for a single benchmark task (expert-level). "
                  "PR #12398 was closed in favor of #12671 which did the full rewrite.",
        ),
    ],
    "urllib3-requests": [
        BreakingChangeCandidate(
            chain_name="urllib3-requests",
            upstream_repo="github.com/urllib3/urllib3",
            upstream_breaking_version="2.0.0",
            upstream_previous_version="1.26.18",
            downstream_repo="github.com/psf/requests",
            downstream_affected_version="v2.28.2",
            downstream_fix_version="v2.30.0",
            fix_pr_url=None,  # Multiple PRs contributed
            fix_commit="2ad18e0e10e7d7ecd5384c378f25ec8821a10a29",
            issue_url="https://github.com/psf/requests/issues/6432",
            description="urllib3 2.0.0 major version bump broke requests version pin (urllib3<1.27). "
                       "Required updating version constraints and adapting to urllib3 2.0 API changes.",
            breaking_api_changes=[
                "Version pin urllib3<1.27 excluded urllib3 2.0.0",
                "urllib3 2.0 dropped Python 3.6 support",
                "urllib3 2.0 removed deprecated APIs (e.g., Retry.DEFAULT_REDIRECT)",
                "urllib3 2.0 changed SSL/TLS defaults (requires OpenSSL 1.1.1+)",
            ],
            affected_files=[
                "setup.cfg (version pin)",
                "requests/adapters.py",
                "requests/compat.py",
                "requests/models.py",
            ],
            confidence="high",
            notes="Well-documented ecosystem-wide breakage. The version pin change is simple, "
                  "but the full adaptation involves handling API deprecations. "
                  "Good for a dependency_management task.",
        ),
        BreakingChangeCandidate(
            chain_name="urllib3-requests-botocore",
            upstream_repo="github.com/urllib3/urllib3",
            upstream_breaking_version="2.0.0",
            upstream_previous_version="1.26.18",
            downstream_repo="github.com/boto/botocore",
            downstream_affected_version="1.29.0",
            downstream_fix_version="1.34.0",
            fix_pr_url="https://github.com/boto/botocore/issues/2926",
            fix_commit=None,
            issue_url="https://github.com/boto/botocore/issues/2926",
            description="botocore vendored urllib3 and had hard pin urllib3<1.27. "
                       "urllib3 2.0 required de-vendoring and adapting to new API.",
            breaking_api_changes=[
                "Vendored urllib3 copy incompatible with urllib3 2.0",
                "Version pin urllib3>=1.25.4,<1.27 blocked upgrade",
                "SSL context changes in urllib3 2.0",
            ],
            affected_files=[
                "setup.py (version constraints)",
                "botocore/httpsession.py",
                "botocore/vendored/ (de-vendoring)",
            ],
            confidence="medium",
            notes="Complex multi-step fix: de-vendoring + API adaptation. "
                  "Took botocore many months to fully resolve. "
                  "May be too broad for a single task unless scoped carefully.",
        ),
    ],
    "eslint-typescript": [
        BreakingChangeCandidate(
            chain_name="eslint-typescript",
            upstream_repo="github.com/eslint/eslint",
            upstream_breaking_version="v10.0.0",
            upstream_previous_version="v9.17.0",
            downstream_repo="github.com/typescript-eslint/typescript-eslint",
            downstream_affected_version="v8.49.0",
            downstream_fix_version="v8.50.0",  # approximate
            fix_pr_url="https://github.com/typescript-eslint/typescript-eslint/pull/11914",
            fix_commit="607c9c9f3fd82f51124094ce944f55204a78ebe5",
            issue_url="https://github.com/typescript-eslint/typescript-eslint/issues/11762",
            description="ESLint v10 requires ScopeManager to implement addGlobals() method. "
                       "typescript-eslint scope manager lacked this, causing crash before any rules run.",
            breaking_api_changes=[
                "ScopeManager must implement addGlobals(names: string[]) method",
                "Reference resolution for global variables shifted to ScopeManager",
                "eslint-scope v9.0.0 implements these changes; custom scope managers must follow",
            ],
            affected_files=[
                "packages/scope-manager/src/ScopeManager.ts",
                "packages/scope-manager/src/scope/GlobalScope.ts",
                "packages/scope-manager/src/scope/ScopeBase.ts",
            ],
            confidence="high",
            notes="Clean, well-scoped fix. Porting addGlobals from eslint-scope to "
                  "typescript-eslint scope manager. Good benchmark candidate: "
                  "clear problem, focused fix, requires understanding scope manager internals.",
        ),
    ],
}


def search_github_releases(repo_name: str, keywords: list[str], token: Optional[str] = None):
    """Search GitHub releases for breaking change mentions.

    This is the automated discovery path. For the prototype, we rely on
    the curated KNOWN_CHAINS database above, but this function shows how
    automated discovery would work at scale.
    """
    if not HAS_GITHUB:
        print("PyGithub not installed. Using curated database only.")
        print("Install with: pip install PyGithub")
        return []

    g = Github(token) if token else Github()
    repo = g.get_repo(repo_name)
    candidates = []

    for release in repo.get_releases():
        body = (release.body or "").lower()
        if any(kw.lower() in body for kw in keywords):
            candidates.append({
                "tag": release.tag_name,
                "title": release.title,
                "url": release.html_url,
                "date": release.published_at.isoformat() if release.published_at else None,
                "matching_keywords": [kw for kw in keywords if kw.lower() in body],
            })

    return candidates


def search_downstream_issues(repo_name: str, upstream_name: str, token: Optional[str] = None):
    """Search downstream repo issues for references to upstream breakage.

    Looks for issues mentioning the upstream repo name + keywords like
    'breaking', 'incompatible', 'upgrade', 'migration'.
    """
    if not HAS_GITHUB:
        print("PyGithub not installed. Using curated database only.")
        return []

    g = Github(token) if token else Github()
    repo = g.get_repo(repo_name)

    short_name = upstream_name.split("/")[-1]
    query = f"repo:{repo_name} {short_name} breaking OR incompatible OR upgrade"

    issues = g.search_issues(query)
    candidates = []
    for issue in issues[:20]:  # Limit to top 20
        candidates.append({
            "number": issue.number,
            "title": issue.title,
            "url": issue.html_url,
            "state": issue.state,
            "created_at": issue.created_at.isoformat(),
        })

    return candidates


def get_candidates(chain_name: str) -> list[BreakingChangeCandidate]:
    """Get breaking change candidates for a dependency chain."""
    if chain_name == "all":
        all_candidates = []
        for candidates in KNOWN_CHAINS.values():
            all_candidates.extend(candidates)
        return all_candidates

    if chain_name not in KNOWN_CHAINS:
        print(f"Unknown chain: {chain_name}")
        print(f"Available chains: {', '.join(KNOWN_CHAINS.keys())}")
        sys.exit(1)

    return KNOWN_CHAINS[chain_name]


def main():
    parser = argparse.ArgumentParser(
        description="Discover breaking changes in OSS dependency chains"
    )
    parser.add_argument(
        "--chain",
        choices=list(KNOWN_CHAINS.keys()) + ["all"],
        default="all",
        help="Dependency chain to investigate",
    )
    parser.add_argument(
        "--github-token",
        help="GitHub API token for automated search (optional)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file for candidates (JSON)",
    )
    parser.add_argument(
        "--search",
        action="store_true",
        help="Run automated GitHub search (requires PyGithub + token)",
    )
    args = parser.parse_args()

    candidates = get_candidates(args.chain)

    if args.search:
        print("=== Automated GitHub Search ===")
        # Example: search grpc-go releases for breaking changes
        if args.chain in ("grpc-go-etcd", "all"):
            results = search_github_releases(
                "grpc/grpc-go",
                ["breaking", "incompatible", "removed", "deprecated"],
                args.github_token,
            )
            print(f"Found {len(results)} release candidates in grpc/grpc-go")
            for r in results[:5]:
                print(f"  - {r['tag']}: {r['title']} ({', '.join(r['matching_keywords'])})")

    print(f"\n=== Curated Candidates ({args.chain}) ===")
    print(f"Found {len(candidates)} candidates\n")

    for i, c in enumerate(candidates, 1):
        print(f"--- Candidate {i}: {c.description[:80]} ---")
        print(f"  Chain:      {c.chain_name}")
        print(f"  Upstream:   {c.upstream_repo} {c.upstream_previous_version} -> {c.upstream_breaking_version}")
        print(f"  Downstream: {c.downstream_repo} {c.downstream_affected_version} -> {c.downstream_fix_version}")
        print(f"  Confidence: {c.confidence}")
        print(f"  Issue:      {c.issue_url}")
        print(f"  Fix PR:     {c.fix_pr_url}")
        print(f"  Files:      {', '.join(c.affected_files[:3])}")
        print(f"  Notes:      {c.notes[:100]}")
        print()

    if args.output:
        with open(args.output, "w") as f:
            json.dump([asdict(c) for c in candidates], f, indent=2)
        print(f"Wrote {len(candidates)} candidates to {args.output}")

    # Summary statistics
    high = sum(1 for c in candidates if c.confidence == "high")
    medium = sum(1 for c in candidates if c.confidence == "medium")
    low = sum(1 for c in candidates if c.confidence == "low")
    print(f"\n=== Summary ===")
    print(f"Total candidates: {len(candidates)}")
    print(f"  High confidence:   {high}")
    print(f"  Medium confidence: {medium}")
    print(f"  Low confidence:    {low}")
    print(f"  Viable for tasks:  {high} (high confidence candidates)")


if __name__ == "__main__":
    main()
