"""Scoring integrity for chain-err-flask-import-001 (EnterpriseBench-e4w15).

The task used to score 1.00/1.00 for zero comprehension: a verbatim copy of the
session prompts into INVESTIGATION.md/FIX_SUMMARY.md plus ONE comment appended
to tests/conftest.py. Three separate defects made that possible.

1. The premise was FABRICATED. The task asserted a cycle
   flask -> flask.json -> flask.globals -> flask.app -> flask.json in Flask
   3.1.0. Two of those four edges do not exist: flask.globals imports flask.app
   only under `if t.TYPE_CHECKING:`, and flask.app never imports flask.json at
   all. `from flask.json import dumps` succeeds; the task's own reported user
   scenario serves HTTP 200. There was no bug, so no check could grade a fix —
   only its footprint.
2. check_fix.sh graded footprint: FIX_SUMMARY.md > 50 bytes AND any *.py file in
   `git diff --name-only HEAD~1`. A comment in a TEST file paid the full 0.40.
3. check_cycle.sh / check_investigation.sh grepped concept vocabulary the
   session prompt already supplied (the prompt stated the cycle verbatim), so an
   echo scored 1.0 — the gen-1 leak class (see test_report_prompt_echo.py).

The re-scope grades the comprehension the fabrication accidentally created: the
claim is stated as unconfirmed triage notes, and the agent must work out which
claimed edges are real. Discrimination is the signal, so blanket answers and
coin flips earn nothing (negative marking), and no diff is graded at all — which
is what removes the comment vector rather than merely tightening it.

This module is the bead's regression test: the uc12m repro (comment-only edit ->
expect 0) is one row of the matrix below.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BENCH = REPO_ROOT / "benchmarks"
TASK_DIR = BENCH / "customer_escalation" / "chain-err-flask-import-001"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
sys.path.insert(0, str(REPO_ROOT / "lib"))
import curated_gate_analyzer as gate  # noqa: E402
from eb_verify.scorer_guard import InfraError, run_verifier_subprocess  # noqa: E402


def _load_toml(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _toml() -> dict:
    return _load_toml(TASK_DIR / "task.toml")


def _ground_truth() -> dict:
    return json.loads((TASK_DIR / "ground_truth.json").read_text())


# --- scoring harness -------------------------------------------------------
#
# Scores the task the way the REAL runners do. The three runners disagree on how
# the workspace reaches a check, and this task's scripts run under all three:
#   runner.py     (checkpoints): no $1, env WORKSPACE+TASK_DIR, cwd=workspace
#   milestone.py  (milestones) : $1 passed, NO env at all, cwd=workspace
#   test_runner.sh (sandbox)   : $1 AND env, cwd deliberately OUTSIDE workspace
# The CONVENTIONS matrix rides only on the tests that assert a NON-ZERO score.
# That is where it carries signal: a check that resolves no convention finds no
# deliverable and scores 0.0, so every "gaming variant -> 0.0" test would pass
# vacuously under exactly the breakage the matrix exists to catch. The two
# correct-answer tests prove resolution works under all three; downstream of
# $WORKSPACE the scoring logic is convention-independent, so re-running the zero
# tests per convention re-tests nothing and just triples the subprocess count.


def _score_one(verifier: Path, workspace: Path, convention: str, cwd: Path) -> float:
    argv = ["bash", str(verifier)]
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)}
    if convention in ("milestone", "sandbox"):
        argv.append(str(workspace))
    if convention in ("runner", "sandbox"):
        env["WORKSPACE"] = str(workspace)
        env["TASK_DIR"] = str(TASK_DIR)
    out = subprocess.run(
        argv, cwd=str(cwd), capture_output=True, text=True, env=env, timeout=120
    )
    if not out.stdout.strip():
        raise AssertionError(f"{verifier.name} printed no verdict: {out.stderr}")
    return float(json.loads(out.stdout.strip())["score"])


def score(workspace: Path, convention: str, tmp_path: Path) -> float:
    """Weighted task score in [0,1] under one runner convention."""
    # cwd=workspace for the two host runners; outside it for the sandbox.
    cwd = workspace if convention in ("runner", "milestone") else tmp_path
    total = 0.0
    for cp in _toml()["checkpoints"]:
        s = _score_one(TASK_DIR / cp["verifier"], workspace, convention, cwd)
        total += s * cp["weight"]
    return round(total, 4)


CONVENTIONS = ["runner", "milestone", "sandbox"]


# --- payloads --------------------------------------------------------------


def _session_prompts() -> str:
    return "\n".join(s["prompt"] for s in _toml()["sessions"])


def _make_ws(tmp_path: Path, name: str) -> Path:
    ws = tmp_path / name
    (ws / "flask").mkdir(parents=True)
    return ws


def _write(ws: Path, **files: str) -> Path:
    """Write deliverables into `ws/flask/`, keyed by kwargs.

    A kwarg name carries the deliverable filename with its ONE dot written as
    `__`, because a dot is not legal in a Python identifier: INVESTIGATION__md ->
    INVESTIGATION.md. Every deliverable this task grades has exactly one
    extension, so the replace is bounded to that single separator — a name with
    two would silently produce the wrong filename, hence count=1 and the assert.
    """
    for fname, content in files.items():
        name = fname.replace("__", ".", 1)
        assert "__" not in name, f"{fname}: expected one '__' separator, got more"
        (ws / "flask" / name).write_text(content)
    return ws


CORRECT_INVESTIGATION = """# Investigation: the reported import cycle

