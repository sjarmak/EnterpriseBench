"""Prompt-echo resistance for the 7 dep-traversal CVE-blast-radius tasks.

EnterpriseBench-vjrbw: dep-traversal-004/007/008/009/010/011/012 each shipped
four checkpoints that grepped BLAST_RADIUS.md for the CVE id, the consumer repo
names, and the fixed version — every one of which instruction.md hands the agent.
A verbatim `cp instruction.md BLAST_RADIUS.md` scored 1.00 across all four
checkpoints with zero investigation.

The fix grades each checkpoint against
`ground_truth.json:scoring_evidence[<checkpoint>]` — tokens that are (a) absent
from instruction.md and (b) present in expected_solution.json, so they are
reachable only by an agent that actually researched the advisory or read the
manifests. ground_truth.json is sealed root-only (run_task.py GRADING_PATHS).

These tests pin BOTH directions on all 7 tasks:
  * the prompt echoed into the deliverable scores 0 on every checkpoint, and
  * a report carrying the real evidence still scores full.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
SUITE = REPO_ROOT / "benchmarks" / "dependency_management"

TASK_IDS = [
    "dep-traversal-004",
    "dep-traversal-007",
    "dep-traversal-008",
    "dep-traversal-009",
    "dep-traversal-010",
    "dep-traversal-011",
    "dep-traversal-012",
]

CHECKS = [
    "check_cve_id.sh",
    "check_direct_deps.sh",
    "check_transitive_paths.sh",
    "check_version_analysis.sh",
]


def _task_dir(task_id: str) -> Path:
    return SUITE / task_id


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


def _all_evidence_tokens(task_id: str) -> list[str]:
    gt = json.loads((_task_dir(task_id) / "ground_truth.json").read_text())
    evidence = gt["scoring_evidence"]
    return sorted({tok for toks in evidence.values() for tok in toks})


def _write_report(workspace: Path, text: str) -> None:
    (workspace / "BLAST_RADIUS.md").write_text(text)


# --- The attack: prompt echoed into the deliverable ---------------------------


@pytest.mark.parametrize("task_id", TASK_IDS)
@pytest.mark.parametrize("check", CHECKS)
def test_prompt_copy_scores_zero(task_id: str, check: str, tmp_path: Path) -> None:
    """`cp instruction.md BLAST_RADIUS.md` — the exact vjrbw attack — scores 0."""
    _write_report(tmp_path, (_task_dir(task_id) / "instruction.md").read_text())

    verdict = _run_check(task_id, check, tmp_path)

    assert verdict["score"] == 0.0, (
        f"{task_id}/{check} credited a prompt copy: {verdict}"
    )
    assert verdict["passed"] is False


@pytest.mark.parametrize("task_id", TASK_IDS)
@pytest.mark.parametrize("check", CHECKS)
def test_no_op_agent_scores_zero(task_id: str, check: str, tmp_path: Path) -> None:
    """No deliverable at all scores 0, never an infra error or free credit."""
    verdict = _run_check(task_id, check, tmp_path)

    assert verdict["score"] == 0.0
    assert verdict["passed"] is False


# --- The guard must not under-credit a real answer ----------------------------


@pytest.mark.parametrize("task_id", TASK_IDS)
@pytest.mark.parametrize("check", CHECKS)
def test_real_evidence_scores_full(task_id: str, check: str, tmp_path: Path) -> None:
    """A report citing the non-prompt evidence tokens scores full on every check."""
    _write_report(
        tmp_path, "Blast radius analysis. " + " ".join(_all_evidence_tokens(task_id))
    )

    verdict = _run_check(task_id, check, tmp_path)

    assert verdict["score"] == 1.0, f"{task_id}/{check} under-credited a real answer: {verdict}"
    assert verdict["passed"] is True


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_expected_solution_content_passes_every_checkpoint(
    task_id: str, tmp_path: Path
) -> None:
    """The shipped expected_solution.json, dropped in as the report, passes all four
    checkpoints — the answer key the checks grade against is internally consistent."""
    _write_report(
        tmp_path, (_task_dir(task_id) / "expected_solution.json").read_text()
    )

    for check in CHECKS:
        verdict = _run_check(task_id, check, tmp_path)
        assert verdict["passed"] is True, (
            f"{task_id}/{check} failed on the expected solution: {verdict}"
        )


# --- Evidence integrity: tokens are non-prompt AND in the answer key ----------


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_scoring_evidence_tokens_are_non_prompt(task_id: str) -> None:
    """Every scoring_evidence token must be ABSENT from instruction.md — else the
    checkpoint is gradable by echoing the prompt, the exact defect vjrbw fixes."""
    task_dir = _task_dir(task_id)
    instruction = task_dir.joinpath("instruction.md").read_text().lower()
    gt = json.loads((task_dir / "ground_truth.json").read_text())

    for checkpoint, tokens in gt["scoring_evidence"].items():
        assert tokens, f"{task_id}/{checkpoint} has an empty evidence set"
        for token in tokens:
            assert token.lower() not in instruction, (
                f"{task_id}/{checkpoint}: evidence token {token!r} leaks into the prompt"
            )


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_scoring_evidence_tokens_are_in_the_answer_key(task_id: str) -> None:
    """Every token must appear in expected_solution.json — else a genuine solve
    that matches the answer key would be under-credited."""
    task_dir = _task_dir(task_id)
    expected = json.dumps(
        json.loads((task_dir / "expected_solution.json").read_text())
    ).lower()
    gt = json.loads((task_dir / "ground_truth.json").read_text())

    for checkpoint, tokens in gt["scoring_evidence"].items():
        for token in tokens:
            assert token.lower() in expected, (
                f"{task_id}/{checkpoint}: evidence token {token!r} is not in expected_solution.json"
            )


# --- Robustness guards --------------------------------------------------------


@pytest.mark.parametrize("check", CHECKS)
def test_missing_ground_truth_is_infra_error(check: str, tmp_path: Path) -> None:
    """A missing answer key is a broken verifier (re-run), not a legitimate 0.0."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_report(workspace, "GHSA-4374-p667-p6c8 1.58.3")
    bare_task_dir = tmp_path / "no_gt"
    (bare_task_dir / "checks").mkdir(parents=True)
    real_check = SUITE / "dep-traversal-004" / "checks" / check
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
    assert "VERIFIER_INFRA_ERROR" in verdict["reason"]


