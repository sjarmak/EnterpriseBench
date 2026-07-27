from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "orchestration"))

from eb_study import StudySpec, file_hash  # noqa: E402
from study_pilot_preflight import (  # noqa: E402
    REQUIRED_ARMS,
    REQUIRED_CACHE_ISOLATION,
    REQUIRED_GATES,
    validate_pilot,
)
from study_run import InputProvenance  # noqa: E402
import study_pilot_preflight as preflight_module  # noqa: E402

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
    curated.write_text(json.dumps({"status": "candidate", "task_ids": [task_id]}))
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
                "cache_isolation": REQUIRED_CACHE_ISOLATION,
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
    curated.write_text(json.dumps({"status": "candidate", "task_ids": []}))
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


@pytest.mark.parametrize(
    ("target", "field", "value", "message"),
    [
        ("manifest", "schema_version", 2, "schema_version"),
        ("manifest", "status", "draft", "status"),
        ("manifest", "study_id", "other", "study_id"),
        ("manifest", "curated_manifest_hash", "sha256:other", "curated manifest hash"),
        ("manifest", "integrity_gates", [], "exact integrity gates"),
        ("manifest", "cache_isolation", {}, "cache-isolation contract"),
        ("spec", "task_ids", ["other"], "task_ids"),
        ("spec", "model", "other-model", "cheap-pilot contract"),
        ("manifest", "harness_hash", "sha256:other", "harness_hash"),
        ("spec", "harness", "sha256:other", "StudySpec harness"),
        ("manifest", "verifier_hashes", {}, "verifier hash"),
    ],
)
def test_contract_drift_fails_closed(
    tmp_path: Path,
    target: str,
    field: str,
    value: object,
    message: str,
) -> None:
    spec_path, manifest_path, curated = _write_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    spec = json.loads(spec_path.read_text())
    payload = manifest if target == "manifest" else spec
    payload[field] = value
    manifest_path.write_text(json.dumps(manifest))
    spec["task_manifest_hash"] = file_hash(manifest_path)
    spec_path.write_text(json.dumps(spec))

    with pytest.raises(ValueError, match=message):
        validate_pilot(
            spec_path=spec_path,
            manifest_path=manifest_path,
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


def test_superseded_repository_pilot_capsule_is_frozen_historically() -> None:
    study_dir = PROJECT_ROOT / "configs" / "studies" / "rryas_pilot_v1"

    with pytest.raises(ValueError, match="does not match current harness"):
        validate_pilot(
            spec_path=study_dir / "study_spec.json",
            manifest_path=study_dir / "pilot_manifest.json",
            curated_manifest_path=(
                PROJECT_ROOT / "results" / "rryas_dataset" / "candidate_manifest.json"
            ),
            repo_root=PROJECT_ROOT,
            closed_gates=frozenset(REQUIRED_GATES),
        )

    spec = StudySpec.load(study_dir / "study_spec.json")
    manifest = json.loads((study_dir / "pilot_manifest.json").read_text())
    assert spec.study_id == "rryas-pilot-v1"
    assert spec.task_manifest_hash == file_hash(study_dir / "pilot_manifest.json")
    assert manifest["harness_hash"] == spec.harness


def test_cli_prints_the_locked_evidence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    study_dir = PROJECT_ROOT / "configs" / "studies" / "rryas_pilot_v1"
    monkeypatch.setattr(
        preflight_module, "_closed_gate_ids", lambda: frozenset(REQUIRED_GATES)
    )
    manifest = json.loads((study_dir / "pilot_manifest.json").read_text())
    task = manifest["tasks"][0]
    monkeypatch.setattr(
        preflight_module,
        "_default_provenance_provider",
        lambda _repo_root: lambda _task_toml: InputProvenance(
            task_hash=task["task_hash"],
            harness_hash=manifest["harness_hash"],
            verifier_hash=manifest["verifier_hashes"][task["task_id"]],
        ),
    )
    monkeypatch.setattr(
        preflight_module,
        "_git_revision_matches",
        lambda _revision, _paths, *, repo_root: True,
    )

    assert (
        preflight_module.main(
            [
                "--spec",
                str(study_dir / "study_spec.json"),
                "--manifest",
                str(study_dir / "pilot_manifest.json"),
                "--curated-manifest",
                str(
                    PROJECT_ROOT
                    / "results"
                    / "rryas_dataset"
                    / "candidate_manifest.json"
                ),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["study_id"] == "rryas-pilot-v1"


def test_gate_query_accepts_only_closed_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issues = [
        {"id": REQUIRED_GATES[0], "status": "closed"},
        {"id": REQUIRED_GATES[1], "status": "open"},
    ]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(issues), stderr=""
        ),
    )

    assert preflight_module._closed_gate_ids() == frozenset({REQUIRED_GATES[0]})
