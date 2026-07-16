"""Every check must emit a verdict the PRODUCTION scorer can actually read.

A check can print a syntactically perfect ``{"score": 1.0}`` and still be
unscorable. ``test_runner.sh:parse_score`` credits a score only when the payload
is one closed root value with nothing beside it, so a subprocess that writes to
the check's stdout before the verdict (pytest, a compiler, a linter) costs the
checkpoint its verdict: it routes to ``verifier_infra_error`` on EVERY run, for
a correct agent exactly as much as for a no-op one.

That failure is silent from both ends. Production sees "no verdict" and blames
infra; ``curated_gate_analyzer.run_checks`` catches the JSONDecodeError, records
``None``, and ``echo_leak`` drops ``None`` as "not exercised" — so the
prompt-echo gate reads a broken check as clean. ansible-galaxy-tar-regression-
prove-001's check_test_fails.sh sat in exactly that blind spot: unscorable in
production while grading 1.0 for a prompt copy underneath, where neither gate
could see it (EnterpriseBench-jn73.2.7.3.1).

So the property is not "the check prints JSON" but "the scorer that credits it
in production can read what it prints". This test asserts it against the real
``parse_score``, never a reimplementation — a copy would drift from the awk
grammar and re-open the blind spot it exists to close.

A check that stays silent is out of scope here: no output is the never-ran mode
scorer_guard's attestation already fails closed on.

Tracking: EnterpriseBench-jn73.2.7.3.1.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
import curated_gate_analyzer as gate  # noqa: E402

TEST_RUNNER = REPO_ROOT / "scripts" / "sandbox" / "test_runner.sh"


def _parse_score_source() -> str:
    """Lift parse_score out of test_runner.sh verbatim.

    Located by name and closed on the first column-0 `}` — brace counting would
    swallow the rest of the file, since parse_score's body is an awk program
    whose braces are not shell braces.
    """
    lines = TEST_RUNNER.read_text().splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("parse_score() {"))
        end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
    except StopIteration:  # pragma: no cover
        pytest.fail(
            f"parse_score() not found in {TEST_RUNNER}. If it was renamed or "
            f"reshaped, repoint this test at the real scorer — do not reimplement it."
        )
    return "\n".join(lines[start:end + 1])


PARSE_SCORE_SRC = _parse_score_source()


def _parse_score(text: str) -> str:
    """What production would credit for this stdout ('' = no verdict)."""
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(PARSE_SCORE_SRC + "\n")
        lib = fh.name
    try:
        r = subprocess.run(
            ["bash", "-c", f'source "{lib}"; parse_score "$1"', "_", text],
            capture_output=True, text=True, timeout=60,
        )
        return r.stdout.strip()
    finally:
        os.unlink(lib)


def _check_outputs(task_dir: Path) -> dict[str, str]:
    """Every check's stdout under the md-echo vector (any deliverable will do:
    we are grading the verdict's SHAPE, not its score)."""
    deliverables = gate.deliverable_paths(task_dir)
    instr = task_dir / "instruction.md"
    if not deliverables or not instr.exists():
        return {}
    out: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        gate.materialize(ws, deliverables, instr.read_text(errors="replace"))
        env = {**os.environ, "WORKSPACE": str(ws), "TASK_DIR": str(task_dir)}
        for sh in sorted((task_dir / "checks").glob("*.sh")):
            try:
                p = subprocess.run(
                    ["bash", str(sh)], capture_output=True, text=True,
                    timeout=gate.CHECK_TIMEOUT, env=env,
                )
            except subprocess.TimeoutExpired:
                continue
            if p.stdout.strip():
                out[sh.name] = p.stdout.strip()
    return out


REPORT_TASKS = gate.discover_report_tasks()
TASK_IDS = [str(d.relative_to(gate.BENCH)) for d in REPORT_TASKS]


@pytest.mark.parametrize("task_rel", TASK_IDS)
def test_check_verdicts_are_readable_by_the_production_scorer(task_rel: str) -> None:
    unreadable = {
        name: out.splitlines()[-1][:120]
        for name, out in _check_outputs(gate.BENCH / task_rel).items()
        if not _parse_score(out)
    }
    assert not unreadable, (
        f"{task_rel}: parse_score cannot credit these verdicts, so every run "
        f"routes them to verifier_infra_error regardless of the agent: "
        f"{unreadable}. Usually a subprocess writing to the check's stdout — "
        f"capture it (>/dev/null 2>&1) and print only the JSON verdict."
    )


def test_parse_score_grammar_still_holds() -> None:
    """Guards the lift above: if these stop holding, PARSE_SCORE_SRC is not the
    real parser and every assertion in this module is vacuous."""
    assert _parse_score('{"score": 1.0, "passed": true}') == "1.0"
    assert _parse_score('INFO starting\n{"score": 1.0}') == ""
    assert _parse_score('{"score": 1.0} {"score": 0.0}') == ""
    assert _parse_score("") == ""
