"""Graded evidence must not be vocabulary the prompt already handed the agent.

The re-anchoring discipline (EnterpriseBench-jn73.2.7.3.1) moved report checks
onto ground_truth.json evidence tokens. That only buys anything if the tokens
are absent from instruction.md: a check grading a word the prompt supplies
credits an echo, which is the original root cause (46/47 curated leaks were
concept-vocabulary greps).

This is the STATIC complement to test_report_prompt_echo.py, and it covers what
that test structurally cannot. The echo vector's only move is
`cp instruction.md <deliverable>`; for a JSON deliverable that copy is not valid
JSON, so json.load throws, the check scores 0.0, and the task is certified clean
without the vector ever exercising it — 81 of 180 report tasks are JSON-only
(EnterpriseBench-jn73.2.7.3.1.4). Comparing tokens to the prompt needs no
deliverable at all, so it reaches those tasks.

Judged against instruction.md ONLY. That is the entire text the agent gets:
run_task.py feeds it as `agent_command < /workspace/instruction.md` (plus an
output appendix, plus the retrieval preamble and instruction_mcp.md in
mcp/cli modes). task.toml's [task].prompt is stale CSB-migration metadata that
is never shown to the agent and diverges from instruction.md in ~155 tasks, so
grading against it would both miss real leaks and invent phantom ones.

What this does NOT catch: evidence that is absent from the prompt but is not
real evidence either — a check's own filename, a ground_truth key, any token no
correct answer would contain. Those pass here and still yield an un-passable
task. Only scoring a plausible correct answer catches that; see the note in
test_report_prompt_echo.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BENCH = REPO_ROOT / "benchmarks"


def _independently_scored_tokens(gt: dict) -> list[tuple[str, str]]:
    """Tokens that each earn credit ON THEIR OWN, as (checkpoint, token).

    The flat scoring_evidence map is scored `found / len(evidence)` — one token,
    one increment, no other token required. So EVERY one of them must be absent
    from the prompt; a single prompt-supplied entry is partial credit for an echo.
    Keys starting with "_" are prose notes to authors, never graded.
    """
    out: list[tuple[str, str]] = []
    evidence = gt.get("scoring_evidence")
    if isinstance(evidence, dict):
        for checkpoint, tokens in evidence.items():
            if checkpoint.startswith("_") or not isinstance(tokens, list):
                continue
            out.extend((checkpoint, t) for t in tokens if isinstance(t, str) and t)
    return out


def _conjunction_groups(gt: dict) -> list[tuple[str, list[str]]]:
    """Token sets that must ALL match together, as (label, tokens).

    config-drift's structured deliverables grade a drift point with
    `all(identifies) and all(actual)` — the tokens are ANDed, so they are not
    individually scored and the rule above does not apply to them. Some are pure
    locators the prompt is expected to supply (an entry name the prompt already
    quotes); the evidence is what sits beside them (the key path, the wrong
    expression). The invariant that survives is weaker but still binding: the
    conjunction as a whole must be unsatisfiable from the prompt alone, i.e. at
    least one token in it must be non-prompt.
    """
    out: list[tuple[str, list[str]]] = []
    for point in gt.get("drift_points") or []:
        if not isinstance(point, dict):
            continue
        tokens = point.get("evidence_tokens")
        if not isinstance(tokens, dict):
            continue
        merged = [
            t
            for values in tokens.values()
            if isinstance(values, list)
            for t in values
            if isinstance(t, str) and t
        ]
        if merged:
            out.append((f"drift_points[{point.get('key')}]", merged))
    return out


def _has_graded_evidence(gt: dict) -> bool:
    return bool(_independently_scored_tokens(gt) or _conjunction_groups(gt))


def _tasks_with_graded_evidence() -> list[Path]:
    found: list[Path] = []
    for gt_path in sorted(BENCH.rglob("ground_truth.json")):
        if {"_archived", "mined"} & set(gt_path.relative_to(BENCH).parts):
            continue
        if not (gt_path.parent / "instruction.md").exists():
            continue
        try:
            gt = json.loads(gt_path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue  # schema tests own malformed ground_truth
        if isinstance(gt, dict) and _has_graded_evidence(gt):
            found.append(gt_path.parent)
    return found


TASK_DIRS = _tasks_with_graded_evidence()
TASK_IDS = [str(d.relative_to(BENCH)) for d in TASK_DIRS]


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=TASK_IDS)
def test_independently_scored_evidence_absent_from_prompt(task_dir: Path) -> None:
    """Every token that scores on its own must be absent from the prompt."""
    gt = json.loads((task_dir / "ground_truth.json").read_text())
    prompt = (task_dir / "instruction.md").read_text(errors="replace").lower()

    # Fixed-string containment, never a regex: "." in a token like
    # "ansible.galaxy.collection" would match "ansible-galaxy collection" in the
    # prose and hide a real leak behind a false match.
    leaked = [
        (checkpoint, token)
        for checkpoint, token in _independently_scored_tokens(gt)
        if token.lower() in prompt
    ]
    assert not leaked, (
        f"{task_dir.relative_to(BENCH)} grades tokens its own instruction.md "
        f"supplies, and scoring_evidence credits each token on its own, so a "
        f"report echoing the prompt earns partial credit for them: {leaked}. "
        f"Re-anchor to evidence only a reader of the repo has."
    )


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=TASK_IDS)
def test_conjunctions_need_at_least_one_nonprompt_token(task_dir: Path) -> None:
    """An ANDed token set must not be satisfiable from the prompt alone."""
    gt = json.loads((task_dir / "ground_truth.json").read_text())
    prompt = (task_dir / "instruction.md").read_text(errors="replace").lower()

    all_prompt = [
        (label, tokens)
        for label, tokens in _conjunction_groups(gt)
        if all(t.lower() in prompt for t in tokens)
    ]
    assert not all_prompt, (
        f"{task_dir.relative_to(BENCH)} has drift points whose every graded "
        f"token comes from its own instruction.md, so the whole conjunction is "
        f"satisfiable by echoing the prompt: {all_prompt}. At least one token "
        f"must be evidence only a reader of the repo has."
    )


def test_the_invariant_is_actually_covering_tasks() -> None:
    """Guard against a silently empty sweep: if _graded_tokens stops matching the
    ground_truth shape, every test above vanishes and the suite still goes green."""
    assert len(TASK_DIRS) >= 80, (
        f"only {len(TASK_DIRS)} tasks expose graded evidence; 82 carried it when "
        f"this was written. A drop means the ground_truth shape moved and "
        f"_graded_tokens no longer reads it — the sweep is passing vacuously."
    )