@pytest.mark.parametrize("check", CHECKS)
def test_symlinked_report_is_not_followed(check: str, tmp_path: Path) -> None:
    """BLAST_RADIUS.md is agent-owned; a symlink to a planted file is not a report."""
    real = tmp_path / "elsewhere.md"
    real.write_text("GHSA-4374-p667-p6c8 1.58.3")
    (tmp_path / "BLAST_RADIUS.md").symlink_to(real)

    verdict = _run_check("dep-traversal-004", check, tmp_path)

    assert verdict["score"] == 0.0
    assert verdict["passed"] is False


@pytest.mark.parametrize("check", CHECKS)
def test_oversized_report_scores_zero(check: str, tmp_path: Path) -> None:
    """A multi-megabyte deliverable is a grader-DoS, not an analysis."""
    tokens = " ".join(_all_evidence_tokens("dep-traversal-004"))
    _write_report(tmp_path, tokens + "\n" + "x" * (2 * 1024 * 1024))

    verdict = _run_check("dep-traversal-004", check, tmp_path)

    assert verdict["score"] == 0.0
    assert verdict["passed"] is False


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_version_token_boundary_match(task_id: str, tmp_path: Path) -> None:
    """A version token must not match inside a longer number (2.0 vs 2.0.5),
    which would hand credit to an unrelated version string."""
    gt = json.loads((_task_dir(task_id) / "ground_truth.json").read_text())
    version_tokens = [
        t
        for toks in gt["scoring_evidence"].values()
        for t in toks
        if t[0].isdigit()
    ]
    if not version_tokens:
        pytest.skip(f"{task_id} grades on no bare version tokens")
    # Append a digit segment to each version so it is embedded in a longer number.
    decoyed = " ".join(f"{t}9" for t in version_tokens)
    _write_report(tmp_path, "versions: " + decoyed)

    verdict = _run_check(task_id, "check_version_analysis.sh", tmp_path)

    assert verdict["score"] == 0.0, (
        f"{task_id}: a version embedded in a longer number was credited: {verdict}"
    )
