"""Regression tests for bead 0rv.23 — Python injection in check scripts.

Covers 37 file-extraction check scripts whose original implementation
shell-interpolated agent-controlled JSON content into a Python triple-quoted
string literal (``'''$AGENT_FILES'''``). An agent writing ``'''`` into a path
inside answer.json could close the string and execute arbitrary Python under
the task runner uid.

These tests enforce four invariants:

1. The vulnerable ``'''$`` shell-interpolation pattern does not appear in any
   of the 37 target scripts.
2. All 37 target scripts use the single-process safe template (identified by
   the presence of ``os.environ['ANSWER_FILE']`` inside one ``python3 -c``
   block and ``json.JSONDecodeError`` handling).
3. The two genuinely safe keyword-overlap scripts in
   ``support-mapping-dual-spring-kafka-001`` are not touched (SHA256 snapshot).
4. Running a representative script against adversarial answer.json payloads
   must not execute injected code, must not silently bypass scoring via
   ``sys.exit``, and must not count substring-only path-spam matches.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
BENCHMARKS = ROOT / "benchmarks"


# ---------------------------------------------------------------------------
# Target file inventory (37 active vulnerable scripts across 19 dirs)
# ---------------------------------------------------------------------------

# Group A: 9 dual-repo dirs where ALL 3 check_*.sh scripts are vulnerable.
_GROUP_A_DIRS = [
    "dependency_management/dep-graph-dual-nextjs-swc-001",
    "technical_debt/refactor-dual-flask-werkzeug-001",
    "technical_debt/dead-code-dual-spring-hibernate-001",
    "technical_debt/dead-code-dual-django-wagtail-001",
    "incident_response/incident-investigation-dual-django-celery-001",
    "platform_engineering/config-drift-dual-webpack-babel-001",
    "platform_engineering/config-drift-dual-tokio-hyper-001",
    "feature_delivery/schema-evolution-dual-spring-flyway-001",
    "customer_escalation/support-mapping-dual-nextjs-webpack-001",
]

# Group B: 7 dual-repo dirs where ONLY check_error_source.sh is vulnerable.
_GROUP_B_DIRS = [
    "customer_escalation/support-mapping-dual-spring-kafka-001",
    "customer_escalation/support-mapping-dual-ansible-001",
    "customer_escalation/err-provenance-dual-celery-001",
    "customer_escalation/err-provenance-dual-docker-001",
    "customer_escalation/err-provenance-dual-grafana-001",
    "customer_escalation/err-provenance-dual-requests-001",
    "customer_escalation/err-provenance-dual-terraform-001",
]

# Group C: 3 single-repo err-provenance tasks, only check_error_source.sh.
_GROUP_C_PATHS = [
    BENCHMARKS
    / "customer_escalation"
    / f"err-provenance-{n:02d}"
    / "checks"
    / "check_error_source.sh"
    for n in (1, 2, 3)
]

TARGET_FILES: list[Path] = [
    *(
        p
        for d in _GROUP_A_DIRS
        for p in sorted((BENCHMARKS / d / "checks").glob("check_*.sh"))
    ),
    *(BENCHMARKS / d / "checks" / "check_error_source.sh" for d in _GROUP_B_DIRS),
    *_GROUP_C_PATHS,
]


# Scripts that are already safe (keyword-overlap algorithm, not file-extraction)
# and MUST NOT be modified by the rewrite.
SAFE_SNAPSHOTS: dict[Path, str] = {
    BENCHMARKS
    / "customer_escalation/support-mapping-dual-spring-kafka-001/checks/check_error_chain.sh": (
        "cb85ffd9e98553b27d56fcd79d44b389ffec463f52bee23eac8543c639cc80a7"
    ),
    BENCHMARKS
    / "customer_escalation/support-mapping-dual-spring-kafka-001/checks/check_trigger_conditions.sh": (
        "c16c6de7666178347efc2af941015ec33e8cf318d886f6199182313247dab83a"
    ),
}

REPRESENTATIVE = (
    BENCHMARKS
    / "platform_engineering/config-drift-dual-tokio-hyper-001/checks/check_config_valid.sh"
)


# ---------------------------------------------------------------------------
# Inventory sanity (catches scope drift before anything else runs)
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_target_file_count_is_37() -> None:
    """If this fails, either the scope changed or a directory was renamed."""
    assert len(TARGET_FILES) == 37, (
        f"expected 37 vulnerable files, found {len(TARGET_FILES)}: "
        f"{[str(p.relative_to(ROOT)) for p in TARGET_FILES]}"
    )


@pytest.mark.security
def test_all_target_files_exist() -> None:
    missing = [str(p.relative_to(ROOT)) for p in TARGET_FILES if not p.exists()]
    assert not missing, f"target files missing from disk: {missing}"


@pytest.mark.security
def test_safe_snapshot_files_exist() -> None:
    missing = [str(p.relative_to(ROOT)) for p in SAFE_SNAPSHOTS if not p.exists()]
    assert not missing, f"safe snapshot files missing: {missing}"


# ---------------------------------------------------------------------------
# Invariant 1: no ''' $ shell interpolation pattern anywhere in scope
# ---------------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.parametrize(
    "script", TARGET_FILES, ids=lambda p: str(p.relative_to(BENCHMARKS))
)
def test_no_triple_quote_shell_interpolation(script: Path) -> None:
    """The core injection vector: ``'''$VAR''' `` in a python3 -c string."""
    content = script.read_text()
    assert "'''$" not in content, (
        f"{script.relative_to(ROOT)} still uses triple-quote shell interpolation — "
        "this is the shell-injection vulnerability from bead 0rv.23."
    )


# ---------------------------------------------------------------------------
# Invariant 2: safe-template markers present in all target files
# ---------------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.parametrize(
    "script", TARGET_FILES, ids=lambda p: str(p.relative_to(BENCHMARKS))
)
def test_script_uses_safe_template(script: Path) -> None:
    content = script.read_text()

    # Safe template markers
    assert (
        "os.environ['ANSWER_FILE']" in content or 'os.environ["ANSWER_FILE"]' in content
    ), f"{script.relative_to(ROOT)} does not read ANSWER_FILE via os.environ"
    assert (
        "JSONDecodeError" in content
    ), f"{script.relative_to(ROOT)} does not handle malformed JSON"

    # There must be exactly ONE python3 -c invocation in the body (single-process),
    # not three as in the vulnerable template.
    py_invocations = content.count("python3 -c")
    assert py_invocations == 1, (
        f"{script.relative_to(ROOT)} has {py_invocations} python3 -c invocations; "
        "safe template must have exactly 1."
    )

    # Tightened match (not unanchored substring)
    assert "gt_f in af" not in content, (
        f"{script.relative_to(ROOT)} still uses unanchored substring match "
        "(gt_f in af). This permits path-spam soft-cheating — tighten to "
        "(af == gt_f or af.endswith('/' + gt_f))."
    )


# ---------------------------------------------------------------------------
# Invariant 3: safe scripts are not touched
# ---------------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.parametrize(
    "script,expected_sha256",
    list(SAFE_SNAPSHOTS.items()),
    ids=lambda x: (
        str(x)[-60:] if isinstance(x, str) else str(x.relative_to(BENCHMARKS))
    ),
)
def test_safe_keyword_scripts_unchanged(script: Path, expected_sha256: str) -> None:
    actual = hashlib.sha256(script.read_bytes()).hexdigest()
    assert actual == expected_sha256, (
        f"{script.relative_to(ROOT)} changed unexpectedly. "
        f"Expected SHA256={expected_sha256}, got {actual}. "
        "These keyword-overlap scripts are already safe and MUST NOT be "
        "overwritten by the security rewrite."
    )


# ---------------------------------------------------------------------------
# Invariant 4: adversarial payload suite on a representative script
# ---------------------------------------------------------------------------


def _run_check(
    script: Path,
    tmp_path: Path,
    *,
    answer: object | None,
    ground_truth: dict,
    write_malformed: str | None = None,
) -> subprocess.CompletedProcess:
    """Invoke a check script with synthesized fixtures under tmp_path."""
    workspace = tmp_path / "workspace"
    task_dir = tmp_path / "task"
    (workspace / "agent_output").mkdir(parents=True)
    task_dir.mkdir(parents=True)

    gt_path = task_dir / "ground_truth.json"
    gt_path.write_text(json.dumps(ground_truth))

    answer_path = workspace / "agent_output" / "answer.json"
    if write_malformed is not None:
        answer_path.write_text(write_malformed)
    elif answer is not None:
        answer_path.write_text(json.dumps(answer))
    # else: leave missing on purpose

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


def _parse_score(proc: subprocess.CompletedProcess) -> dict:
    """Scripts print a single JSON line to stdout. Parse it or fail loudly."""
    stdout = proc.stdout.strip()
    assert stdout, f"no stdout from script (stderr={proc.stderr!r})"
    # Take the last line — some runners prepend warnings.
    last_line = stdout.splitlines()[-1]
    return json.loads(last_line)


GT_THREE_FILES = {
    "required_files": [
        {"path": "src/hyper/conn/http1.rs"},
        {"path": "tokio/runtime/scheduler.rs"},
        {"path": "hyper/server/builder.rs"},
    ]
}


@pytest.fixture
def run_check(
    tmp_path: Path,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Run the representative script against GT_THREE_FILES with the given answer.

    Returns the CompletedProcess so callers can inspect stdout/stderr/returncode.
    """

    def _run(
        *, answer: object | None = None, write_malformed: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return _run_check(
            REPRESENTATIVE,
            tmp_path,
            answer=answer,
            ground_truth=GT_THREE_FILES,
            write_malformed=write_malformed,
        )

    return _run


@pytest.mark.security
def test_benign_fixture_scores_two_of_three(run_check) -> None:
    proc = run_check(
        answer={
            "source_files": [
                "src/hyper/conn/http1.rs",
                "tokio/runtime/scheduler.rs",
                "unrelated/file.rs",
            ]
        }
    )
    result = _parse_score(proc)
    assert result["score"] == pytest.approx(0.67, abs=0.01)
    assert result["passed"] is True


@pytest.mark.security
def test_missing_answer_file_returns_zero(run_check) -> None:
    proc = run_check(answer=None)
    result = _parse_score(proc)
    assert result["score"] == 0.0
    assert result["passed"] is False
    # Missing fixture is an agent failure, not infra — must exit 0.
    assert proc.returncode == 0


@pytest.mark.security
def test_malformed_json_does_not_crash(run_check) -> None:
    proc = run_check(write_malformed="{not: valid, json")
    result = _parse_score(proc)
    assert result["score"] == 0.0
    assert result["passed"] is False


@pytest.mark.security
def test_triple_quote_injection_blocked(run_check, tmp_path: Path) -> None:
    """Agent writes a path that breaks out of ``'''$AGENT_FILES'''`` interpolation.

    The payload is crafted to survive Python parsing so a concrete side effect
    (creation of ``canary``) can be observed:

      '''+str(__import__('os').system('touch <canary>'))+'''

    When shell-interpolated into ``agent_files = '''<paths>'''``, this produces
    a valid Python expression::

      agent_files = '''\\n'''+str(os.system('touch <canary>'))+'''\\n...\\n'''

    which at runtime evaluates the system() call (creating canary), concatenates
    str(0), and resumes the original string.  On the SAFE template there is no
    shell interpolation at all: the payload is treated as an opaque file path.
    """
    canary = tmp_path / "pwned_triple_quote"
    # os.system is used instead of pathlib.touch to keep the injected
    # expression a simple str-concat that Python can parse and execute.
    injected = "'''+str(__import__('os').system('touch " + str(canary) + "'))+'''"
    proc = run_check(
        answer={
            "source_files": [
                injected,
                "/workspace/hyper/src/hyper/conn/http1.rs",
            ]
        }
    )

    assert not canary.exists(), (
        f"triple-quote injection executed code: canary {canary} was created. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    # Safe template must still produce valid JSON output even with a weird
    # path in the answer — no crash, no empty stdout.
    assert proc.stdout.strip(), (
        f"check script produced empty stdout on injection payload "
        f"(stderr={proc.stderr!r}) — payload may have crashed the Python "
        "process in a way that indicates partial vulnerability."
    )
    result = _parse_score(proc)
    # The injected string is not a real path — it must not score.
    # The second file IS a legit suffix match, so score should be 1/3.
    assert result["score"] == pytest.approx(1 / 3, abs=0.01)


@pytest.mark.security
def test_sys_exit_injection_blocked(run_check) -> None:
    """Agent tries to short-circuit scoring via ``sys.exit(0)``.

    Under the vulnerable template, the injected string ends up inside a Python
    process whose sys.exit could terminate before printing the score.  The safe
    template must score the answer regardless of what's in the paths.
    """
    injected = "'''; import sys; sys.exit(0); x='"
    proc = run_check(answer={"source_files": [injected]})
    # Guard against silent bypass: under the vulnerable template this payload
    # causes sys.exit(0) mid-Python, producing empty stdout and a zero exit.
    # Assert on stdout directly so the failure message names the real issue.
    assert proc.stdout.strip(), (
        "sys.exit injection produced empty stdout — the injected payload "
        f"terminated the Python process before scoring. stderr={proc.stderr!r}"
    )
    result = _parse_score(proc)
    assert result["score"] == 0.0  # no valid paths matched


@pytest.mark.security
def test_path_traversal_payload_not_executed(run_check) -> None:
    """``../../etc/passwd`` in source_files must be treated as an opaque string."""
    proc = run_check(answer={"source_files": ["../../etc/passwd", "/etc/passwd"]})
    result = _parse_score(proc)
    assert result["score"] == 0.0


@pytest.mark.security
def test_type_confusion_does_not_crash(run_check) -> None:
    """source_files as a bare string (not a list) must not raise."""
    proc = run_check(answer={"source_files": "just-a-string-not-a-list.rs"})
    result = _parse_score(proc)
    assert result["score"] == 0.0
    assert proc.returncode == 0


@pytest.mark.security
def test_path_spam_substring_cheat_blocked(run_check) -> None:
    """Agent spams paths that substring-match required files.

    Each payload below is carefully chosen so that:
      - OLD match ``gt_f in af or af.endswith(gt_f)`` → scores (test is RED
        on vulnerable scripts, proving the cheat exists)
      - NEW match ``af == gt_f or af.endswith('/' + gt_f)`` → does NOT score
        (test is GREEN after the fix, proving the cheat is dead)

    Payload walk-through for gt_f = "tokio/runtime/scheduler.rs":
      "prefix_tokio/runtime/scheduler.rs_suffix"
        - OLD: gt_f is a contiguous substring starting at index 7 → MATCHES
        - NEW: not equal; does not end with "/tokio/runtime/scheduler.rs"
          (ends with "_suffix") → NO MATCH

    Payload walk-through for gt_f = "src/hyper/conn/http1.rs":
      "xsrc/hyper/conn/http1.rsy"
        - OLD: gt_f is a contiguous substring starting at index 1 → MATCHES
        - NEW: not equal; does not end with "/src/hyper/conn/http1.rs"
          (ends with ".rsy") → NO MATCH
    """
    proc = run_check(
        answer={
            "source_files": [
                "xsrc/hyper/conn/http1.rsy",
                "prefix_tokio/runtime/scheduler.rs_suffix",
                "totally/unrelated/file.rs",
            ]
        }
    )
    result = _parse_score(proc)
    assert result["score"] == 0.0, (
        "path-spam soft-cheat: unanchored substring matches must not count. "
        f"got score={result['score']}"
    )


@pytest.mark.security
def test_suffix_anchored_match_still_scores(run_check) -> None:
    """Legitimate case: long absolute paths ending in the required suffix."""
    proc = run_check(
        answer={
            "source_files": [
                "/workspace/hyper/src/hyper/conn/http1.rs",
                "/workspace/tokio/tokio/runtime/scheduler.rs",
                "/workspace/hyper/hyper/server/builder.rs",
            ]
        }
    )
    result = _parse_score(proc)
    assert result["score"] == 1.0


# ---------------------------------------------------------------------------
# Invariant 4b: key adversarial cases replayed against ALL 37 scripts
# ---------------------------------------------------------------------------
#
# The single-script tests above give fast, detailed coverage on the
# representative (`check_config_valid.sh`).  The parametrized sweep below
# catches the case where a future edit silently drifts one of the 36 other
# scripts away from the template — the text-level invariants 1 and 2 can miss
# subtle runtime regressions that show up only under adversarial input.
# We only replay the two cheapest, highest-signal payloads to keep test
# runtime bounded (74 subprocess invocations instead of 37 * 9 = 333).


_GT_THREE = {
    "required_files": [
        {"path": "a/b/c.rs"},
        {"path": "d/e/f.rs"},
        {"path": "g/h/i.rs"},
    ]
}


@pytest.mark.security
@pytest.mark.parametrize(
    "script", TARGET_FILES, ids=lambda p: str(p.relative_to(BENCHMARKS))
)
def test_all_scripts_reject_path_spam(script: Path, tmp_path: Path) -> None:
    """Every rewritten script must reject unanchored substring path spam."""
    proc = _run_check(
        script,
        tmp_path,
        answer={
            "source_files": [
                "prefix_a/b/c.rsX",
                "prefix_d/e/f.rsY",
                "prefix_g/h/i.rsZ",
            ]
        },
        ground_truth=_GT_THREE,
    )
    result = _parse_score(proc)
    assert result["score"] == 0.0, (
        f"{script.relative_to(ROOT)} scored path-spam substrings as matches — "
        "tightened match regressed."
    )


@pytest.mark.security
@pytest.mark.parametrize(
    "script", TARGET_FILES, ids=lambda p: str(p.relative_to(BENCHMARKS))
)
def test_all_scripts_survive_type_confusion(script: Path, tmp_path: Path) -> None:
    """Every rewritten script must produce a valid score on malformed answers.

    This exercises the `isinstance` guards added after the security review:
    a non-dict `error_source`, a string `source_files`, a nested non-list.
    """
    proc = _run_check(
        script,
        tmp_path,
        answer={
            "source_files": "not-a-list",
            "error_source": "also-not-a-dict",
            "files": 42,
        },
        ground_truth=_GT_THREE,
    )
    assert proc.stdout.strip(), (
        f"{script.relative_to(ROOT)} produced empty stdout on type-confused "
        f"answer — likely an AttributeError crash. stderr={proc.stderr!r}"
    )
    result = _parse_score(proc)
    assert result["score"] == 0.0


# ---------------------------------------------------------------------------
# Invariant 5: new answer and GT shapes covered explicitly
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_error_source_fallback_shape_scores(run_check) -> None:
    """Answer shape {"error_source": {"files": [...]}} must fall through to scoring."""
    proc = run_check(
        answer={
            "error_source": {
                "files": [
                    "/workspace/hyper/src/hyper/conn/http1.rs",
                    "/workspace/tokio/tokio/runtime/scheduler.rs",
                ]
            }
        }
    )
    result = _parse_score(proc)
    # 2 of 3 GT files matched via nested error_source.files fallback.
    assert result["score"] == pytest.approx(0.67, abs=0.01)


@pytest.mark.security
def test_error_source_non_dict_does_not_crash(run_check) -> None:
    """Answer with error_source set to a non-dict must NOT raise AttributeError.

    This is the denial-of-scoring vector identified in the security review:
    an agent writing {"error_source": "malicious-string"} previously crashed
    the Python process with an AttributeError during the nested .get() chain.
    """
    proc = run_check(answer={"error_source": "malicious-string"})
    assert (
        proc.stdout.strip()
    ), f"error_source type confusion crashed the script: stderr={proc.stderr!r}"
    result = _parse_score(proc)
    assert result["score"] == 0.0


@pytest.mark.security
def test_gt_flat_string_list_scores(tmp_path: Path) -> None:
    """GT with required_files as a flat string list (no dicts) must still score.

    Latent-trap protection: some task authors may write
    ``required_files = ["a.py", "b.py"]`` instead of
    ``required_files = [{"path": "a.py"}, {"path": "b.py"}]``. The rewritten
    template accepts both.
    """
    flat_gt = {
        "required_files": ["src/hyper/conn/http1.rs", "tokio/runtime/scheduler.rs"]
    }
    proc = _run_check(
        REPRESENTATIVE,
        tmp_path,
        answer={
            "source_files": [
                "/workspace/hyper/src/hyper/conn/http1.rs",
                "/workspace/tokio/tokio/runtime/scheduler.rs",
            ]
        },
        ground_truth=flat_gt,
    )
    result = _parse_score(proc)
    assert result["score"] == 1.0


@pytest.mark.security
def test_missing_gt_file_is_infra_failure(tmp_path: Path) -> None:
    """Missing ground_truth.json must exit non-zero so runners see infra failure.

    Contrast with test_missing_answer_file_returns_zero: a missing *answer* is
    an agent failure and must exit 0. A missing *GT* is always a task-directory
    misconfiguration (infra) and must exit non-zero so operators get alerted.
    """
    workspace = tmp_path / "workspace"
    (workspace / "agent_output").mkdir(parents=True)
    (workspace / "agent_output" / "answer.json").write_text(
        json.dumps({"source_files": ["a.rs"]})
    )
    # Deliberately do not create task_dir / ground_truth.json.
    task_dir = tmp_path / "task"
    task_dir.mkdir()

    env = os.environ.copy()
    env["WORKSPACE"] = str(workspace)
    env["TASK_DIR"] = str(task_dir)
    proc = subprocess.run(
        ["bash", str(REPRESENTATIVE)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode != 0, (
        "missing ground_truth.json must be a non-zero-exit infrastructure "
        f"failure, got returncode={proc.returncode}"
    )
