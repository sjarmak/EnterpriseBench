#!/usr/bin/env python3
"""Check repo_versions.json for repos with stale last_verified dates.

Usage:
    python scripts/infra/check_repo_staleness.py                  # human-readable staleness
    python scripts/infra/check_repo_staleness.py --json            # machine-readable JSON
    python scripts/infra/check_repo_staleness.py --verify-files    # clone repos and verify required_files exist
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "configs" / "repo_versions.json"
DEFAULT_BENCHMARKS = ROOT / "benchmarks"
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


@dataclass(frozen=True)
class RequiredFileEntry:
    """A single ground-truth required file with its repo context."""

    task_id: str
    task_path: str
    file_path: str
    repo_name: str
    repo_url: str
    pinned_rev: str
    confidence: float


def _parse_toml(path: pathlib.Path) -> dict:
    """Parse a TOML file, raising RuntimeError if no parser is available."""
    if tomllib is None:
        raise RuntimeError("No TOML parser available. Install tomli: pip install tomli")
    with open(path, "rb") as f:
        return tomllib.load(f)


def scan_required_files(
    benchmarks_dir: pathlib.Path,
) -> list[RequiredFileEntry]:
    """Scan task.toml files and collect ground_truth.required_files entries.

    Skips archived tasks (under _archived/) and tasks without required_files.
    Cross-references each required_file's repo name against the task's [[repos]]
    to resolve the URL and pinned revision.

    Returns:
        Sorted list of RequiredFileEntry (by task_id, then file_path).
    """
    entries: list[RequiredFileEntry] = []

    for toml_path in sorted(benchmarks_dir.glob("**/task.toml")):
        # Skip archived tasks
        if "_archived" in toml_path.parts:
            continue

        try:
            data = _parse_toml(toml_path)
        except Exception:
            continue

        task_section = data.get("task", {})
        task_id = task_section.get("id", toml_path.parent.name)

        # Build repo lookup: path -> {url, rev}
        repos = data.get("repos", [])
        repo_lookup: dict[str, dict[str, str]] = {}
        for repo in repos:
            repo_path = repo.get("path", "")
            repo_lookup[repo_path] = {
                "url": repo.get("url", ""),
                "rev": repo.get("rev", ""),
            }

        # Extract required_files from ground_truth
        ground_truth = data.get("ground_truth", {})
        required_files = ground_truth.get("required_files", [])

        for rf in required_files:
            repo_name = rf.get("repo", "")
            repo_info = repo_lookup.get(repo_name, {"url": "", "rev": ""})
            entries.append(
                RequiredFileEntry(
                    task_id=task_id,
                    task_path=str(toml_path.relative_to(benchmarks_dir)),
                    file_path=rf.get("path", ""),
                    repo_name=repo_name,
                    repo_url=repo_info["url"],
                    pinned_rev=repo_info["rev"],
                    confidence=rf.get("confidence", 0.0),
                )
            )

    return sorted(entries, key=lambda e: (e.task_id, e.file_path))


def format_verify_files_report(
    entries: list[RequiredFileEntry],
    json_output: bool = False,
) -> str:
    """Format the verify-files report as human-readable text or JSON.

    Args:
        entries: List of RequiredFileEntry from scan_required_files.
        json_output: If True, return JSON; otherwise human-readable text.

    Returns:
        Formatted report string.
    """
    if json_output:
        return json.dumps(
            {
                "total_required_files": len(entries),
                "entries": [asdict(e) for e in entries],
            },
            indent=2,
        )

    if not entries:
        return "No ground_truth.required_files found in any active task."

    lines: list[str] = []
    lines.append(f"Found {len(entries)} required_files across active tasks:\n")
    current_task = ""
    for entry in entries:
        if entry.task_id != current_task:
            current_task = entry.task_id
            lines.append(f"  [{entry.task_id}]")
        lines.append(
            f"    {entry.repo_name}/{entry.file_path}  "
            f"@ {entry.pinned_rev}  (confidence: {entry.confidence})"
        )
    return "\n".join(lines)


@dataclass(frozen=True)
class FileVerifyResult:
    """Result of verifying a single required file against its pinned revision."""

    entry: RequiredFileEntry
    exists: bool
    error: str = ""


def _shallow_fetch_file_list(
    repo_url: str,
    rev: str,
    work_dir: pathlib.Path,
    timeout_seconds: int = 120,
) -> set[str]:
    """Fetch a repo at a specific revision and return the set of file paths.

    Uses shallow fetch with no checkout to minimize disk and network usage.

    Args:
        repo_url: Git clone URL.
        rev: Tag, branch, or SHA to fetch.
        work_dir: Empty directory to use for the git operations.
        timeout_seconds: Maximum time for each git command.

    Returns:
        Set of file paths present at the given revision.

    Raises:
        RuntimeError: If any git command fails.
    """

    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git command failed: {' '.join(cmd)}\n"
                f"stderr: {result.stderr.strip()}"
            )
        return result

    _run(["git", "init", "-q"])
    _run(["git", "remote", "add", "origin", repo_url])
    _run(["git", "fetch", "--depth", "1", "-q", "origin", rev])

    result = _run(["git", "ls-tree", "-r", "--name-only", "FETCH_HEAD"])
    return set(result.stdout.strip().splitlines())


def verify_files_exist(
    entries: list[RequiredFileEntry],
    timeout_seconds: int = 120,
) -> list[FileVerifyResult]:
    """Clone repos at pinned revisions and verify required files exist.

    Groups entries by (repo_url, pinned_rev) to avoid redundant clones.
    Uses shallow fetch + git ls-tree for minimal disk/network usage.

    Args:
        entries: Required file entries from scan_required_files.
        timeout_seconds: Timeout per git command.

    Returns:
        List of FileVerifyResult for every entry.
    """
    # Group by (url, rev) to deduplicate clones
    groups: dict[tuple[str, str], list[RequiredFileEntry]] = {}
    for entry in entries:
        key = (entry.repo_url, entry.pinned_rev)
        groups.setdefault(key, []).append(entry)

    results: list[FileVerifyResult] = []

    for (repo_url, rev), group_entries in groups.items():
        file_set: set[str] | None = None
        clone_error = ""

        if not repo_url or not rev:
            clone_error = "missing repo_url or pinned_rev"
        else:
            try:
                with tempfile.TemporaryDirectory(prefix="eb_verify_") as tmpdir:
                    file_set = _shallow_fetch_file_list(
                        repo_url, rev, pathlib.Path(tmpdir), timeout_seconds
                    )
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
                clone_error = str(exc)
                logger.warning(
                    "Failed to fetch %s @ %s: %s", repo_url, rev, clone_error
                )

        for entry in group_entries:
            if clone_error:
                results.append(
                    FileVerifyResult(entry=entry, exists=False, error=clone_error)
                )
            else:
                assert file_set is not None
                exists = entry.file_path in file_set
                results.append(FileVerifyResult(entry=entry, exists=exists))

    return sorted(results, key=lambda r: (r.entry.task_id, r.entry.file_path))


def format_verify_results_report(
    results: list[FileVerifyResult],
    json_output: bool = False,
) -> str:
    """Format verification results as human-readable text or JSON.

    Args:
        results: List of FileVerifyResult from verify_files_exist.
        json_output: If True, return JSON; otherwise human-readable text.

    Returns:
        Formatted report string.
    """
    missing = [r for r in results if not r.exists]
    passed = [r for r in results if r.exists]

    if json_output:
        return json.dumps(
            {
                "total_files": len(results),
                "missing_count": len(missing),
                "passed_count": len(passed),
                "missing": [{**asdict(r.entry), "error": r.error} for r in missing],
                "passed": [asdict(r.entry) for r in passed],
            },
            indent=2,
        )

    if not results:
        return "No ground_truth.required_files found to verify."

    if not missing:
        return f"All {len(results)} required files verified successfully."

    lines: list[str] = []
    lines.append(
        f"FAILED: {len(missing)} of {len(results)} required files not found:\n"
    )
    current_task = ""
    for r in missing:
        if r.entry.task_id != current_task:
            current_task = r.entry.task_id
            lines.append(f"  [{r.entry.task_id}]")
        error_note = f"  (error: {r.error})" if r.error else ""
        lines.append(
            f"    {r.entry.repo_name}/{r.entry.file_path}  "
            f"@ {r.entry.pinned_rev}{error_note}"
        )
    return "\n".join(lines)


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
    parser.add_argument(
        "--verify-files",
        action="store_true",
        help="Clone repos at pinned SHAs and verify ground_truth.required_files exist",
    )
    parser.add_argument(
        "--benchmarks-dir",
        type=pathlib.Path,
        default=DEFAULT_BENCHMARKS,
        help=f"Path to benchmarks directory (default: {DEFAULT_BENCHMARKS})",
    )
    args = parser.parse_args()

    # --verify-files mode: clone repos and verify required files exist
    if args.verify_files:
        required = scan_required_files(args.benchmarks_dir)
        if not required:
            print(format_verify_files_report(required, json_output=args.json_output))
            return 0

        results = verify_files_exist(required)
        report = format_verify_results_report(results, json_output=args.json_output)
        print(report)
        missing = [r for r in results if not r.exists]
        return 1 if missing else 0

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
