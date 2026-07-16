"""A no-op agent may score >0 on at most the one known-open checkpoint.

Discovered from EnterpriseBench-hpcsv and generalized by EnterpriseBench-b5vk6:
a checkpoint that credits evidence already present in the agent-visible tree
(instruction.md, the ``$TASK_DIR`` answer key, or a default-pass eb_verify
plugin) pays a NO-OP agent full marks — the answer key grading itself. That is a
benchmark-defensibility hole, not a per-task curation slip.

``scripts/validation/noop_leak_sweep.py`` reproduces the no-op condition offline
(WORKSPACE = only instruction.md + empty repo dirs, no agent_output; TASK_DIR =
the real answer key) and reports every checkpoint scoring >0. This test freezes
the audit result: the leak set must never grow beyond the known-open allowlist.

KNOWN_OPEN is the single checkpoint whose fix lives on its own bead (hpcsv). It
is a subset assertion, so this test stays green both while hpcsv is open (its
check still leaks in a worktree without the fix) and after it lands (the set
shrinks to empty). Any NEW leaking checkpoint fails the build — that is the
regression this guard exists to catch.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

from noop_leak_sweep import sweep  # noqa: E402

# task_id:checkpoint for every leak whose remediation is tracked elsewhere.
KNOWN_OPEN = frozenset(
    {
        "ansible-galaxy-tar-regression-prove-001:root_cause",  # EnterpriseBench-hpcsv
    }
)


def _leak_keys():
    benchmarks = REPO_ROOT / "benchmarks"
    leaks, n_tasks, n_checks = sweep(benchmarks, benchmarks)
    assert n_tasks > 0, "swept zero tasks — path or discovery is broken"
    assert n_checks > 0, "swept zero checks — path or discovery is broken"
    return {f"{lk.task_id}:{lk.checkpoint}" for lk in leaks}


def test_no_new_noop_leaks():
    unexpected = sorted(_leak_keys() - KNOWN_OPEN)
    assert not unexpected, (
        "A no-op agent scores >0 on checkpoint(s) not in the known-open "
        f"allowlist: {unexpected}. A planted-evidence / answer-key leak grades "
        "the answer key against itself — re-anchor the check to agent-produced "
        "evidence (cf. EnterpriseBench-hpcsv, EnterpriseBench-b5vk6)."
    )


def test_allowlist_stays_minimal():
    """The allowlist must not carry entries that no longer leak (stale debt)."""
    stale = sorted(KNOWN_OPEN - _leak_keys())
    assert not stale, (
        f"Allowlisted checkpoints no longer leak and should be removed: {stale}"
    )
