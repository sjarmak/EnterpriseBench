"""A no-op agent may score >0 on at most the one known-open checkpoint.

Discovered from EnterpriseBench-hpcsv and generalized by EnterpriseBench-b5vk6:
a checkpoint that credits evidence already present in the agent-visible tree
(instruction.md, the ``$TASK_DIR`` answer key, or a default-pass eb_verify
plugin) pays a NO-OP agent full marks — the answer key grading itself. That is a
benchmark-defensibility hole, not a per-task curation slip.

``scripts/validation/noop_leak_sweep.py`` reproduces the no-op condition offline
(WORKSPACE = only instruction.md, rendered as production renders it; TASK_DIR =
the real answer key) and reports every checkpoint scoring >0. This test freezes
the audit result: the leak set must never grow beyond the known-open allowlist.

KNOWN_OPEN is empty — the corpus has no known no-op leak. hpcsv's was the last
one, closed when ``check_root_cause.sh`` was re-anchored to ``agent_output/``
(e3f1242), so ``test_no_new_noop_leaks`` now asserts the strongest form of the
property: a no-op agent scores 0 on every checkpoint in the corpus.

Entries are ``task_id:checkpoint`` using the checkpoint name as registered in
``task.toml`` (e.g. ``root_cause_identified``), which is what the sweep reports
and what ``--allow`` matches — not the verifier's filename stem.

The two guards react to an allowlist entry differently, and only one of them
tolerates a stale one:

* ``test_no_new_noop_leaks`` asserts a SUBSET, so it stays green whether an
  allowlisted leak is open or already fixed.
* ``test_allowlist_stays_minimal`` asserts the converse and is the one that goes
  RED when an entry outlives its leak. That is deliberate: a resolved entry is
  debt, and a fix that lands elsewhere should force this list to shrink rather
  than let the allowlist quietly keep granting an exemption nobody needs.
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
    """Every check's "not a leak" must be proven — that is what keeps it honest.

    ``errored`` counts checks the sweep never learned the real no-op score of, for
    either of the two reasons ``sweep()`` documents, so a failure here has two
    possible causes and the message must not presume one:

    * No verdict. The sweep parses verdicts with ``json.loads``; production's
      ``parse_score`` (test_runner.sh) is more tolerant of malformed JSON, so the
      two can only diverge on a check whose no-op output is NOT valid JSON — and
      such a check surfaces here as ``errored``. Holding this at 0 is what proves
      the two parsers agree on every leak decision. Fix by re-anchoring the check,
      or align the sweep onto parse_score (tracked follow-up).
    * A degraded plant. A task.toml stopped parsing, so the 0.00 was scored
      against a subset of production's render and does not transfer. Fix the
      task.toml.

    Either way, do not relax this assertion.
    """
    result = _sweep_result()
    assert result.n_errored == 0, (
        f"{result.n_errored} of {result.n_checks} checks are unproven under the "
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
