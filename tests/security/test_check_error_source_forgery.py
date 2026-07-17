"""Regression test for EnterpriseBench-qvpzt — forgeable verifier verdict.

``check_error_source.sh`` extracted agent-controlled file paths from answer.json
via a safe ``json.load`` subprocess into the bash var ``$AGENT_FILES``, then
re-embedded that var UNESCAPED inside a Python triple-quoted string literal in a
third ``python3 -c`` block::

    agent_files = '''$AGENT_FILES'''.strip().split('\n')

Bash substitutes ``$AGENT_FILES`` before Python parses it, so an answer.json
``source_files`` entry containing ``'''`` closes the string and the rest becomes
literal Python source. This is strictly worse than an infra escape: the agent
forges a PASSING score. The fix passes the file lists through ``os.environ`` (the
pattern the two earlier subprocesses in the same file already use) so the payload
is read back as an opaque string that can never be code.

These tests drive the REAL check scripts with the exploit payload from the bead
and assert the forged ``{"score": 1.0, "passed": true, "detail": "forged"}``
verdict is not produced. They fail against the vulnerable template and pass once
the interpolation is removed.

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


def _dynamic_scripts() -> list[Path]:
    """Active scripts that inline their scoring, so the exploit payload can be
    driven end-to-end with a simple ``{"path": ...}`` ground truth.

    Some active scripts instead ``exec python3 -m eb_verify.scorers.file_extraction``
    (e.g. the httpx tri/dual tasks). Those delegate scoring to the eb_verify
    package, which the harness makes importable via ``PYTHONPATH`` and which
    expects a repo-qualified ground-truth schema — driving them here would test
    the harness wiring, not the interpolation vector this bead is about. They
    are covered by ``tests/test_file_extraction.py`` and, for the injection
    pattern specifically, by ``test_no_source_injection_pattern`` below (which
    still scans every script). They are not interpolation-vulnerable: module
    delegation reads the answer as data, never as source.
    """
    return [s for s in _active_scripts() if "python3 -m eb_verify" not in s.read_text()]


def _all_scripts() -> list[Path]:
    """Active + archived copies — the full blast radius named in the bead."""
    return sorted(
        [
            *BENCHMARKS.glob("customer_escalation/*/checks/check_error_source.sh"),
            *BENCHMARKS.glob(
                "_archived/customer_escalation/*/checks/check_error_source.sh"
            ),
        ]
    )


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


def test_scripts_are_discovered() -> None:
    """Guard against a rename silently emptying the parametrized suites — a
    zero-case parametrize is a false-green regression test."""
    assert _all_scripts(), "no check_error_source.sh scripts found under benchmarks/"
    assert _dynamic_scripts(), "no inline-scoring check_error_source.sh scripts found"


@pytest.mark.security
@pytest.mark.parametrize(
    "script", _all_scripts(), ids=lambda p: str(p.relative_to(BENCHMARKS))
)
def test_no_source_injection_pattern(script: Path) -> None:
    """The ``'''$VAR'''`` shell-into-Python interpolation must be gone entirely.

    Matches ``'''`` followed by optional whitespace and a ``$`` so a reformatted
    ``''' $VAR`` cannot slip past this regression guard.
    """
    assert not re.search(r"'''\s*\$", script.read_text()), (
        f"{script.relative_to(ROOT)} still interpolates a bash var into a Python "
        "triple-quoted literal — the forgeable-verdict vector (qvpzt)."
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
    assert not (result.get("score") == 1.0 and result.get("passed") is True), (
        f"{script.relative_to(ROOT)} forged a passing verdict from an answer that "
        f"names no required file: {result!r}"
    )
    # The payload is an opaque, non-matching path: the only correct score is 0.
    assert (
        result["score"] == 0.0
    ), f"{script.relative_to(ROOT)} scored a non-file payload: {result!r}"
    assert result["passed"] is False


@pytest.mark.security
def test_benign_answer_still_scores(tmp_path: Path) -> None:
    """A legitimate answer naming the required file must still score 1.0.

    Guards against the fix breaking real scoring — the os.environ round-trip
    must preserve the file lists exactly.
    """
    script = (
        BENCHMARKS
        / "customer_escalation/err-provenance-01/checks/check_error_source.sh"
    )
    proc = _run(
        script,
        tmp_path,
        answer={"source_files": ["pkg/apis/batch/validation/validation.go"]},
        ground_truth=GROUND_TRUTH,
    )
    result = _parse(proc)
    assert result["score"] == 1.0
    assert result["passed"] is True