I checked each edge the triage notes claim against src/flask/ at 3.1.0.

- flask -> flask.json: REAL. src/flask/__init__.py imports `from . import json as json`
  at module level.
- flask.json -> flask.globals: REAL. src/flask/json/__init__.py does
  `from ..globals import current_app` at module level.
- flask.globals -> flask.app: NOT a runtime import. src/flask/globals.py only does
  `from .app import Flask` inside `if t.TYPE_CHECKING:`, which the interpreter never
  executes. Its actual runtime imports are __future__, typing, contextvars
  (ContextVar) and werkzeug.local (LocalProxy). The globals are LocalProxy objects
  over ContextVar, so no Flask class is needed at import time.
- flask.app -> flask.json: ABSENT. src/flask/app.py does not import flask.json at all,
  not even under a type-checking guard.

The chain therefore never closes: two of the four claimed edges do not exist at
runtime. Exercising it confirms this -- `from flask.json import dumps` imports
cleanly and the reported blueprint scenario serves a normal response.
"""

CORRECT_VERDICT = json.dumps(
    {
        "claimed_edges": [
            {"from": "flask", "to": "flask.json", "imported_at_runtime": True},
            {"from": "flask.json", "to": "flask.globals", "imported_at_runtime": True},
            {"from": "flask.globals", "to": "flask.app", "imported_at_runtime": False},
            {"from": "flask.app", "to": "flask.json", "imported_at_runtime": False},
        ]
    },
    indent=2,
)

CORRECT_RESOLUTION = json.dumps(
    {
        "code_change_required": False,
        "reason": (
            "The reported cycle does not exist, so there is nothing to break. "
            "flask.globals imports flask.app only under a TYPE_CHECKING guard and "
            "flask.app never imports flask.json, so the chain never closes. Patching "
            "working code to defer an import that already is not there would add risk "
            "and fix nothing; the customer's ImportError has another cause and needs "
            "their actual traceback."
        ),
    },
    indent=2,
)


def correct_ws(tmp_path: Path) -> Path:
    ws = _make_ws(tmp_path, "correct")
    return _write(
        ws,
        INVESTIGATION__md=CORRECT_INVESTIGATION,
        CYCLE_VERDICT__json=CORRECT_VERDICT,
        RESOLUTION__json=CORRECT_RESOLUTION,
    )


# --- the matrix ------------------------------------------------------------


@pytest.mark.parametrize("convention", CONVENTIONS)
def test_correct_answer_scores_high(tmp_path: Path, convention: str) -> None:
    """The refutation -- the reported cycle is not real -- is the correct answer.

    A task where the correct answer cannot score is not fixed, it is un-passable
    (see the note in test_report_prompt_echo.py). This is the half that keeps the
    zero-scoring tests below honest.
    """
    got = score(correct_ws(tmp_path), convention, tmp_path)
    assert got >= 0.9, f"correct answer scored {got} under {convention}"


def test_prompt_echo_scores_zero(tmp_path: Path) -> None:
    """The defect that opened the bead: echoing the REAL prompt (task.toml
    [[sessions]].prompt, not the instruction.md stub) used to score 0.84."""
    echo = _session_prompts()
    ws = _write(
        _make_ws(tmp_path, "echo"),
        INVESTIGATION__md=echo,
        CYCLE_VERDICT__json=echo,
        RESOLUTION__json=echo,
    )
    got = score(ws, "runner", tmp_path)
    assert got == 0.0, f"prompt echo scored {got} under {convention}"


def test_comment_only_patch_scores_zero(tmp_path: Path) -> None:
    """The uc12m repro. Echo + one comment in tests/conftest.py scored 1.00/1.00:
    check_fix.sh took bare changed-file membership from `git diff HEAD~1`, so a
    comment in a TEST file paid the full 0.40 fix weight. No diff is graded now."""
    echo = _session_prompts()
    ws = _write(
        _make_ws(tmp_path, "comment"),
        INVESTIGATION__md=echo,
        CYCLE_VERDICT__json=echo,
        RESOLUTION__json=echo,
    )
    repo = ws / "flask"
    (repo / "tests").mkdir()
    (repo / "tests" / "conftest.py").write_text("import pytest\n")
    for cmd in (
        ["git", "init", "-q", "."],
        ["git", "config", "user.email", "t@t.t"],
        ["git", "config", "user.name", "t"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "base"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    (repo / "tests" / "conftest.py").write_text("import pytest\n# a comment\n")
    for cmd in (["git", "add", "-A"], ["git", "commit", "-qm", "comment only"]):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)

    got = score(ws, "runner", tmp_path)
    assert got == 0.0, f"comment-only patch scored {got} under {convention}"


ALL_TRUE_VERDICT = json.dumps(
    {
        "claimed_edges": [
            {"from": f, "to": t, "imported_at_runtime": True}
            for f, t in (
                ("flask", "flask.json"),
                ("flask.json", "flask.globals"),
                ("flask.globals", "flask.app"),
                ("flask.app", "flask.json"),
            )
        ]
    }
)

# The two ways to assert the cycle without having looked: restate the task's own
# old answer key, or rebuild it fluently from words the prompt handed over. The
# gen-1 checks scored both 1.0. They are one test because they are one behaviour --
# measured, not assumed: both produce the identical score vector
# {investigation 0.0, cycle 0.0, resolution 0.0}, for the identical reasons.
FABRICATIONS = {
    "old_answer_key": (
        "# Circular Import Investigation\n\n## Import Cycle\n"
        "flask/__init__.py -> flask/json/__init__.py -> flask/globals.py -> "
        "flask/app.py -> flask/__init__.py\n\n## Affected Modules\n"
        "1. flask/__init__.py\n2. flask/json/__init__.py\n3. flask/globals.py\n"
        "4. flask/app.py\n\n## Severity\nMedium - triggered when importing "
        "flask.json at module level.\n\n## Workaround\nImport inside functions.\n",
        "Modified flask/json/__init__.py to use a lazy import for flask.globals, "
        "breaking the circular dependency.",
    ),
    "prompt_vocabulary": (
        "# Circular Import Investigation\n\nThe import chain flask -> "
        "flask.json -> flask.globals -> flask.app -> flask.json forms a "
        "circular import. The modules involved are flask/__init__.py, "
        "flask/json/__init__.py, flask/globals.py and flask/app.py. The "
        "symbols that trigger the cycle are dumps and current_app. Severity "
        "is medium; the workaround is to import flask.json inside functions "
        "rather than at module level.\n",
        "Break the cycle with a lazy import in flask/json/__init__.py.",
    ),
}


@pytest.mark.parametrize("variant", sorted(FABRICATIONS), ids=sorted(FABRICATIONS))
def test_fabricated_cycle_scores_zero(tmp_path: Path, variant: str) -> None:
    """Asserting the reported cycle is real must earn nothing, however fluently.

    old_answer_key is the task's OWN previous reference answer, which encoded the
    fabrication -- it is now the thing the task exists to catch. prompt_vocabulary
    is the same claim rebuilt from the prompt's words with the right shape and no
    reading.
    """
    investigation, reason = FABRICATIONS[variant]
    ws = _write(
        _make_ws(tmp_path, f"fabricated_{variant}"),
        INVESTIGATION__md=investigation,
        CYCLE_VERDICT__json=ALL_TRUE_VERDICT,
        RESOLUTION__json=json.dumps(
            {"code_change_required": True, "reason": reason}
        ),
    )
    got = score(ws, "runner", tmp_path)
    assert got == 0.0, f"{variant} fabrication scored {got}"




@pytest.mark.parametrize("blanket", [True, False], ids=["all_true", "all_false"])
def test_blanket_edge_verdicts_score_zero(tmp_path: Path, blanket: bool) -> None:
    """Negative marking. 2 of 4 claimed edges are real, so any blanket answer is
    2 right and 2 wrong. Fraction-correct would pay 0.5 of the weightiest
    checkpoint for zero work -- and 'the premise is flagged unconfirmed, so deny
    everything' is exactly the strategy the framing invites. It must pay nothing."""
    ws = _write(
        _make_ws(tmp_path, f"blanket_{blanket}"),
        INVESTIGATION__md="# Report\n\nNothing was checked.\n" * 5,
        CYCLE_VERDICT__json=json.dumps(
            {
                "claimed_edges": [
                    {"from": f, "to": t, "imported_at_runtime": blanket}
                    for f, t in (
                        ("flask", "flask.json"),
                        ("flask.json", "flask.globals"),
                        ("flask.globals", "flask.app"),
                        ("flask.app", "flask.json"),
                    )
                ]
            }
        ),
        RESOLUTION__json=json.dumps({"code_change_required": not blanket, "reason": "."}),
    )
    got = score(ws, "runner", tmp_path)
    assert got == 0.0, f"blanket-{blanket} scored {got} under {convention}"




