"""Gate-compatible output contracts for incident-report tasks."""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
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
HEADLINE_INCIDENT_TASK_IDS = (
    "incident-investigation-004",
    "incident-investigation-dual-cockroach-001",
    "incident-investigation-dual-cortex-001",
    "incident-investigation-dual-flux-001",
    "incident-investigation-dual-kafka-001",
    "incident-investigation-dual-loki-001",
    "incident-investigation-dual-nats-001",
    "incident-investigation-dual-nomad-001",
    "incident-investigation-dual-prometheus-001",
    "incident-investigation-dual-tempo-001",
    "incident-investigation-dual-tikv-001",
    "incident-investigation-dual-vault-001",
    "incident-investigation-quad-containerd-001",
    "incident-investigation-tri-containerd-001",
)


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


@pytest.mark.parametrize("task_id", HEADLINE_INCIDENT_TASK_IDS)
def test_headline_incident_report_contract_is_gate_compatible(task_id: str) -> None:
    task_dir = PROJECT_ROOT / "benchmarks" / "incident_response" / task_id
    task_data = run_task._parse_task(task_dir / "task.toml")

    assert run_task._derive_graded_artifact_path(task_dir) == REPORT_PATH
    for mode in GATED_MODES:
        check_eligibility(
            task_data,
            mode,
            graded_artifact_path=REPORT_PATH,
            workspace=run_task.WORKSPACE_DIR,
        )

    prompt_sources = [task_dir / "instruction.md", task_dir / "task.toml"]
    check_sources = sorted((task_dir / "checks").glob("*.sh"))
    assert all(REPORT_PATH in source.read_text() for source in prompt_sources)
    assert all(
        "$WORKSPACE/agent_output/INCIDENT_REPORT.md" in source.read_text()
        for source in check_sources
    )
    assert all(
        f"/workspace/{repo['path']}/INCIDENT_REPORT.md"
        not in "\n".join(
            source.read_text() for source in [*prompt_sources, *check_sources]
        )
        for repo in task_data["repos"]
    )


def test_nerdctl_runtime_checkpoint_names_reach_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_data = run_task._parse_task(TASK_DIR / "task.toml")
    specs = run_task._verifier_specs_by_name(task_data["checkpoints"])
    expected = json.loads((TASK_DIR / "expected_solution.json").read_text())
    assert set(specs) == set(expected["checkpoints"])

    class FakeJudge:
        provenance = {"backend": "test"}

        def __init__(self, **_kwargs: object) -> None:
            pass

        def evaluate_checkpoint(
            self, *_args: object, **_kwargs: object
        ) -> SimpleNamespace:
            return SimpleNamespace(score=1.0, reasoning="test judge")

    from eb_verify import judge as judge_module

    monkeypatch.setattr(judge_module, "LLMJudge", FakeJudge)
    monkeypatch.setattr(
        run_task,
        "_docker_exec",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, stdout="grounded incident report", stderr=""
        ),
    )
    scores = {
        "checkpoints": [
            {
                "name": name,
                "weight": weight,
                "score": 1.0,
                "passed": True,
            }
            for name, (_verifier, weight, _timeout) in specs.items()
        ]
    }

    judged = run_task._apply_llm_judge(scores, TASK_DIR, "container", task_data)

    assert "verifier_infra_error" not in judged
    assert judged["task_score"] == 1.0
    assert all(checkpoint["judge_score"] == 1.0 for checkpoint in judged["checkpoints"])


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
