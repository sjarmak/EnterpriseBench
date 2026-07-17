"""A no-op agent may score >0 on at most the one known-open checkpoint.

Discovered from EnterpriseBench-hpcsv and generalized by EnterpriseBench-b5vk6:
a checkpoint that credits evidence already present in the agent-visible tree
(instruction.md, the ``$TASK_DIR`` answer key, or a default-pass eb_verify
plugin) pays a NO-OP agent full marks — the answer key grading itself. That is a
benchmark-defensibility hole, not a per-task curation slip.

``scripts/validation/noop_leak_sweep.py`` reproduces the no-op condition offline
(WORKSPACE = only instruction.md, no agent_output; TASK_DIR = the real answer
key) and reports every checkpoint scoring >0. This test freezes
the audit result: the leak set must never grow beyond the known-open allowlist.

KNOWN_OPEN is the single checkpoint whose fix lives on its own bead (hpcsv). It
is a subset assertion, so this test stays green both while hpcsv is open (its
check still leaks in a worktree without the fix) and after it lands (the set
shrinks to empty). Any NEW leaking checkpoint fails the build — that is the
regression this guard exists to catch.
"""

from __future__ import annotations

import functools
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


@functools.lru_cache(maxsize=1)
def _sweep_result():
    # The sweep shells out one subprocess per check (~400); every test below
    # consumes the same immutable result, so compute it once.
    benchmarks = REPO_ROOT / "benchmarks"
    result = sweep(benchmarks)
    assert result.n_tasks > 0, "swept zero tasks — path or discovery is broken"
    assert result.n_checks > 0, "swept zero checks — path or discovery is broken"
    return result


def _leak_keys():
    return {f"{lk.task_id}:{lk.checkpoint}" for lk in _sweep_result().leaks}


def test_every_check_scored():
    """No check may go unscored — that is what keeps 'not a leak' honest.

    The sweep parses verdicts with ``json.loads``; production's ``parse_score``
    (test_runner.sh) is more tolerant of malformed JSON. They can only diverge on
    a check whose no-op output is NOT valid JSON — and such a check surfaces here
    as ``errored``. Holding ``errored == 0`` proves every check parsed cleanly, so
    the two parsers agree on every leak decision and no leak is silently dropped
    to "not a leak". If this ever fails, a check started emitting malformed no-op
    output: re-anchor it or align the sweep onto parse_score (tracked follow-up),
    do not relax this assertion.
    """
    result = _sweep_result()
    assert result.n_errored == 0, (
        f"{result.n_errored} of {result.n_checks} checks produced no verdict "
        "under the no-op condition. An unscored check is not a proven "
        "'not a leak' — the audit is blind for it."
    )


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
