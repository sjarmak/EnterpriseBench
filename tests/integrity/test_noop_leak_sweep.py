"""A no-op agent must score 0 on every checkpoint outside the known-open allowlist.

Discovered from EnterpriseBench-hpcsv and generalized by EnterpriseBench-b5vk6:
a checkpoint that credits evidence already present in the agent-visible tree
(instruction.md, the ``$TASK_DIR`` answer key, or a default-pass eb_verify
plugin) pays a NO-OP agent full marks — the answer key grading itself. That is a
benchmark-defensibility hole, not a per-task curation slip.

``scripts/validation/noop_leak_sweep.py`` reproduces the no-op condition offline
(WORKSPACE = only instruction.md, rendered as production renders it; TASK_DIR =
the real answer key) and reports every checkpoint scoring >0. This test freezes
that result.

Allowlist entries are ``task_id:checkpoint`` using the checkpoint name as
registered in ``task.toml`` (e.g. ``root_cause_identified``), which is what the
sweep reports and what ``--allow`` matches — not the verifier's filename stem.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

from noop_leak_sweep import sweep  # noqa: E402

# task_id:checkpoint for every leak whose remediation is tracked elsewhere.
# Empty: no checkpoint in the corpus pays a no-op agent. Adding an entry here
# grants an exemption, so it belongs to a bead that will remove it again.
KNOWN_OPEN: frozenset[str] = frozenset()


@functools.lru_cache(maxsize=1)
def _sweep_result():
    # The sweep shells out one subprocess per check (~470); every test below
    # consumes the same immutable result, so compute it once.
    benchmarks = REPO_ROOT / "benchmarks"
    result = sweep(benchmarks)
    assert result.n_tasks > 0, "swept zero tasks — path or discovery is broken"
    assert result.n_checks > 0, "swept zero checks — path or discovery is broken"
    return result


def _leak_keys():
    return {f"{lk.task_id}:{lk.checkpoint}" for lk in _sweep_result().leaks}


def test_every_check_scored():
    """Every check's "not a leak" must be proven, not merely unobserved.

    Holding this at 0 is what proves the sweep's ``json.loads`` oracle and
    production's more tolerant ``parse_score`` agree on every leak decision (see
    the parser-boundary limitation in docs/internal/NOOP_LEAK_AUDIT.md). Fix the
    check or the task.toml; do not relax the assertion.
    """
    result = _sweep_result()
    assert result.n_unproven == 0, (
        f"{result.n_unproven} of {result.n_checks} checks are unproven under the "
        "no-op condition — either they reached no verdict, or their task.toml "
        "would not parse so they were graded against a degraded plant. Neither is "
        "a proven 'not a leak' — the audit is blind for them. See stderr for which."
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
    """The allowlist must not carry entries that no longer leak (stale debt).

    This is the guard that shrinks KNOWN_OPEN. It goes RED when a fix lands
    elsewhere and resolves an allowlisted leak — remove the entry, that is the
    fix. Vacuous while KNOWN_OPEN is empty; it arms itself the moment an
    exemption is added.
    """
    stale = sorted(KNOWN_OPEN - _leak_keys())
    assert not stale, (
        f"Allowlisted checkpoints no longer leak and should be removed: {stale}"
    )
