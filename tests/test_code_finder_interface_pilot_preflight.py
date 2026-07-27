from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "orchestration"))

from code_finder_interface_pilot_preflight import (  # noqa: E402
    REQUIRED_ARMS,
    REQUIRED_EXECUTION,
    REQUIRED_JUDGE,
    REQUIRED_TREATMENT_CONTRACT,
    validate_interface_pilot,
)
import code_finder_interface_pilot_preflight as preflight_module  # noqa: E402
from eb_study import file_hash  # noqa: E402
from study_run import InputProvenance  # noqa: E402

PROVENANCE = InputProvenance(
    task_hash="sha256:task",
    harness_hash="sha256:harness",
    verifier_hash="sha256:verifier",
)


def _provenance(task_toml: Path) -> InputProvenance:
    return InputProvenance(
        task_hash=file_hash(task_toml),
        harness_hash=PROVENANCE.harness_hash,
        verifier_hash=PROVENANCE.verifier_hash,
    )


def _task_toml(task_id: str, task_type: str, repo_names: tuple[str, str]) -> str:
    return f"""
difficulty_stratum = "dual_repo"

[task]
id = "{task_id}"
task_type = "{task_type}"
estimated_duration_minutes = 30
prompt = "Investigate the cross-repository behavior without naming oracle files."

[[repos]]
url = "https://github.com/example/{repo_names[0]}"
rev = "v1.0.0"
path = "{repo_names[0]}"
role = "primary"

[[repos]]
url = "https://github.com/example/{repo_names[1]}"
rev = "v2.0.0"
path = "{repo_names[1]}"
role = "dependency"
"""


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    task_rows = (
        ("dep", "dependency_graph", ("one", "two")),
        ("err", "error_provenance", ("three", "four")),
        ("inc", "incident_investigation", ("five", "six")),
    )
    task_entries = []
    verifier_hashes = {}
    for task_id, task_type, repos in task_rows:
        task_dir = tmp_path / "benchmarks" / task_type / task_id
        task_dir.mkdir(parents=True)
        task_toml = task_dir / "task.toml"
        task_toml.write_text(_task_toml(task_id, task_type, repos))
        task_entries.append(
            {
                "task_id": task_id,
                "task_type": task_type,
                "task_toml": str(task_toml.relative_to(tmp_path)),
                "task_hash": file_hash(task_toml),
                "expected_repositories": [
                    f"github.com/sg-evals/{repos[0]}--v1.0.0",
                    f"github.com/sg-evals/{repos[1]}--v2.0.0",
                ],
                "selection_audit": {
                    "prompt_leakage": "pass",
                    "structural_verifier": "pass",
                    "prior_run_count": 0,
                },
            }
        )
        verifier_hashes[task_id] = PROVENANCE.verifier_hash

    curated = tmp_path / "candidate_manifest.json"
    curated.write_text(
        json.dumps(
            {
                "status": "candidate",
                "task_ids": [task_id for task_id, *_rest in task_rows],
            }
        )
    )
    manifest = tmp_path / "pilot_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "locked-pilot",
                "study_id": "finder-interface-pilot-v1",
                "curated_manifest": "candidate_manifest.json",
                "curated_manifest_hash": file_hash(curated),
                "selection": {
                    "rule": "declared duration then task_id; reject only prompt leakage, unavailable mirrors, or structural verifier failure",
                    "outcomes_inspected": False,
                    "rejections": [],
                },
                "tasks": task_entries,
                "treatment_contract": REQUIRED_TREATMENT_CONTRACT,
                "cache_isolation": {
                    "schema_version": 1,
                    "required": True,
                    "comparison_rule": "valid proof and cross_run_cache_read_tokens == 0",
                    "legacy_evidence": "comparison_ineligible",
                },
                "judge_configuration": REQUIRED_JUDGE,
                "execution_configuration": REQUIRED_EXECUTION,
                "estimands": {
                    "primary": "paired_task_score_difference_cli_minus_mcp",
                    "secondary": [
                        "reported_outer_cost_usd",
                        "elapsed_seconds",
                        "combined_tokens",
                        "finder_activity",
                    ],
                    "inference": "descriptive_only_n3",
                },
                "spend_guard": {
                    "slots": 6,
                    "paid_dispatch_requires_separate_explicit_authorization": True,
                    "calibrated_reported_outer_spend_usd": 1.38,
                    "inner_finder_cost": "unavailable",
                },
                "evidence_policy": {
                    "exclude_canary_outcomes": True,
                    "excluded_task_ids": ["dep-traversal-003"],
                    "promotion": "none",
                },
                "harness_hash": PROVENANCE.harness_hash,
                "verifier_hashes": verifier_hashes,
            }
        )
    )
    spec = tmp_path / "study_spec.json"
    spec.write_text(
        json.dumps(
            {
                "study_id": "finder-interface-pilot-v1",
                "schema_version": 1,
                "task_manifest_hash": file_hash(manifest),
                "task_ids": [task_id for task_id, *_rest in task_rows],
                "arms": [
                    {"name": name, "capability_fingerprint": fingerprint}
                    for name, fingerprint in REQUIRED_ARMS
                ],
                "baseline_arm": "mcp_code_finder",
                "repetitions": 1,
                "attempt_policy": "first_valid_attempt",
                "max_attempts": 1,
                "model": "claude-sonnet-5",
                "harness": PROVENANCE.harness_hash,
                "revision": "abc123",
                "token_source": "sdk_model_usage",
                "score_contract": "weighted-mean-v2",
                "promotion_policy": "descriptive-interface-pilot-no-promotion",
            }
        )
    )
    return spec, manifest, curated


