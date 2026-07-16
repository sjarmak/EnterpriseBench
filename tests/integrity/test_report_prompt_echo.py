"""Suite-wide prompt-echo invariant for report-deliverable tasks.

The integrity property every graded report task must hold: a verbatim copy of
the prompt into the deliverable (`cp instruction.md <deliverable>`) must earn
ZERO credit on every check. A check that credits a prompt copy is grading
vocabulary the task already handed the agent, not investigation evidence
(EnterpriseBench root cause: 46/47 curated leaks were concept-vocabulary greps;
see docs — the gen-1 report verifiers never adopted the scoring_evidence /
repo-specific-evidence discipline the gen-2 checks use).

This test enforces the invariant across ALL active report tasks so it cannot
regress, and QUARANTINES the currently-known leakers as strict xfails. When a
quarantined task is re-anchored (grade against ground_truth.json:scoring_evidence
or repo-specific evidence absent from the prompt), its xfail flips to a failure
that says "remove me from known_prompt_echo_leaks.json" — the quarantine only
shrinks.

One-way exception to shrink-only: a leaker the ORIGINAL scan missed may be added
once, as bookkeeping. refactor-orchestration-tri-tokio-001 is the only such entry
— it was tracked and leaking at a51e7e8 yet absent from the generated list, so
main has been red since. It is a pre-existing leak, not a regression; a scan of
all 141 tracked report tasks at that commit found no other omission. A NEW leak
is still a failure to fix, never an addition here.

A fix means the check stops crediting prompt vocabulary while a CORRECT answer
still scores. Padding scoring_evidence with tokens no real answer would contain
(a check's own filename, a ground_truth JSON key) silences this test by failing
every deliverable equally — an un-passable task, not a fixed one. Verify a fix
against a plausible correct answer, not only against expected_solution.json:
that key can be, and has been, written to fit the grader.

Regenerate the quarantine (a reviewed act, only after fixing tasks):
    python3 scripts/validation/curated_gate_analyzer.py  # then rescan helper

Tracking: EnterpriseBench-jn73.2.7.3.1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
import curated_gate_analyzer as gate  # noqa: E402

QUARANTINE_FILE = Path(__file__).parent / "known_prompt_echo_leaks.json"
KNOWN_LEAK: set[str] = set(json.loads(QUARANTINE_FILE.read_text()))

REPORT_TASKS = gate.discover_report_tasks()
TASK_IDS = [str(d.relative_to(gate.BENCH)) for d in REPORT_TASKS]


def _run(task_rel: str) -> dict:
    return gate.echo_leak(gate.BENCH / task_rel)


@pytest.mark.parametrize(
    "task_rel",
    [t for t in TASK_IDS if t not in KNOWN_LEAK],
)
def test_clean_report_task_resists_prompt_echo(task_rel: str) -> None:
    """Every non-quarantined report task scores 0 on a prompt copy — enforced."""
    leak = _run(task_rel)
    assert not leak, (
        f"{task_rel} credits a prompt copy on {list(leak)} (scores {leak}). "
        f"Re-anchor these checks to non-prompt evidence "
        f"(ground_truth.json:scoring_evidence)."
    )


@pytest.mark.parametrize("task_rel", sorted(KNOWN_LEAK))
@pytest.mark.xfail(strict=True, reason="known prompt-echo leak, quarantined "
                   "under EnterpriseBench-jn73.2.7.3.1")
def test_quarantined_task_still_leaks(task_rel: str) -> None:
    """Quarantined tasks are expected to still leak. When one is fixed this
    xfail flips (XPASS -> failure), signalling: remove it from
    known_prompt_echo_leaks.json."""
    leak = _run(task_rel)
    assert not leak


def test_quarantine_list_has_no_stale_entries() -> None:
    """Every quarantined id is still a discoverable report task (no drift)."""
    stale = KNOWN_LEAK - set(TASK_IDS)
    assert not stale, f"quarantine references non-existent report tasks: {stale}"
