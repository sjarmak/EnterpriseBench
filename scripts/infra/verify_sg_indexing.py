#!/usr/bin/env python3
"""Verify Sourcegraph indexing status for EnterpriseBench repos.

Reads configs/sg_indexing_list.json and outputs a summary of indexing
status across all suites and repos.

Usage:
    python scripts/infra/verify_sg_indexing.py
    python scripts/infra/verify_sg_indexing.py --check-api
    python scripts/infra/verify_sg_indexing.py --json
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_INDEX_PATH = os.path.join(ROOT, "configs", "sg_indexing_list.json")


@dataclass(frozen=True)
class RepoStatus:
    name: str
    url: str
    indexed: bool


@dataclass(frozen=True)
class SuiteStatus:
    name: str
    repos: tuple[RepoStatus, ...]
    total: int
    indexed: int
    pending: int


@dataclass(frozen=True)
class IndexingSummary:
    total_repos: int
    indexed_count: int
    pending_count: int
    suites: tuple[SuiteStatus, ...]


def load_index(path: str) -> dict[str, Any]:
    """Load the indexing list JSON file."""
    with open(path) as f:
        return json.load(f)


def compute_summary(data: dict[str, Any]) -> IndexingSummary:
    """Compute indexing summary from the loaded JSON data."""
    # Count from flat repos array
    all_repos = data.get("repos", [])
    total = len(all_repos)
    indexed = sum(1 for r in all_repos if r.get("_indexed", False))
    pending = total - indexed

    # Per-suite breakdown
    suites_data = data.get("suites", {})
    suite_statuses: list[SuiteStatus] = []

    for suite_name in sorted(suites_data.keys()):
        suite = suites_data[suite_name]
        suite_repos_raw = suite.get("repos", [])
        repo_statuses = tuple(
            RepoStatus(
                name=r["name"],
                url=r["url"],
                indexed=r.get("_indexed", False),
            )
            for r in suite_repos_raw
        )
        suite_total = len(repo_statuses)
        suite_indexed = sum(1 for r in repo_statuses if r.indexed)
        suite_statuses.append(
            SuiteStatus(
                name=suite_name,
                repos=repo_statuses,
                total=suite_total,
                indexed=suite_indexed,
                pending=suite_total - suite_indexed,
            )
        )

    return IndexingSummary(
        total_repos=total,
        indexed_count=indexed,
        pending_count=pending,
        suites=tuple(suite_statuses),
    )


def format_summary(summary: IndexingSummary) -> str:
    """Format the summary as human-readable text."""
    lines: list[str] = []
    lines.append("=== Sourcegraph Indexing Status ===")
    lines.append("")
    lines.append(f"Total repos:   {summary.total_repos}")
    lines.append(f"Indexed:       {summary.indexed_count}")
    lines.append(f"Pending:       {summary.pending_count}")
    lines.append("")
    lines.append("--- Per-Suite Breakdown ---")

    for suite in summary.suites:
        lines.append(
            f"  {suite.name}: {suite.indexed}/{suite.total} indexed, {suite.pending} pending"
        )

    lines.append("")
    return "\n".join(lines)


def format_json(summary: IndexingSummary) -> str:
    """Format the summary as JSON."""
    result = {
        "total_repos": summary.total_repos,
        "indexed_count": summary.indexed_count,
        "pending_count": summary.pending_count,
        "suites": {
            s.name: {
                "total": s.total,
                "indexed": s.indexed,
                "pending": s.pending,
                "repos": [{"name": r.name, "indexed": r.indexed} for r in s.repos],
            }
            for s in summary.suites
        },
    }
    return json.dumps(result, indent=2)


def check_api_stub() -> None:
    """Stub for future Sourcegraph API verification."""
    print("[stub] --check-api: Sourcegraph API verification not yet implemented.")
    print("[stub] This will verify each repo is indexed on the SG instance.")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Verify Sourcegraph indexing status for EnterpriseBench repos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/infra/verify_sg_indexing.py\n"
            "  python scripts/infra/verify_sg_indexing.py --json\n"
            "  python scripts/infra/verify_sg_indexing.py --check-api\n"
        ),
    )
    parser.add_argument(
        "--index-path",
        default=DEFAULT_INDEX_PATH,
        help="Path to sg_indexing_list.json (default: configs/sg_indexing_list.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output summary as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--check-api",
        action="store_true",
        help="Check indexing status against Sourcegraph API (not yet implemented)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not os.path.exists(args.index_path):
        print(f"Error: Index file not found: {args.index_path}", file=sys.stderr)
        return 1

    data = load_index(args.index_path)
    summary = compute_summary(data)

    if args.output_json:
        print(format_json(summary))
    else:
        print(format_summary(summary))

    if args.check_api:
        check_api_stub()

    return 0


if __name__ == "__main__":
    sys.exit(main())
