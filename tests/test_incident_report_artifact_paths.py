"""Gate-compatible output contract for the Finder supplement incident task."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASK_DIR = (
    PROJECT_ROOT
    / "benchmarks"
    / "incident_response"
    / "incident-investigation-dual-nerdctl-001"
)
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "orchestration"))

import run_task  # noqa: E402
from mode_gate import GATED_MODES, check_eligibility  # noqa: E402

REPORT_PATH = "/workspace/agent_output/INCIDENT_REPORT.md"
OLD_REPORT_PATH = "/workspace/nerdctl/INCIDENT_REPORT.md"


def test_nerdctl_report_contract_is_gate_compatible() -> None:
    task_data = run_task._parse_task(TASK_DIR / "task.toml")

    assert run_task._derive_graded_artifact_path(TASK_DIR) == REPORT_PATH
    for mode in GATED_MODES:
        check_eligibility(
            task_data,
            mode,
            graded_artifact_path=REPORT_PATH,
            workspace=run_task.WORKSPACE_DIR,
        )

    prompt_sources = [TASK_DIR / "instruction.md", TASK_DIR / "task.toml"]
    check_sources = sorted((TASK_DIR / "checks").glob("*.sh"))
    assert all(REPORT_PATH in source.read_text() for source in prompt_sources)
    assert all(
        "$WORKSPACE/agent_output/INCIDENT_REPORT.md" in source.read_text()
        for source in check_sources
    )
    assert all(
        OLD_REPORT_PATH not in source.read_text()
        for source in [*prompt_sources, *check_sources]
    )


@pytest.mark.parametrize(
    ("report_source", "expected_score"),
    (("instruction.md", 0.0), ("expected_solution.json", 1.0)),
)
def test_nerdctl_verifier_discriminates_at_agent_output(
    tmp_path: Path, report_source: str, expected_score: float
) -> None:
    workspace = tmp_path / "workspace"
    report = workspace / "agent_output" / "INCIDENT_REPORT.md"
    report.parent.mkdir(parents=True)
    report.write_text((TASK_DIR / report_source).read_text())
    env = {
        "PATH": "/usr/bin:/bin",
        "WORKSPACE": str(workspace),
        "TASK_DIR": str(TASK_DIR),
    }

    for check in sorted((TASK_DIR / "checks").glob("*.sh")):
        completed = subprocess.run(
            ["bash", str(check)],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr
        verdict = json.loads(completed.stdout)
        assert verdict["score"] == expected_score, check.name
