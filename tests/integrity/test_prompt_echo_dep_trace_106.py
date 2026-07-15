"""Prompt-echo evidence for ccx-dep-trace-106.

Unlike the ansible planted-prompt vector, this task's leak lived in the
*instruction itself*: instruction_mcp.md named all five ground-truth file paths
and two ground-truth symbols verbatim, so a no-work agent that echoed the prompt
into answer.json scored full marks having read nothing — no matcher can tell a
repo-reader from a prompt-echoer when the prompt contains the answer.

The fix de-leaks the instruction (role descriptions, no paths/symbols) and points
the file check at the canonical file_extraction scorer. These regressions
reconstruct the REAL combined mcp-arm instruction via the live builder
(run_task._build_instruction_text) — a test that planted only the already-clean
instruction.md would pass green while the exploit stayed open — and assert an
echo of it earns nothing on EITHER checkpoint.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent

# The runner's own env builder, not a copy: check_source_files.sh execs the
# scorer as `python3 -m eb_verify.…`, which needs lib/ on PYTHONPATH exactly the
# way the runner provides it.
from eb_verify.runner import checkpoint_env  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))
import run_task  # noqa: E402

TASK_DIR = REPO_ROOT / "benchmarks" / "dependency_management" / "ccx-dep-trace-106"
CHECKS = TASK_DIR / "checks"

# The five answer-key symbols check_symbols.sh looks for. This mirrors the
# literal list in that script (checks/check_symbols.sh) by hand — the two must
# move together; if the check's list changes, update this copy or the leak
# assertion below validates against a stale set.
GT_SYMBOLS = [
    "opt_pass",
    "pass_manager",
    "execute_pass_list",
    "tree_ssa_dce",
    "passes.def",
]


def _run_check(check_name: str, workspace: Path) -> dict:
    result = subprocess.run(
        ["bash", str(CHECKS / check_name)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(workspace),
        env=checkpoint_env(workspace, TASK_DIR, "prompt-echo-test"),
    )
    stdout = result.stdout.strip()
    assert stdout, f"{check_name} emitted no verdict (stderr: {result.stderr})"
    return json.loads(stdout)


def _combined_mcp_instruction() -> str:
    """The exact text the mcp-arm agent sees: preamble + instruction_mcp.md +
    instruction.md + output appendix."""
    text = run_task._build_instruction_text(TASK_DIR, "mcp_only")
    assert text, "combined mcp instruction is empty"
    return text


def _write_answer(workspace: Path, answer: dict) -> None:
    out = workspace / "agent_output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "answer.json").write_text(json.dumps(answer))


@pytest.mark.parametrize("check", ["check_source_files.sh", "check_symbols.sh"])
def test_echoing_the_mcp_instruction_earns_nothing(tmp_path: Path, check: str) -> None:
    """Dump the combined mcp instruction into answer.json — the live exploit."""
    _write_answer(
        tmp_path,
        {"text": _combined_mcp_instruction(), "summary": _combined_mcp_instruction()},
    )

    verdict = _run_check(check, tmp_path)

    assert verdict["score"] == 0.0, f"{check} credited a prompt echo: {verdict}"
    assert verdict["passed"] is False


def test_mcp_instruction_names_no_answer_key() -> None:
    """The property that makes both checks sound: the instruction the agent sees
    must not contain any GT path or GT symbol."""
    combined = _combined_mcp_instruction()
    gt = json.loads((TASK_DIR / "ground_truth.json").read_text())

    for f in gt.get("required_files", []):
        assert f["path"] not in combined, f"instruction leaks GT path {f['path']}"

    # check_symbols.sh normalizes underscores before matching; mirror it.
    norm_combined = combined.replace("_", "")
    for sym in GT_SYMBOLS:
        assert sym not in combined and sym.replace("_", "") not in norm_combined, (
            f"instruction leaks GT symbol {sym}"
        )


def test_genuine_answer_scores_full(tmp_path: Path) -> None:
    """A real answer naming the five files still scores 1.0 (no under-credit)."""
    gt = json.loads((TASK_DIR / "ground_truth.json").read_text())
    paths = [f["path"] for f in gt["required_files"]]
    _write_answer(tmp_path, {"files": [{"repo": "gcc", "path": p} for p in paths]})

    verdict = _run_check("check_source_files.sh", tmp_path)

    assert verdict["score"] == 1.0, f"real files answer under-credited: {verdict}"
    assert verdict["passed"] is True
