#!/usr/bin/env python3
"""Check repo_versions.json for repos with stale last_verified dates.

Usage:
    python scripts/infra/check_repo_staleness.py           # human-readable output
    python scripts/infra/check_repo_staleness.py --json     # machine-readable JSON
"""

import argparse
import json
import pathlib
import sys
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "configs" / "repo_versions.json"
STALENESS_THRESHOLD_DAYS = 183  # ~6 months


def load_manifest(path: pathlib.Path) -> list[dict]:
    """Load the repo versions manifest from disk."""
    with open(path) as f:
        return json.load(f)


def check_staleness(
    entries: list[dict],
    today: date | None = None,
    threshold_days: int = STALENESS_THRESHOLD_DAYS,
) -> list[dict]:
    """Return entries whose last_verified date is older than threshold_days.

    Args:
        entries: List of repo version dicts with 'last_verified' ISO date strings.
        today: Reference date for staleness check (defaults to today).
        threshold_days: Number of days after which a repo is considered stale.

    Returns:
        List of stale entry dicts, each augmented with 'days_since_verified'.
    """
    if today is None:
        today = date.today()

    cutoff = today - timedelta(days=threshold_days)
    stale = []

    for entry in entries:
        last_verified = date.fromisoformat(entry["last_verified"])
        if last_verified <= cutoff:
            stale.append(
                {
                    **entry,
                    "days_since_verified": (today - last_verified).days,
                }
            )

    return sorted(stale, key=lambda e: e["days_since_verified"], reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for stale repo versions in the manifest."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--manifest",
        type=pathlib.Path,
        default=DEFAULT_MANIFEST,
        help=f"Path to repo_versions.json (default: {DEFAULT_MANIFEST})",
    )
    parser.add_argument(
        "--threshold-days",
        type=int,
        default=STALENESS_THRESHOLD_DAYS,
        help=f"Days before a repo is considered stale (default: {STALENESS_THRESHOLD_DAYS})",
    )
    args = parser.parse_args()

    entries = load_manifest(args.manifest)
    stale = check_staleness(entries, threshold_days=args.threshold_days)

    if args.json_output:
        json.dump(
            {"stale_count": len(stale), "total_count": len(entries), "stale": stale},
            sys.stdout,
            indent=2,
        )
        print()
        return 1 if stale else 0

    if not stale:
        print(
            f"All {len(entries)} repos are up to date (verified within {args.threshold_days} days)."
        )
        return 0

    print(
        f"WARNING: {len(stale)} of {len(entries)} repos are stale (>{args.threshold_days} days since verification):\n"
    )
    for entry in stale:
        print(f"  {entry['url']} @ {entry['pinned_rev']}")
        print(
            f"    Last verified: {entry['last_verified']} ({entry['days_since_verified']} days ago)\n"
        )

    return 1


if __name__ == "__main__":
    sys.exit(main())