def test_empty_workspace_scores_zero(tmp_path: Path) -> None:
    got = score(_make_ws(tmp_path, "empty"), "runner", tmp_path)
    assert got == 0.0, f"empty workspace scored {got} under {convention}"


def test_empty_deliverables_score_zero(tmp_path: Path) -> None:
    ws = _write(
        _make_ws(tmp_path, "blank"),
        INVESTIGATION__md="",
        CYCLE_VERDICT__json="",
        RESOLUTION__json="",
    )
    got = score(ws, "runner", tmp_path)
    assert got == 0.0, f"empty deliverables scored {got} under {convention}"


@pytest.mark.parametrize("convention", CONVENTIONS)
def test_correct_answer_tolerates_path_spellings_and_extra_edges(
    tmp_path: Path, convention: str
) -> None:
    """A correct answer must not be failed by cosmetics. Module identity arrives
    as flask.globals, flask/globals.py or src/flask/globals.py, and an agent may
    also report the real (benign) cycles it found. Only the four CLAIMED edges
    are graded; extras are ignored."""
    ws = _write(
        _make_ws(tmp_path, "spellings"),
        INVESTIGATION__md=CORRECT_INVESTIGATION,
        CYCLE_VERDICT__json=json.dumps(
            {
                "claimed_edges": [
                    {
                        "from": "src/flask/__init__.py",
                        "to": "flask/json/__init__.py",
                        "imported_at_runtime": True,
                    },
                    {
                        "from": "flask/json/__init__.py",
                        "to": "src/flask/globals.py",
                        "imported_at_runtime": True,
                    },
                    {
                        # a leading "./" is a natural repo-relative spelling, and
                        # naive path-joining emits "././"; it normalized to
                        # "..flask.globals" and silently missed the key
                        "from": "./flask/globals.py",
                        "to": "flask/app.py",
                        "imported_at_runtime": False,
                    },
                    {
                        "from": "flask.app",
                        "to": "flask.json",
                        "imported_at_runtime": False,
                    },
                    # a real cycle the agent noticed; not one of the claims
                    {"from": "flask", "to": "flask.app", "imported_at_runtime": True},
                ]
            }
        ),
        RESOLUTION__json=CORRECT_RESOLUTION,
    )
    got = score(ws, convention, tmp_path)
    assert got >= 0.9, f"correct answer with alternate spellings scored {got}"