def _validate(tmp_path: Path):
    spec, manifest, curated = _write_fixture(tmp_path)
    return validate_interface_pilot(
        spec_path=spec,
        manifest_path=manifest,
        curated_manifest_path=curated,
        repo_root=tmp_path,
        revision_validator=lambda _revision, _paths: True,
        provenance_provider=_provenance,
        mirror_probe=lambda _repository: True,
    )


def test_locked_contract_compiles_six_matched_slots(tmp_path: Path) -> None:
    evidence = _validate(tmp_path)

    assert len(evidence.slots) == 6
    assert evidence.slots[0] == ("dep", "mcp_code_finder", 1)
    assert evidence.slots[1] == ("dep", "cli_code_finder", 1)
    assert evidence.mirror_repositories == (
        "github.com/sg-evals/one--v1.0.0",
        "github.com/sg-evals/two--v2.0.0",
        "github.com/sg-evals/three--v1.0.0",
        "github.com/sg-evals/four--v2.0.0",
        "github.com/sg-evals/five--v1.0.0",
        "github.com/sg-evals/six--v2.0.0",
    )


@pytest.mark.parametrize(
    ("target", "field", "value", "message"),
    [
        ("manifest", "treatment_contract", {}, "treatment contract"),
        ("manifest", "cache_isolation", {}, "cache-isolation contract"),
        ("manifest", "spend_guard", {}, "spend guard"),
        ("manifest", "evidence_policy", {}, "evidence policy"),
        ("spec", "max_attempts", 2, "interface-pilot contract"),
        (
            "spec",
            "promotion_policy",
            "paired-valid-complete-arms",
            "interface-pilot contract",
        ),
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
    (manifest if target == "manifest" else spec)[field] = value
    manifest_path.write_text(json.dumps(manifest))
    spec["task_manifest_hash"] = file_hash(manifest_path)
    spec_path.write_text(json.dumps(spec))

    with pytest.raises(ValueError, match=message):
        validate_interface_pilot(
            spec_path=spec_path,
            manifest_path=manifest_path,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=_provenance,
            mirror_probe=lambda _repository: True,
        )


def test_wrong_task_type_mix_fails_closed(tmp_path: Path) -> None:
    spec_path, manifest_path, curated = _write_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["tasks"][0]["task_type"] = "incident_investigation"
    manifest_path.write_text(json.dumps(manifest))
    spec = json.loads(spec_path.read_text())
    spec["task_manifest_hash"] = file_hash(manifest_path)
    spec_path.write_text(json.dumps(spec))

    with pytest.raises(ValueError, match="identity/type"):
        validate_interface_pilot(
            spec_path=spec_path,
            manifest_path=manifest_path,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=_provenance,
            mirror_probe=lambda _repository: True,
        )


def test_unavailable_mirror_fails_closed(tmp_path: Path) -> None:
    spec, manifest, curated = _write_fixture(tmp_path)

    with pytest.raises(ValueError, match="Sourcegraph mirror is unavailable"):
        validate_interface_pilot(
            spec_path=spec,
            manifest_path=manifest,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=_provenance,
            mirror_probe=lambda repository: not repository.endswith("six--v2.0.0"),
        )


def test_prior_run_or_failed_audit_fails_closed(tmp_path: Path) -> None:
    spec_path, manifest_path, curated = _write_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["tasks"][1]["selection_audit"]["prior_run_count"] = 1
    manifest_path.write_text(json.dumps(manifest))
    spec = json.loads(spec_path.read_text())
    spec["task_manifest_hash"] = file_hash(manifest_path)
    spec_path.write_text(json.dumps(spec))

    with pytest.raises(ValueError, match="selection audit"):
        validate_interface_pilot(
            spec_path=spec_path,
            manifest_path=manifest_path,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=_provenance,
            mirror_probe=lambda _repository: True,
        )


def test_repository_capsule_is_frozen_and_self_consistent() -> None:
    study_dir = (
        PROJECT_ROOT / "configs" / "studies" / "rryas_code_finder_interface_pilot_v1"
    )

    evidence = validate_interface_pilot(
        spec_path=study_dir / "study_spec.json",
        manifest_path=study_dir / "pilot_manifest.json",
        curated_manifest_path=(
            PROJECT_ROOT / "results" / "rryas_dataset" / "candidate_manifest.json"
        ),
        repo_root=PROJECT_ROOT,
        mirror_probe=lambda _repository: True,
    )

    assert evidence.study_id == "rryas-code-finder-interface-pilot-v1"
    assert len(evidence.task_ids) == 3
    assert len(evidence.slots) == 6


def test_cli_prints_locked_evidence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    study_dir = (
        PROJECT_ROOT / "configs" / "studies" / "rryas_code_finder_interface_pilot_v1"
    )
    monkeypatch.setattr(
        preflight_module, "_default_mirror_probe", lambda _repository: True
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
    assert json.loads(capsys.readouterr().out)["slots"] == [
        ["dep-graph-dual-junit-mockito-001", "mcp_code_finder", 1],
        ["dep-graph-dual-junit-mockito-001", "cli_code_finder", 1],
        ["error-prov-dual-otel-jaeger-001", "mcp_code_finder", 1],
        ["error-prov-dual-otel-jaeger-001", "cli_code_finder", 1],
        ["incident-investigation-dual-istio-001", "mcp_code_finder", 1],
        ["incident-investigation-dual-istio-001", "cli_code_finder", 1],
    ]
