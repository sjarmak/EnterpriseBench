from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "orchestration"))

from eb_study import StudySpec, file_hash  # noqa: E402
from study_pilot_preflight import (  # noqa: E402
    REQUIRED_ARMS,
    REQUIRED_GATES,
    validate_pilot,
)
from study_run import InputProvenance  # noqa: E402

PROVENANCE = InputProvenance(
    task_hash="sha256:task",
    harness_hash="sha256:harness",
    verifier_hash="sha256:verifier",
)


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    task_id = "task-a"
    task_dir = tmp_path / "benchmarks" / "suite" / task_id
    task_dir.mkdir(parents=True)
    task_toml = task_dir / "task.toml"
    task_toml.write_text(
        '[task]\nid = "task-a"\nestimated_duration_minutes = 25\n'
        '[tool_access]\nsourcegraph_mirror_config = "configs/sg/task-a.json"\n'
    )
    sg_config = tmp_path / "configs" / "sg" / "task-a.json"
    sg_config.parent.mkdir(parents=True)
    sg_config.write_text('{"repos": ["example/repo"]}\n')

    curated = tmp_path / "curated.json"
    curated.write_text(
        json.dumps({"status": "candidate", "tasks": [{"task_id": task_id}]})
    )
    manifest = tmp_path / "pilot_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "locked-pilot",
                "study_id": "pilot-v1",
                "curated_manifest": "curated.json",
                "curated_manifest_hash": file_hash(curated),
                "tasks": [
                    {
                        "task_id": task_id,
                        "task_toml": "benchmarks/suite/task-a/task.toml",
                        "task_hash": file_hash(task_toml),
                    }
                ],
                "integrity_gates": list(REQUIRED_GATES),
                "harness_hash": PROVENANCE.harness_hash,
                "verifier_hashes": {task_id: PROVENANCE.verifier_hash},
            }
        )
    )
    spec_path = tmp_path / "study_spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "study_id": "pilot-v1",
                "schema_version": 1,
                "task_manifest_hash": file_hash(manifest),
                "task_ids": [task_id],
                "arms": [
                    {"name": name, "capability_fingerprint": fingerprint}
                    for name, fingerprint in REQUIRED_ARMS
                ],
                "baseline_arm": "baseline",
                "repetitions": 1,
                "attempt_policy": "first_valid_attempt",
                "max_attempts": 2,
                "model": "claude-sonnet-5",
                "harness": "sha256:harness",
                "revision": "abc123",
                "token_source": "sdk_model_usage",
                "score_contract": "weighted-mean-v2",
                "promotion_policy": "paired-valid-complete-arms",
            }
        )
    )
    return spec_path, manifest, curated


def _validate(
    tmp_path: Path,
    *,
    closed_gates: frozenset[str] = frozenset(REQUIRED_GATES),
    revision_ok: bool = True,
):
    spec, manifest, curated = _write_fixture(tmp_path)
    return validate_pilot(
        spec_path=spec,
        manifest_path=manifest,
        curated_manifest_path=curated,
        repo_root=tmp_path,
        closed_gates=closed_gates,
        revision_validator=lambda _revision, _paths: revision_ok,
        provenance_provider=lambda _task_toml: PROVENANCE,
    )


def test_locked_pilot_compiles_exactly_three_declared_trials(tmp_path: Path) -> None:
    evidence = _validate(tmp_path)

    assert evidence.study_id == "pilot-v1"
    assert evidence.task_ids == ("task-a",)
    assert evidence.slots == (
        ("task-a", "baseline", 1),
        ("task-a", "mcp_only", 1),
        ("task-a", "cli", 1),
    )


def test_missing_integrity_gate_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="integrity gates are not closed"):
        _validate(tmp_path, closed_gates=frozenset(REQUIRED_GATES[:-1]))


def test_task_must_remain_in_curated_manifest(tmp_path: Path) -> None:
    spec, manifest, curated = _write_fixture(tmp_path)
    curated.write_text(json.dumps({"status": "candidate", "tasks": []}))
    pilot = json.loads(manifest.read_text())
    pilot["curated_manifest_hash"] = file_hash(curated)
    manifest.write_text(json.dumps(pilot))
    study = json.loads(spec.read_text())
    study["task_manifest_hash"] = file_hash(manifest)
    spec.write_text(json.dumps(study))

    with pytest.raises(ValueError, match="not in curated manifest"):
        validate_pilot(
            spec_path=spec,
            manifest_path=manifest,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            closed_gates=frozenset(REQUIRED_GATES),
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda _task_toml: PROVENANCE,
        )


def test_task_hash_drift_fails_closed(tmp_path: Path) -> None:
    spec, manifest, curated = _write_fixture(tmp_path)
    task_path = tmp_path / "benchmarks" / "suite" / "task-a" / "task.toml"
    task_path.write_text(task_path.read_text() + "\n# drift\n")

    with pytest.raises(ValueError, match="task hash"):
        validate_pilot(
            spec_path=spec,
            manifest_path=manifest,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            closed_gates=frozenset(REQUIRED_GATES),
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda _task_toml: PROVENANCE,
        )


def test_extra_arm_fails_closed(tmp_path: Path) -> None:
    spec_path, manifest, curated = _write_fixture(tmp_path)
    payload = json.loads(spec_path.read_text())
    payload["arms"].append({"name": "hybrid", "capability_fingerprint": "forbidden"})
    spec_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="exact arms"):
        validate_pilot(
            spec_path=spec_path,
            manifest_path=manifest,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            closed_gates=frozenset(REQUIRED_GATES),
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda _task_toml: PROVENANCE,
        )


def test_revision_drift_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="revision"):
        _validate(tmp_path, revision_ok=False)


def test_spec_manifest_hash_drift_fails_closed(tmp_path: Path) -> None:
    spec_path, manifest, curated = _write_fixture(tmp_path)
    spec = StudySpec.load(spec_path)
    manifest.write_text(manifest.read_text() + "\n")
    assert spec.task_manifest_hash != file_hash(manifest)

    with pytest.raises(ValueError, match="task_manifest_hash"):
        validate_pilot(
            spec_path=spec_path,
            manifest_path=manifest,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            closed_gates=frozenset(REQUIRED_GATES),
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda _task_toml: PROVENANCE,
        )