# --- the gate that should have caught this ---------------------------------


def test_chain_echo_payload_is_the_session_prompts_not_the_stub() -> None:
    """Locks the blind spot closed. curated_gate_analyzer copied instruction.md
    as the echo payload, but this task is session_type='chain': its real prompts
    live in task.toml [[sessions]].prompt and its instruction.md was a 4-line
    stub pointing at them. So echo_leak() returned {} ('clean') while the real
    session-prompt echo scored 1.00, and known_prompt_echo_leaks.json stayed [].
    Chain tasks were structurally invisible to the echo gate."""
    payload = gate.agent_prompt_text(TASK_DIR)
    for session in _toml()["sessions"]:
        assert session["prompt"].strip() in payload, (
            "chain echo payload must be the session prompts the agent is really "
            "shown, not the instruction.md stub"
        )


def test_non_chain_payload_is_still_instruction_md() -> None:
    """The chain fix must not change any other task's payload. [task].prompt is
    stale CSB metadata that is never shown to an agent, so resolving it here
    would manufacture phantom leaks across ~155 tasks.

    Swept over EVERY non-chain task rather than one hand-picked fixture. A single
    named task would need a skip-if-absent guard, and this same commit deletes one
    of those from test_grading_asset_seal.py for eroding coverage silently — a
    guard that skips itself when its fixture moves is not a guard.
    """
    checked = 0
    for toml_path in sorted(BENCH.rglob("task.toml")):
        d = toml_path.parent
        if {"_archived", "mined"} & set(d.relative_to(BENCH).parts):
            continue
        instr = d / "instruction.md"
        if not instr.exists() or _load_toml(toml_path).get("sessions"):
            continue
        assert gate.agent_prompt_text(d) == instr.read_text(errors="replace"), (
            f"{d.relative_to(BENCH)} is not a chain task, so its payload must "
            f"still be instruction.md verbatim"
        )
        checked += 1
    assert checked >= 100, (
        f"only {checked} non-chain tasks checked; the sweep is passing vacuously"
    )


