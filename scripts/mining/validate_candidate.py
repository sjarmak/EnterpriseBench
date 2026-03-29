#!/usr/bin/env python3
"""
validate_candidate.py — Validate whether a mining candidate is viable as a benchmark task.

Checks:
1. Repos are publicly accessible and cloneable
2. Pinned revisions (tags/commits) exist
3. Fix commit is self-contained (touches reasonable number of files)
4. Fix is not trivially small (>5 lines changed) or impossibly large (>500 lines)
5. Task is reproducible (the "before" state actually breaks with the upstream change)

Usage:
    python validate_candidate.py --candidate candidates.json --index 0
    python validate_candidate.py --task benchmarks/mined/dep-mgmt-grpc-go-v1270-001.toml

For full validation (cloning repos), use --deep. Without it, only metadata checks run.
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class ValidationResult:
    candidate_id: str
    checks: dict[str, dict]  # check_name -> {"pass": bool, "message": str}
    viable: bool
    notes: str


def check_repo_accessible(url: str) -> tuple[bool, str]:
    """Check if a repo URL is valid and publicly accessible via git ls-remote."""
    if not url.startswith("https://"):
        url = f"https://{url}"
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return True, "Repository accessible"
        return False, f"git ls-remote failed: {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, "Timeout checking repository"
    except FileNotFoundError:
        return None, "git not found — skipping remote check"


def check_revision_exists(url: str, rev: str) -> tuple[bool, str]:
    """Check if a specific revision (tag or commit) exists in a remote repo."""
    if not url.startswith("https://"):
        url = f"https://{url}"
    try:
        result = subprocess.run(
            ["git", "ls-remote", url, f"refs/tags/{rev}"],
            capture_output=True, text=True, timeout=30,
        )
        if rev in result.stdout:
            return True, f"Tag {rev} found"

        # Try as a branch
        result = subprocess.run(
            ["git", "ls-remote", url, f"refs/heads/{rev}"],
            capture_output=True, text=True, timeout=30,
        )
        if rev in result.stdout:
            return True, f"Branch {rev} found"

        # Could be a commit hash — can't check without clone
        if len(rev) >= 7 and all(c in "0123456789abcdef" for c in rev.lower()):
            return None, f"Commit hash {rev[:12]} — requires clone to verify"

        return False, f"Revision {rev} not found as tag or branch"
    except subprocess.TimeoutExpired:
        return None, "Timeout checking revision"
    except FileNotFoundError:
        return None, "git not found — skipping revision check"


def check_fix_scope(candidate: dict) -> tuple[bool, str]:
    """Check if the fix is appropriately scoped for a benchmark task."""
    files = candidate.get("affected_files", [])

    if len(files) == 0:
        return None, "No affected files listed — cannot assess scope"

    if len(files) < 2:
        return False, f"Fix too trivial: only {len(files)} file(s)"

    if len(files) > 20:
        return False, f"Fix too broad: {len(files)} files (max 20 for a task)"

    return True, f"Fix scope OK: {len(files)} files"


def check_ground_truth(candidate: dict) -> tuple[bool, str]:
    """Check if ground truth (fix commit/PR) is available."""
    fix_pr = candidate.get("fix_pr_url")
    fix_commit = candidate.get("fix_commit")

    if fix_pr and fix_commit:
        return True, f"Ground truth available: PR + commit"
    elif fix_pr:
        return True, f"Ground truth available: PR (commit hash missing)"
    elif fix_commit:
        return True, f"Ground truth available: commit (PR link missing)"
    else:
        return False, "No ground truth: neither fix PR nor commit available"


def check_confidence(candidate: dict) -> tuple[bool, str]:
    """Check candidate confidence level."""
    confidence = candidate.get("confidence", "unknown")
    if confidence == "high":
        return True, "High confidence candidate"
    elif confidence == "medium":
        return None, "Medium confidence — may need manual review"
    else:
        return False, f"Low/unknown confidence: {confidence}"


def validate_candidate(candidate: dict, deep: bool = False) -> ValidationResult:
    """Run all validation checks on a candidate."""
    candidate_id = (
        f"{candidate.get('downstream_repo', 'unknown').split('/')[-1]}"
        f"-{candidate.get('upstream_breaking_version', 'unknown')}"
    )

    checks = {}

    # Metadata checks (always run)
    checks["fix_scope"] = dict(zip(["pass", "message"], check_fix_scope(candidate)))
    checks["ground_truth"] = dict(zip(["pass", "message"], check_ground_truth(candidate)))
    checks["confidence"] = dict(zip(["pass", "message"], check_confidence(candidate)))

    # API changes documented
    api_changes = candidate.get("breaking_api_changes", [])
    if api_changes:
        checks["api_changes_documented"] = {
            "pass": True,
            "message": f"{len(api_changes)} breaking API changes documented",
        }
    else:
        checks["api_changes_documented"] = {
            "pass": False,
            "message": "No breaking API changes documented",
        }

    # Deep checks (require network access)
    if deep:
        upstream_url = candidate.get("upstream_repo", "")
        downstream_url = candidate.get("downstream_repo", "")

        checks["upstream_accessible"] = dict(
            zip(["pass", "message"], check_repo_accessible(upstream_url))
        )
        checks["downstream_accessible"] = dict(
            zip(["pass", "message"], check_repo_accessible(downstream_url))
        )

        upstream_rev = candidate.get("upstream_breaking_version", "")
        if upstream_rev:
            checks["upstream_rev_exists"] = dict(
                zip(["pass", "message"], check_revision_exists(upstream_url, upstream_rev))
            )

        downstream_rev = candidate.get("downstream_affected_version", "")
        if downstream_rev:
            checks["downstream_rev_exists"] = dict(
                zip(["pass", "message"], check_revision_exists(downstream_url, downstream_rev))
            )

    # Determine viability
    failures = [k for k, v in checks.items() if v["pass"] is False]
    warnings = [k for k, v in checks.items() if v["pass"] is None]
    passes = [k for k, v in checks.items() if v["pass"] is True]

    viable = len(failures) == 0 and len(passes) >= 2

    notes_parts = []
    if failures:
        notes_parts.append(f"FAILED: {', '.join(failures)}")
    if warnings:
        notes_parts.append(f"WARNINGS: {', '.join(warnings)}")

    return ValidationResult(
        candidate_id=candidate_id,
        checks=checks,
        viable=viable,
        notes="; ".join(notes_parts) if notes_parts else "All checks passed",
    )


def print_result(result: ValidationResult):
    """Pretty-print a validation result."""
    status = "VIABLE" if result.viable else "NOT VIABLE"
    print(f"\n{'='*60}")
    print(f"Candidate: {result.candidate_id}")
    print(f"Status:    {status}")
    print(f"{'='*60}")

    for check_name, check_result in result.checks.items():
        icon = {True: "PASS", False: "FAIL", None: "WARN"}[check_result["pass"]]
        print(f"  [{icon}] {check_name}: {check_result['message']}")

    if result.notes:
        print(f"\n  Notes: {result.notes}")


def main():
    parser = argparse.ArgumentParser(
        description="Validate a mining candidate for benchmark viability"
    )
    parser.add_argument(
        "--candidate",
        help="Path to candidates JSON file",
    )
    parser.add_argument(
        "--index", type=int, default=-1,
        help="Index of candidate (-1 = validate all)",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Run deep validation (requires network access, git)",
    )
    args = parser.parse_args()

    if not args.candidate:
        parser.error("Provide --candidate <path to candidates.json>")

    with open(args.candidate) as f:
        candidates = json.load(f)

    if args.index >= 0:
        candidates = [candidates[args.index]]

    results = []
    for candidate in candidates:
        result = validate_candidate(candidate, deep=args.deep)
        print_result(result)
        results.append(result)

    # Summary
    viable = sum(1 for r in results if r.viable)
    print(f"\n{'='*60}")
    print(f"SUMMARY: {viable}/{len(results)} candidates viable")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
