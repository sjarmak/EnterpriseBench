#!/usr/bin/env python3
"""Fail when a CLOSED bead's work branch has commits that never landed on main.

The bead store says DONE; main does not have the code. Every such branch is a
fix that was written, reviewed, committed, closed — and shipped nothing. This
check is the gate that catches that at close time instead of at audit time.

Not every closed bead is meant to ship: a bead can be closed as superseded or
rejected, its branch deliberately abandoned. That is a legitimate outcome, but
it has to be stated rather than inferred, so this check reads an explicit
`no-merge` label and does not try to divine intent from the close reason. An
unlabelled closed bead with unlanded commits is an error.

A commit counts as landed if its patch is on the integration ref, even under a
different SHA, so rebased and cherry-picked branches are not flagged. Squash
merges are NOT recognised: a squash gives the combined diff a patch id that
matches none of the source commits, so a squash-landed branch reports as
unlanded. This repo lands work by fast-forward, merge, or cherry-pick.

Runs locally, not in GitHub Actions: work/* branches are never pushed and the
bead store is untracked, so a hosted CI job would see neither and report green
forever.

Usage:
    python scripts/infra/check_unmerged_closed_beads.py
    python scripts/infra/check_unmerged_closed_beads.py --json
    python scripts/infra/check_unmerged_closed_beads.py --integration-ref origin/main
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from dataclasses import asdict, dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_INTEGRATION_REF = "main"
DEFAULT_PREFIX = "work/"
CLOSED = "closed"
NO_MERGE_LABEL = "no-merge"
SUBPROCESS_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class Bead:
    """The slice of a bead this check needs."""

    status: str
    no_merge: bool


@dataclass(frozen=True)
class BranchState:
    """A work branch, the bead it belongs to, and how much of it never landed."""

    branch: str
    bead_id: str
    status: str  # bd status, or "" when the store has no such bead
    unlanded_commits: int
    no_merge: bool = False


UNKNOWN_BEAD = Bead(status="", no_merge=False)


def find_violations(states: list[BranchState]) -> list[BranchState]:
    """Return the closed beads that still owe commits to main, worst first.

    Three kinds of branch are left alone. An open bead is work in progress. A
    bead labelled `no-merge` was closed with its branch deliberately abandoned.
    A branch with no bead in the store cannot be a close-without-merge, and
    policing other people's branches is not this check's job.
    """
    return sorted(
        (
            state
            for state in states
            if state.status == CLOSED
            and state.unlanded_commits > 0
            and not state.no_merge
        ),
        key=lambda state: (-state.unlanded_commits, state.bead_id),
    )


def bead_id_for_branch(branch: str, prefix: str) -> str:
    """Strip the branch prefix to recover the bead id."""
    if not branch.startswith(prefix):
        raise ValueError(f"branch {branch!r} does not start with {prefix!r}")
    return branch[len(prefix) :]


def _run(
    cmd: list[str], cwd: pathlib.Path, timeout: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def list_work_branches(prefix: str, cwd: pathlib.Path) -> list[str]:
    """List local branches under the prefix, sorted by name."""
    result = _run(
        ["git", "for-each-ref", "--format=%(refname:short)", f"refs/heads/{prefix}"],
        cwd,
        SUBPROCESS_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git for-each-ref failed: {result.stderr.strip()}")
    return sorted(line for line in result.stdout.splitlines() if line)


def count_unlanded_commits(branch: str, integration_ref: str, cwd: pathlib.Path) -> int:
    """Count commits on the branch whose patch is not on the integration ref.

    `git cherry` compares by patch id, so a commit that reached the integration
    ref through a rebase or cherry-pick is reported as landed ('-') rather than
    unlanded ('+'). See the module docstring on squash merges.
    """
    result = _run(
        ["git", "cherry", integration_ref, branch], cwd, SUBPROCESS_TIMEOUT_SECONDS
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git cherry failed for {branch} against {integration_ref}: "
            f"{result.stderr.strip()}"
        )
    return sum(1 for line in result.stdout.splitlines() if line.startswith("+"))


def parse_beads(payload: str) -> dict[str, Bead]:
    """Parse `bd list --json` output into a bead-id keyed map.

    Anything unexpected in the payload raises rather than degrading into a
    partial map: a check that silently loses a bead's status would report clean
    for the very branch it failed to look up.
    """
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"bd list returned invalid JSON: {exc}") from exc

    if not isinstance(raw, list):
        raise RuntimeError(f"bd list returned {type(raw).__name__}, expected a list")

    beads: dict[str, Bead] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise RuntimeError(f"bd list returned a non-object entry: {entry!r}")

        bead_id = entry.get("id")
        status = entry.get("status")
        if not isinstance(bead_id, str) or not isinstance(status, str):
            raise RuntimeError(
                f"bd list entry is missing a string id or status: {entry!r}"
            )

        labels = entry.get("labels") or []
        if not isinstance(labels, list):
            raise RuntimeError(
                f"bd list entry {bead_id} has non-list labels: {labels!r}"
            )

        beads[bead_id] = Bead(status=status, no_merge=NO_MERGE_LABEL in labels)

    return beads


def fetch_beads(bead_ids: list[str], cwd: pathlib.Path) -> dict[str, Bead]:
    """Look up each bead id. Ids absent from the store are omitted from the map."""
    if not bead_ids:
        return {}

    result = _run(
        ["bd", "list", "--id", ",".join(bead_ids), "--all", "--json"],
        cwd,
        SUBPROCESS_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"bd list failed: {result.stderr.strip()}")

    return parse_beads(result.stdout)


def collect_states(
    prefix: str, integration_ref: str, cwd: pathlib.Path
) -> list[BranchState]:
    """Gather every work branch with its bead status and unlanded commit count."""
    branches = list_work_branches(prefix, cwd)
    bead_ids = [bead_id_for_branch(branch, prefix) for branch in branches]
    beads = fetch_beads(bead_ids, cwd)

    states = []
    for branch, bead_id in zip(branches, bead_ids):
        bead = beads.get(bead_id, UNKNOWN_BEAD)
        states.append(
            BranchState(
                branch=branch,
                bead_id=bead_id,
                status=bead.status,
                unlanded_commits=count_unlanded_commits(branch, integration_ref, cwd),
                no_merge=bead.no_merge,
            )
        )
    return states


def format_report(states: list[BranchState], violations: list[BranchState]) -> str:
    """Render the human-readable report."""
    if not states:
        return "No work branches found."

    if not violations:
        return (
            f"No closed bead has unlanded commits "
            f"({len(states)} work branches checked)."
        )

    lines = [
        f"FAILED: {len(violations)} of {len(states)} work branches belong to a "
        f"CLOSED bead but have commits that never reached the integration ref.",
        "The bead store says this work is done. It is not on main.",
        "",
    ]
    for violation in violations:
        lines.append(
            f"  {violation.bead_id}: {violation.unlanded_commits} unlanded "
            f"commit(s) on {violation.branch}"
        )
    lines.append("")
    lines.append(
        "Land the branch, or reopen the bead. If the branch is deliberately "
        f"abandoned (superseded, rejected), say so: bd update <id> --add-label "
        f"{NO_MERGE_LABEL}"
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail when a closed bead's work branch has unlanded commits."
    )
    parser.add_argument(
        "--integration-ref",
        default=DEFAULT_INTEGRATION_REF,
        help=f"Ref that work must land on (default: {DEFAULT_INTEGRATION_REF})",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"Work branch prefix (default: {DEFAULT_PREFIX})",
    )
    parser.add_argument(
        "--repo",
        type=pathlib.Path,
        default=ROOT,
        help=f"Repository to check (default: {ROOT})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    try:
        states = collect_states(args.prefix, args.integration_ref, args.repo)
    except (RuntimeError, ValueError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    violations = find_violations(states)

    if args.json_output:
        json.dump(
            {
                "integration_ref": args.integration_ref,
                "branches_checked": len(states),
                "violation_count": len(violations),
                "violations": [
                    {
                        "branch": v.branch,
                        "bead_id": v.bead_id,
                        "unlanded_commits": v.unlanded_commits,
                    }
                    for v in violations
                ],
                "branches": [asdict(s) for s in states],
            },
            sys.stdout,
            indent=2,
        )
        print()
    else:
        print(format_report(states, violations))

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