def test_echo_gate_now_sees_this_task_as_clean() -> None:
    """End-to-end: the gate's own verdict on the re-scoped task."""
    assert gate.echo_leak(TASK_DIR) == {}


def test_run_checks_actually_reaches_a_workspace_resolving_check(
    tmp_path: Path,
) -> None:
    """Positive control for the gate's OTHER vacuity, which no clean verdict can
    distinguish from a real pass.

    run_checks exported $WORKSPACE but passed no argv[1] and no cwd. A check that
    resolves `WORKSPACE="${1:-.}"` shadows the exported variable with the shell
    assignment, so it read cwd — the repo root — and scored 0.0 for ANY payload.
    Every such task was certified clean because nothing could score, not because an
    echo earned nothing. That is indistinguishable from a real pass at the call
    site, so this drives a probe check that scores 1.0 ONLY if it can actually see
    the materialized deliverable, under the same `${1:-.}` idiom the shipped
    gen-1 checks use (EnterpriseBench-e4w15).
    """
    task = tmp_path / "probe_task"
    (task / "checks").mkdir(parents=True)
    (task / "instruction.md").write_text("probe payload")
    (task / "checks" / "check_probe.sh").write_text(
        '#!/usr/bin/env bash\n'
        'set -euo pipefail\n'
        'WORKSPACE="${1:-.}"\n'
        'if [ -f "$WORKSPACE/report/FINDINGS.md" ]; then\n'
        '  echo \'{"score": 1.0, "message": "saw the workspace"}\'\n'
        'else\n'
        '  echo \'{"score": 0.0, "message": "resolved cwd, not the workspace"}\'\n'
        'fi\n'
    )
    assert gate.deliverable_paths(task) == ["report/FINDINGS.md"]

    ws = tmp_path / "ws"
    gate.materialize(ws, ["report/FINDINGS.md"], "anything")
    scores = gate.run_checks(task, ws)
    assert scores == {"check_probe.sh": 1.0}, (
        "run_checks did not deliver the workspace to a ${1:-.} check — the gate is "
        f"scoring something else and certifying tasks clean vacuously: {scores}"
    )


def test_task_is_inside_the_echo_gate_universe() -> None:
    """deliverable_paths() drives discover_report_tasks(), which parametrizes the
    suite-wide echo test. A check that stops spelling the deliverable as a literal
    $WORKSPACE/... path silently drops the task from that sweep -- passing CI by
    becoming invisible rather than by being clean."""
    assert TASK_DIR in gate.discover_report_tasks()
    assert set(gate.deliverable_paths(TASK_DIR)) == {
        "flask/CYCLE_VERDICT.json",
        "flask/INVESTIGATION.md",
        "flask/RESOLUTION.json",
    }


# --- the grader must not run the agent's code ------------------------------


