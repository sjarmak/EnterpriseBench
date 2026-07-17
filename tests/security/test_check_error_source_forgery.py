"""Regression test for EnterpriseBench-qvpzt — forgeable verifier verdict.

``check_error_source.sh`` extracted agent-controlled file paths from answer.json
via a safe ``json.load`` subprocess into the bash var ``$AGENT_FILES``, then
re-embedded that var UNESCAPED inside a Python triple-quoted string literal in a
third ``python3 -c`` block::

    agent_files = '''$AGENT_FILES'''.strip().split('\n')

Bash substitutes ``$AGENT_FILES`` before Python parses it, so an answer.json
``source_files`` entry containing ``'''`` closes the string and the rest becomes
literal Python source. This is strictly worse than an infra escape: the agent
forges a PASSING score.

Relationship to ``test_check_scripts_injection.py`` (bead 0rv.23): that module is
the broad 37-script suite for the same injection class, but it depends on
committed benchmark fixtures that are currently missing (bead g165d), so its
dynamic cases are red in a clean checkout. This module is deliberately
self-contained — it synthesises its own ``workspace``/``task`` inputs under
``tmp_path`` — so it stays green and is the working end-to-end proof for the
forged-verdict vector on the ``check_error_source.sh`` scripts specifically,
including the archived copies that the 0rv.23 suite does not cover.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
BENCHMARKS = ROOT / "benchmarks"

# The exact payload from the bead repro: it closes the '''...''' literal, prints
# a fully-forged passing verdict, and sys.exit(0)s before the real score runs.
FORGERY_PAYLOAD = (
    "x''';import sys,json;"
    "print(json.dumps({'score':1.0,'passed':True,'detail':'forged'}));"
    "sys.exit(0)#"
)

# Ground truth requiring a file the forged answer never legitimately names, so a
# correct grader must score 0/1 — any pass here is the forgery leaking through.
GROUND_TRUTH = {"required_files": [{"path": "pkg/apis/batch/validation/validation.go"}]}


def _active_scripts() -> list[Path]:
    return sorted(BENCHMARKS.glob("customer_escalation/*/checks/check_error_source.sh"))


def _all_scripts() -> list[Path]:
    """Active + archived copies — the full blast radius named in the bead."""
    return sorted(
        [
            *_active_scripts(),
            *BENCHMARKS.glob(
                "_archived/customer_escalation/*/checks/check_error_source.sh"
            ),
        ]
    )


def _delegates_to_module(text: str) -> bool:
    """True if the script actually ``exec``s the ``eb_verify`` scorer module.

    Such scripts read the answer as data, never as source, so they are not
    interpolation-vulnerable and are covered by ``tests/test_file_extraction.py``.

    Comment content is stripped before the scan (everything after the first
    ``#`` on each line): a whole-file substring match would misclassify a script
    that merely *mentions* the delegation pattern in a header comment as a safe
    delegator and silently drop it from the end-to-end forgery suite. Erring
    toward inclusion — a trailing ``# ... python3 -m eb_verify`` comment on a
    real code line drops that line's tail and the script stays in the suite — is
    the safe direction for a security guard.
    """
    return any(
        "python3 -m eb_verify" in line.split("#", 1)[0] for line in text.splitlines()
    )


def _dynamic_scripts() -> list[Path]:
    """Inline-scoring scripts across the full blast radius (active + archived),
    so the exploit payload — and the benign round-trip — can be driven
    end-to-end with a simple ``{"path": ...}`` ground truth.

    Scripts that delegate to ``eb_verify.scorers.file_extraction`` are excluded
    (see ``_delegates_to_module``); ``test_no_source_injection_pattern`` still
    scans every script, delegators included, statically.
    """
    return [s for s in _all_scripts() if not _delegates_to_module(s.read_text())]


# A bash var interpolated into a Python string literal is the forgeable-verdict
# vector (qvpzt). Match the extracted-content vars (``$AGENT_FILES`` /
# ``$GT_FILES`` — the agent-controlled values pulled out of answer.json) wrapped
# in ANY Python string opener: single, double, or triple quotes, optionally
# braced (``${AGENT_FILES}``). Anchoring on the var name — rather than any
# quote-then-``$`` — is deliberate: the safe template exports paths bash-side
# (``export ANSWER_FILE="$WORKSPACE/..."``), so a bare ``"$`` pattern would
# false-positive on every script. Only the plural extracted-content vars carry
# untrusted answer bytes into the interpreter.
INJECTION_RE = re.compile(r"""['"]{1,3}\s*\$\{?(?:AGENT_FILES|GT_FILES)\b""")


def _run(
    script: Path,
    tmp_path: Path,
    *,
    answer: object,
    ground_truth: Mapping[str, object],
) -> subprocess.CompletedProcess[str]:
    workspace = tmp_path / "workspace"
    task_dir = tmp_path / "task"
    (workspace / "agent_output").mkdir(parents=True)
    task_dir.mkdir(parents=True)

    (task_dir / "ground_truth.json").write_text(json.dumps(ground_truth))
    (workspace / "agent_output" / "answer.json").write_text(json.dumps(answer))

    env = os.environ.copy()
    env["WORKSPACE"] = str(workspace)
    env["TASK_DIR"] = str(task_dir)
    return subprocess.run(
        ["bash", str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _parse(proc: subprocess.CompletedProcess[str]) -> dict[str, object]:
    stdout = proc.stdout.strip()
    assert stdout, f"no stdout (stderr={proc.stderr!r})"
    result: dict[str, object] = json.loads(stdout.splitlines()[-1])
    return result


@pytest.mark.security
def test_scripts_are_discovered() -> None:
    """Guard against a rename silently emptying the parametrized suites — a
    zero-case parametrize is a false-green regression test.

    Marked ``security`` so ``pytest -m security`` — the selector a security
    sweep runs — cannot deselect the vacuity guard that keeps the parametrized
    security tests non-empty.
    """
    assert _all_scripts(), "no check_error_source.sh scripts found under benchmarks/"
    assert _dynamic_scripts(), "no inline-scoring check_error_source.sh scripts found"


@pytest.mark.security
@pytest.mark.parametrize(
    "script", _all_scripts(), ids=lambda p: str(p.relative_to(BENCHMARKS))
)
def test_no_source_injection_pattern(script: Path) -> None:
    """The shell-into-Python interpolation must be gone entirely, in every
    quote spelling.

    ``INJECTION_RE`` matches ``$AGENT_FILES``/``$GT_FILES`` wrapped in single,
    double, or triple quotes (optionally braced), so a reformatted
    ``'$AGENT_FILES'`` — a single-quoted reintroduction equally injectable
    inside a bash-double-quoted ``python3 -c`` block — cannot slip past this
    guard the way it slipped past the original triple-quote-only regex.
    """
    assert not INJECTION_RE.search(script.read_text()), (
        f"{script.relative_to(ROOT)} still interpolates an agent-controlled bash "
        "var into a Python string literal — the forgeable-verdict vector (qvpzt)."
    )


@pytest.mark.security
@pytest.mark.parametrize(
    "script", _dynamic_scripts(), ids=lambda p: str(p.relative_to(BENCHMARKS))
)
def test_forged_verdict_not_produced(script: Path, tmp_path: Path) -> None:
    """The bead's exploit payload must not forge a passing verdict."""
    proc = _run(
        script,
        tmp_path,
        answer={"source_files": [FORGERY_PAYLOAD]},
        ground_truth=GROUND_TRUTH,
    )
    result = _parse(proc)

    assert result.get("detail") != "forged", (
        f"{script.relative_to(ROOT)} emitted the agent-injected 'forged' detail — "
        "the payload executed as Python source."
    )
    # The payload is an opaque, non-matching path: the only correct score is 0.
    assert (
        result["score"] == 0.0
    ), f"{script.relative_to(ROOT)} scored a non-file payload: {result!r}"
    # passed is the field the harness consumes and the one an attacker wants
    # flipped — assert it directly rather than deriving it from score.
    assert result["passed"] is False


@pytest.mark.security
@pytest.mark.parametrize(
    "script", _dynamic_scripts(), ids=lambda p: str(p.relative_to(BENCHMARKS))
)
def test_benign_answer_still_scores(script: Path, tmp_path: Path) -> None:
    """A legitimate answer naming the required file must still score 1.0 — in
    EVERY inline-scoring script, not just one hand-picked one.

    This is the positive-path counterpart to ``test_forged_verdict_not_produced``,
    and the two are load-bearing together. Every forgery assertion there is
    negative (score 0.0 / passed False), which an all-zeros *bricked* grader
    also satisfies: e.g. dropping the ``export GT_FILES`` that the os.environ
    fix depends on degrades the env round-trip to ``detail='No GT files'``,
    score 0.0, passed False — for a correct answer, silently, with exit 0.
    Parametrizing the benign round-trip across the full blast radius means a
    grader bricked to all-zeros in ANY of the inline scripts goes red here
    rather than passing the negative-only forgery suite. It also guards the
    os.environ round-trip preserving the file lists exactly.
    """
    proc = _run(
        script,
        tmp_path,
        answer={"source_files": ["pkg/apis/batch/validation/validation.go"]},
        ground_truth=GROUND_TRUTH,
    )
    result = _parse(proc)
    assert result["score"] == 1.0, (
        f"{script.relative_to(ROOT)} failed to score a correct benign answer — "
        f"a grader bricked to all-zeros defeats the negative-only forgery suite: "
        f"{result!r}"
    )
    assert result["passed"] is True
