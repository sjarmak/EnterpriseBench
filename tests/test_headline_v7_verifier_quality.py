from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = (
    PROJECT_ROOT / "configs" / "studies" / "rryas-headline-v7" / "final_manifest.json"
)


def _tasks() -> list[dict[str, Any]]:
    return json.loads(MANIFEST.read_text())["tasks"]


def _report_path(workspace: Path, declared: str) -> Path:
    prefix = "/workspace/"
    assert declared.startswith(prefix)
    relative = Path(declared.removeprefix(prefix))
    assert relative.parts
    assert all(part not in {"", ".", ".."} for part in relative.parts)
    resolved = (workspace / relative).resolve()
    resolved.relative_to(workspace.resolve())
    return resolved


def _expected_report(task_dir: Path) -> tuple[str, set[str]]:
    expected = json.loads((task_dir / "expected_solution.json").read_text())
    checkpoints = expected["checkpoints"]
    return (
        "\n\n".join(
            checkpoint["expected_solution"] for checkpoint in checkpoints.values()
        ),
        set(checkpoints),
    )


def _run_check(
    *,
    task_dir: Path,
    script_name: str,
    workspace: Path,
) -> dict[str, Any]:
    relative = Path(script_name)
    assert not relative.is_absolute()
    assert all(part not in {"", ".", ".."} for part in relative.parts)
    assert len(relative.parts) == 2
    assert relative.parts[0] == "checks"
    resolved_task = task_dir.resolve()
    resolved_task.relative_to(PROJECT_ROOT.resolve())
    assert not task_dir.is_symlink()
    checks = task_dir / "checks"
    assert not checks.is_symlink()
    resolved_checks = checks.resolve()
    resolved_checks.relative_to(resolved_task)
    assert resolved_checks.is_dir()
    candidate = task_dir / relative
    assert not candidate.is_symlink()
    script = candidate.resolve()
    script.relative_to(resolved_checks)
    assert script.is_file()
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TASK_DIR": str(task_dir),
        "WORKSPACE": str(workspace),
    }
    result = subprocess.run(
        ["bash", str(script)],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def _weighted_results(
    checkpoints: list[dict[str, Any]],
    *,
    task_dir: Path,
    workspace: Path,
) -> tuple[float, list[dict[str, Any]]]:
    weighted = [
        (
            float(checkpoint["weight"]),
            _run_check(
                task_dir=task_dir,
                script_name=checkpoint["verifier"],
                workspace=workspace,
            ),
        )
        for checkpoint in checkpoints
    ]
    return (
        sum(weight * float(result["score"]) for weight, result in weighted),
        [result for _weight, result in weighted],
    )


@pytest.mark.parametrize(
    "task",
    _tasks(),
    ids=lambda task: task["task_id"],
)
def test_v7_ground_truth_and_empty_answer_calibration(
    tmp_path: Path,
    task: dict[str, Any],
) -> None:
    task_dir = PROJECT_ROOT / Path(task["task_toml"]).parent
    with (task_dir / "task.toml").open("rb") as handle:
        task_config = tomllib.load(handle)
    expected_report, expected_checkpoints = _expected_report(task_dir)
    checkpoints = task_config["checkpoints"]

    assert {checkpoint["name"] for checkpoint in checkpoints} == expected_checkpoints
    assert sum(
        float(checkpoint["weight"]) for checkpoint in checkpoints
    ) == pytest.approx(1.0)

    workspace = tmp_path / "ground-truth"
    report = _report_path(workspace, task["graded_artifact_path"])
    report.parent.mkdir(parents=True)
    report.write_text(expected_report)
    ground_truth_score, ground_truth_results = _weighted_results(
        checkpoints,
        task_dir=task_dir,
        workspace=workspace,
    )
    assert all(
        "VERIFIER_INFRA_ERROR" not in str(result.get("detail"))
        for result in ground_truth_results
    )
    assert ground_truth_score >= 0.85, ground_truth_results

    empty_workspace = tmp_path / "empty"
    empty_report = _report_path(
        empty_workspace,
        task["graded_artifact_path"],
    )
    empty_report.parent.mkdir(parents=True)
    empty_report.write_text("")
    empty_score, empty_results = _weighted_results(
        checkpoints,
        task_dir=task_dir,
        workspace=empty_workspace,
    )
    assert all(
        "VERIFIER_INFRA_ERROR" not in str(result.get("detail"))
        for result in empty_results
    )
    assert empty_score <= 0.1


def test_verifier_gate_confines_scripts_and_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys.modules[__name__], "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("PRIVATE_SENTINEL", "must-not-leak")
    task_dir = tmp_path / "task"
    checks = task_dir / "checks"
    checks.mkdir(parents=True)
    valid = checks / "valid.sh"
    valid.write_text(
        'if [[ -n "${PRIVATE_SENTINEL+x}" ]]; then exit 9; fi\n'
        'printf \'{"score": 1.0, "detail": "ok"}\\n\'\n'
    )

    assert (
        _run_check(
            task_dir=task_dir,
            script_name="checks/valid.sh",
            workspace=tmp_path,
        )["score"]
        == 1.0
    )
    for escaped in (str(valid), "../valid.sh", "checks/../valid.sh"):
        with pytest.raises((AssertionError, ValueError)):
            _run_check(
                task_dir=task_dir,
                script_name=escaped,
                workspace=tmp_path,
            )

    outside = tmp_path / "outside"
    outside.mkdir()
    evil = outside / "evil.sh"
    evil.write_text("touch escaped\n")
    (checks / "evil.sh").symlink_to(evil)
    with pytest.raises((AssertionError, ValueError)):
        _run_check(
            task_dir=task_dir,
            script_name="checks/evil.sh",
            workspace=tmp_path,
        )

    other_task = tmp_path / "other-task"
    other_task.mkdir()
    (other_task / "checks").symlink_to(outside, target_is_directory=True)
    with pytest.raises((AssertionError, ValueError)):
        _run_check(
            task_dir=other_task,
            script_name="checks/evil.sh",
            workspace=tmp_path,
        )
    assert not (tmp_path / "escaped").exists()