def test_planted_stdlib_module_cannot_forge_a_verdict(tmp_path: Path) -> None:
    """An agent that drops `json.py` beside its deliverables must not mint its own
    score.

    These checks are bash, but they score via `python3 -c`, and `-c` puts
    sys.path[0]='' — the cwd — ahead of the stdlib. Both Python runners set cwd to
    the agent's workspace, so a planted json.py shadows the real module and the
    check's own `json.dumps` returns whatever the agent wrote. Reproduced before
    the fix: a blanket-true verdict scoring 0.0 came back as
    {"score": 1.0, "detail": "FORGED BY THE AGENT"}.

    This is bead 5cfxa's shadowing class through a different door. runner.py set
    PYTHONSAFEPATH=1 in checkpoint_env, but milestone.py passes no env and
    inherited — uncovered, and unreachable only until these checks became the first
    milestone verifiers to invoke python. scorer_guard.run_verifier_subprocess now
    sets it for every verifier (EnterpriseBench-e4w15).
    """
    ws = _write(
        _make_ws(tmp_path, "planted"),
        INVESTIGATION__md=CORRECT_INVESTIGATION,
        # blanket-true: 2 of 4 right, 2 wrong -> negative marking scores this 0.0
        CYCLE_VERDICT__json=json.dumps(
            {
                "claimed_edges": [
                    {"from": f, "to": t, "imported_at_runtime": True}
                    for f, t in (
                        ("flask", "flask.json"),
                        ("flask.json", "flask.globals"),
                        ("flask.globals", "flask.app"),
                        ("flask.app", "flask.json"),
                    )
                ]
            }
        ),
        RESOLUTION__json=CORRECT_RESOLUTION,
    )
    (ws / "json.py").write_text(
        'def dumps(*a, **k):\n'
        '    return \'{"score": 1.0, "passed": true, "detail": "FORGED"}\'\n'
        'def load(fh, *a, **k):\n'
        '    return {"claimed_edges": []}\n'
    )

    # Drive the real boundary both Python runners share, with milestone.py's exact
    # contract: cwd=workspace, env inherited (no PYTHONSAFEPATH of its own).
    verdict = run_verifier_subprocess(
        "checks/check_cycle.sh",
        base_dir=TASK_DIR,
        argv_suffix=(str(ws),),
        cwd=ws,
        timeout=120,
        checkpoint="cycle_discrimination",
    )
    assert not isinstance(verdict, InfraError), f"probe did not reach a verdict: {verdict}"
    assert verdict["score"] == 0.0, (
        f"a planted json.py forged a verdict: {verdict} — the grader is importing "
        f"the agent's code from its own cwd"
    )
    # Not enough to assert 0.0: a check that never found the deliverable also scores
    # 0.0, so the assertion above would pass vacuously in exactly the failure mode
    # this test exists to detect. Require the detail that only a check which really
    # read and graded the file can print.
    assert "2/4 claimed edges" in verdict["detail"], (
        f"probe scored 0.0 without actually grading the payload — the assertion "
        f"above would pass for the wrong reason: {verdict}"
    )


def test_scorer_guard_isolates_every_verifier_from_the_agents_cwd(
    tmp_path: Path,
) -> None:
    """The BOUNDARY half of the shadowing fix, guarded on its own.

    The task-level test above now passes because these three checks use `python3
    -I`, so it can no longer tell whether scorer_guard still isolates the
    interpreter. That matters: -I protects THESE checks, but PYTHONSAFEPATH at the
    boundary is what protects every other verifier and every future milestone check
    that forgets -I. Without this test the boundary fix could be reverted and the
    suite would stay green (EnterpriseBench-e4w15).

    Drives a probe verifier that reports the env it actually received.
    """
    probe_task = tmp_path / "probe_task"
    (probe_task / "checks").mkdir(parents=True)
    (probe_task / "checks" / "check_env.sh").write_text(
        '#!/usr/bin/env bash\n'
        'printf \'{"score": %s, "passed": true, "detail": "safepath=%s"}\\n\' \\\n'
        '  "$([ "${PYTHONSAFEPATH:-unset}" = "1" ] && echo 1.0 || echo 0.0)" \\\n'
        '  "${PYTHONSAFEPATH:-unset}"\n'
    )
    verdict = run_verifier_subprocess(
        "checks/check_env.sh",
        base_dir=probe_task,
        argv_prefix=("bash",),
        cwd=tmp_path,
        timeout=60,
        checkpoint="probe",
    )
    assert not isinstance(verdict, InfraError), verdict
    assert verdict["score"] == 1.0, (
        f"run_verifier_subprocess did not set PYTHONSAFEPATH=1: {verdict}. Every "
        f"verifier runs with cwd=the agent's workspace, so without it a bash check "
        f"that shells out to python3 imports the agent's code from sys.path[0]."
    )


