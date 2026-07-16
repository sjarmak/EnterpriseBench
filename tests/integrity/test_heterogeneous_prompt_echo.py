"""Prompt-echo resistance for the three non-dep-traversal echo tasks.

Siblings of the twelve CVE-blast-radius tasks pinned in
test_dep_traversal_prompt_echo.py, but each with its own task_type, its own
deliverable, and its own reason the old checks were gradable by echoing the
prompt (EnterpriseBench-jn73.2.7.3):

  * rbac-audit-001 (0.69 on an echo) — instruction.md asks "does it check the
    old tier, the new tier, or both?", and the two checkpoints grepped for "old
    tier" and "new tier" respectively. The prompt states the question in a form
    that contains both answers, so a report restating it satisfied both.
  * camel-routing-arch-001 (0.67) — both prompts name RouteReifier,
    RouteDefinition, Pipeline and Channel, which is exactly what the chain
    checkpoint grepped for; the architecture checkpoint added a >=500-char
    length gate that credits padding.
  * ceph-rgw-auth-secure-001 (0.61 on instruction.md, 0.88 on instruction_mcp.md)
    — the MCP variant lists the auth source files in a "Key Reference Files"
    block, so the auth-flow patterns self-matched.

The fix is the vjrbw one: grade each checkpoint against
ground_truth.json:scoring_evidence[<checkpoint>] — tokens absent from every
prompt variant the task ships and present in expected_solution.json, so they are
reachable only by an agent that actually read the code. ground_truth.json is
sealed root-only (run_task.py GRADING_PATHS), so its tokens cannot leak.

Two tasks ship BOTH instruction.md and instruction_mcp.md. Echo is pinned
against each variant separately: ceph scored higher on the MCP arm than the
baseline arm, so testing only instruction.md would have missed the worse case.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
BENCHMARKS = REPO_ROOT / "benchmarks"

sys.path.insert(0, str(REPO_ROOT / "lib"))
from eb_verify.scorer_guard import InfraError, guard_checkpoint_verdict  # noqa: E402


# task_id -> (suite-relative dir, deliverable path under $WORKSPACE, checks)
TASKS = {
    "rbac-audit-001": (
        "security_operations/rbac-audit-001",
        "security_audit.md",
        [
            "check_policy_types.sh",
            "check_apiserver_auth.sh",
            "check_webhook_auth.sh",
            "check_bypass_remediation.sh",
        ],
    ),
    "camel-routing-arch-001": (
        "feature_delivery/camel-routing-arch-001",
        "agent_output/answer.json",
        [
            "check_source_files.sh",
            "check_dependency_chain.sh",
            "check_architecture.sh",
        ],
    ),
    "ceph-rgw-auth-secure-001": (
        "security_operations/ceph-rgw-auth-secure-001",
        "security_audit.md",
        [
            "check_auth_flow.sh",
            "check_findings.sh",
            "check_remediations.sh",
        ],
    ),
}

CASES = [(task_id, check) for task_id, (_, _, checks) in TASKS.items() for check in checks]
CASE_IDS = [f"{task_id}:{check}" for task_id, check in CASES]


def _task_dir(task_id: str) -> Path:
    return BENCHMARKS / TASKS[task_id][0]


def _prompt_variants(task_id: str) -> list[Path]:
    """Every instruction file this task ships — each is a separate echo vector."""
    return [p for p in sorted(_task_dir(task_id).glob("instruction*.md"))]


def _write_report(task_id: str, workspace: Path, text: str) -> None:
    report = workspace / TASKS[task_id][1]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(text)


def _run_check(task_id: str, check: str, workspace: Path) -> dict:
    task_dir = _task_dir(task_id)
    env = os.environ.copy()
    env["WORKSPACE"] = str(workspace)
    env["TASK_DIR"] = str(task_dir)
    result = subprocess.run(
        ["bash", str(task_dir / "checks" / check)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    stdout = result.stdout.strip()
    assert stdout, f"{task_id}/{check} emitted no verdict (stderr: {result.stderr})"
    return json.loads(stdout)


def _evidence(task_id: str) -> dict[str, list[str]]:
    gt = json.loads((_task_dir(task_id) / "ground_truth.json").read_text())
    return gt["scoring_evidence"]


def _all_evidence_tokens(task_id: str) -> list[str]:
    return sorted({tok for toks in _evidence(task_id).values() for tok in toks})


# --- The attack: prompt echoed into the deliverable ---------------------------


@pytest.mark.parametrize(("task_id", "check"), CASES, ids=CASE_IDS)
def test_prompt_copy_scores_zero(task_id: str, check: str, tmp_path: Path) -> None:
    """Every prompt variant, copied verbatim into the deliverable, scores 0."""
    for variant in _prompt_variants(task_id):
        workspace = tmp_path / variant.stem
        workspace.mkdir()
        _write_report(task_id, workspace, variant.read_text())

        verdict = _run_check(task_id, check, workspace)

        assert verdict["score"] == 0.0, (
            f"{task_id}/{check} credited a copy of {variant.name}: {verdict}"
        )
        assert verdict["passed"] is False


@pytest.mark.parametrize(("task_id", "check"), CASES, ids=CASE_IDS)
def test_no_op_agent_scores_zero(task_id: str, check: str, tmp_path: Path) -> None:
    """No deliverable at all scores 0, never an infra error or free credit."""
    verdict = _run_check(task_id, check, tmp_path)

    assert verdict["score"] == 0.0
    assert verdict["passed"] is False


# --- The guard must not under-credit a real answer ----------------------------


@pytest.mark.parametrize(("task_id", "check"), CASES, ids=CASE_IDS)
def test_real_evidence_scores_full(task_id: str, check: str, tmp_path: Path) -> None:
    """A report citing the non-prompt evidence tokens scores full on every check."""
    _write_report(
        task_id, tmp_path, "Audit findings. " + " ".join(_all_evidence_tokens(task_id))
    )

    verdict = _run_check(task_id, check, tmp_path)

    assert verdict["score"] == 1.0, (
        f"{task_id}/{check} under-credited a real answer: {verdict}"
    )
    assert verdict["passed"] is True


@pytest.mark.parametrize("task_id", list(TASKS), ids=list(TASKS))
def test_expected_solution_content_passes_every_checkpoint(
    task_id: str, tmp_path: Path
) -> None:
    """The shipped expected_solution.json, dropped in as the deliverable, passes
    every checkpoint — the answer key the checks grade against is self-consistent."""
    _write_report(
        task_id, tmp_path, (_task_dir(task_id) / "expected_solution.json").read_text()
    )

    for check in TASKS[task_id][2]:
        verdict = _run_check(task_id, check, tmp_path)
        assert verdict["passed"] is True, (
            f"{task_id}/{check} failed on the expected solution: {verdict}"
        )


# --- Evidence integrity: non-prompt AND in the answer key ---------------------


@pytest.mark.parametrize("task_id", list(TASKS), ids=list(TASKS))
def test_scoring_evidence_tokens_are_non_prompt(task_id: str) -> None:
    """Every token must be absent from EVERY prompt variant — a token present in
    one is gradable by echoing that arm, which is the whole defect."""
    variants = {p.name: p.read_text().lower() for p in _prompt_variants(task_id)}
    assert variants, f"{task_id} ships no instruction file to test against"

    for checkpoint, tokens in _evidence(task_id).items():
        assert tokens, f"{task_id}/{checkpoint} has an empty evidence set"
        for token in tokens:
            for name, text in variants.items():
                assert token.lower() not in text, (
                    f"{task_id}/{checkpoint}: evidence token {token!r} leaks into {name}"
                )


@pytest.mark.parametrize("task_id", list(TASKS), ids=list(TASKS))
def test_scoring_evidence_tokens_are_in_the_answer_key(task_id: str) -> None:
    """Every token must appear in expected_solution.json — else a genuine solve
    that matches the answer key would be under-credited."""
    expected = json.dumps(
        json.loads((_task_dir(task_id) / "expected_solution.json").read_text())
    ).lower()

    for checkpoint, tokens in _evidence(task_id).items():
        for token in tokens:
            assert token.lower() in expected, (
                f"{task_id}/{checkpoint}: evidence token {token!r} is not in "
                f"expected_solution.json"
            )


@pytest.mark.parametrize("task_id", list(TASKS), ids=list(TASKS))
def test_no_evidence_token_nests_inside_a_sibling(task_id: str) -> None:
    """No token may be a substring of another in the same checkpoint: the driver
    matches by substring, so citing the longer one would silently score both.

    This is the collision class these tasks actually have — `NetworkPolicy`
    inside `StagedNetworkPolicy`, `memcmp` inside `CRYPTO_memcmp`,
    `DefaultChannel` inside its own full path — the reason the tokens are
    `projectcalico/`-prefixed paths rather than bare type names.
    """
    for checkpoint, tokens in _evidence(task_id).items():
        for token in tokens:
            nested = [
                other
                for other in tokens
                if other != token and token.lower() in other.lower()
            ]
            assert not nested, (
                f"{task_id}/{checkpoint}: {token!r} nests inside {nested!r} — "
                f"citing the longer token would score both"
            )


@pytest.mark.parametrize("task_id", list(TASKS), ids=list(TASKS))
def test_no_evidence_token_is_a_bare_version(task_id: str) -> None:
    """These drivers match by plain substring, deliberately: no checkpoint here
    grades on a bare version, so the dep-traversal version-boundary branch would
    be dead code. If a version token is ever added, plain substring would match
    it inside a longer number (2.0 in 12.0.5) — so fail here and make whoever
    adds it port the boundary matcher rather than inherit a silent miscredit."""
    for checkpoint, tokens in _evidence(task_id).items():
        for token in tokens:
            assert not re.fullmatch(r"v?\d+(\.\d+)+", token), (
                f"{task_id}/{checkpoint}: {token!r} is a bare version, but this "
                f"driver matches by plain substring — port the version-boundary "
                f"matcher from the dep-traversal driver first"
            )


# --- Robustness guards --------------------------------------------------------


@pytest.mark.parametrize(("task_id", "check"), CASES, ids=CASE_IDS)
def test_missing_ground_truth_is_infra_error(
    task_id: str, check: str, tmp_path: Path
) -> None:
    """A missing answer key is a broken verifier (re-run), not a legitimate 0.0.

    Asserted by driving scorer_guard, which reads the sentinel out of `detail`
    and nothing else — a sentinel under any other key routes nowhere and lands
    as a real agent 0.0.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_report(task_id, workspace, " ".join(_all_evidence_tokens(task_id)))
    bare_task_dir = tmp_path / "no_gt"
    (bare_task_dir / "checks").mkdir(parents=True)
    real_check = _task_dir(task_id) / "checks" / check
    (bare_task_dir / "checks" / check).write_text(real_check.read_text())

    env = os.environ.copy()
    env["WORKSPACE"] = str(workspace)
    env["TASK_DIR"] = str(bare_task_dir)
    result = subprocess.run(
        ["bash", str(bare_task_dir / "checks" / check)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )

    verdict = json.loads(result.stdout.strip())
    assert verdict["score"] == 0.0
    assert "VERIFIER_INFRA_ERROR" in verdict.get("detail", ""), (
        f"{task_id}/{check}: the sentinel must ride in 'detail' — the only field "
        f"scorer_guard scans. Got: {verdict}"
    )

    guarded = guard_checkpoint_verdict(
        result.stdout, result.returncode, checkpoint=check
    )
    assert isinstance(guarded, InfraError), (
        f"{task_id}/{check}: a missing answer key was scored as a real 0.0 "
        f"instead of routing to the re-run channel: {guarded}"
    )
    assert guarded.context["signature"] == "VERIFIER_INFRA_ERROR"


@pytest.mark.parametrize(("task_id", "check"), CASES, ids=CASE_IDS)
def test_symlinked_report_is_not_followed(
    task_id: str, check: str, tmp_path: Path
) -> None:
    """The deliverable is agent-owned; a symlink to a planted file is not a report."""
    real = tmp_path / "elsewhere.md"
    real.write_text(" ".join(_all_evidence_tokens(task_id)))
    report = tmp_path / TASKS[task_id][1]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.symlink_to(real)

    verdict = _run_check(task_id, check, tmp_path)

    assert verdict["score"] == 0.0
    assert verdict["passed"] is False


@pytest.mark.parametrize(("task_id", "check"), CASES, ids=CASE_IDS)
def test_oversized_report_scores_zero(
    task_id: str, check: str, tmp_path: Path
) -> None:
    """A multi-megabyte deliverable is a grader-DoS, not an analysis."""
    _write_report(
        task_id,
        tmp_path,
        " ".join(_all_evidence_tokens(task_id)) + "\n" + "x" * (2 * 1024 * 1024),
    )

    verdict = _run_check(task_id, check, tmp_path)

    assert verdict["score"] == 0.0
    assert verdict["passed"] is False