# --- task-definition invariants --------------------------------------------


def test_no_check_grades_a_git_diff() -> None:
    """The fix vector was `git diff --name-only HEAD~1 | grep '\\.py$'` -- bare
    changed-file membership, which cannot tell a fix from a comment because it
    never reads the code's meaning. Grading the decision instead of the footprint
    is what removes it; this asserts it does not come back."""
    for sh in sorted((TASK_DIR / "checks").glob("*.sh")):
        body = sh.read_text()
        assert "git diff" not in body, f"{sh.name} grades a diff again"


def test_ground_truth_does_not_assert_the_fabricated_cycle() -> None:
    gt = _ground_truth()
    assert gt.get("cycle_exists") is False
    assert gt.get("code_change_required") is False
    runtime = {
        (e["from"], e["to"]) for e in gt["claimed_edges"] if e["imported_at_runtime"]
    }
    assert runtime == {("flask", "flask.json"), ("flask.json", "flask.globals")}


def test_task_does_not_require_a_code_patch_artifact() -> None:
    """`artifacts.required = ["code_patch"]` asserted a patch that must not exist:
    the correct answer changes no code."""
    assert "code_patch" not in _toml().get("artifacts", {}).get("required", [])


def test_simulation_encodes_the_correct_answer() -> None:
    """--simulate must exercise the correct answer, not the fabrication it used to
    hardcode (a lazy-import FIX_SUMMARY for a cycle that does not exist).

    Asserted on the parsed deliverables, not on prose: the correct resolution
    REFUSES a lazy-import patch and says so, so banning the phrase would fail the
    right answer for describing what it declined to do.
    """
    toml = _toml()
    actions = {
        a["file"]: a["content"]
        for key in ("session_1", "session_2")
        for a in toml["simulation"][key]["actions"]
    }
    key = {(e["from"], e["to"]): e["imported_at_runtime"] for e in _ground_truth()["claimed_edges"]}

    verdict = json.loads(actions["CYCLE_VERDICT.json"])
    assert {
        (e["from"], e["to"]): e["imported_at_runtime"] for e in verdict["claimed_edges"]
    } == key, "simulated session 1 must answer every claimed edge as ground_truth does"

    resolution = json.loads(actions["RESOLUTION.json"])
    assert resolution["code_change_required"] is False
    assert "type_checking" in resolution["reason"].lower()
    assert "type_checking" in actions["INVESTIGATION.md"].lower()


def test_every_check_is_claimed_by_a_checkpoint() -> None:
    """run_task.py stages EVERY checks/*.sh into .verifiers/ but writes a .meta
    weight only for scripts a [[checkpoints]].verifier names, and test_runner.sh
    defaults a missing weight to 1.0. So a check left behind by a rename -- or one
    reachable only from a milestone -- is scored at weight 1.0 and pushes
    task_score above 1.0 with nothing raising. Holds for all 141 tasks today."""

    def vname(p: str) -> str:
        stem = Path(p).stem
        return stem[len("check_") :] if stem.startswith("check_") else stem

    offenders: list[str] = []
    for toml_path in sorted(BENCH.rglob("task.toml")):
        d = toml_path.parent
        if {"_archived", "mined"} & set(d.relative_to(BENCH).parts):
            continue
        checks = d / "checks"
        if not checks.is_dir():
            continue
        scripts = {vname(p.name) for p in checks.glob("*.sh")}
        if not scripts:
            continue
        data = tomllib.load(open(toml_path, "rb"))
        claimed = {
            vname(c["verifier"]) for c in data.get("checkpoints", []) if c.get("verifier")
        }
        if scripts - claimed or claimed - scripts:
            offenders.append(
                f"{d.relative_to(BENCH)}: unclaimed={sorted(scripts - claimed)} "
                f"missing={sorted(claimed - scripts)}"
            )
    assert not offenders, "checks/ and [[checkpoints]] must correspond: " + "; ".join(
        offenders
    )
