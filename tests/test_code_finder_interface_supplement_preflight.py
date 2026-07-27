from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "orchestration"))

import code_finder_interface_supplement_preflight as preflight_module  # noqa: E402
from code_finder_interface_pilot_preflight import REQUIRED_ARMS  # noqa: E402
from code_finder_interface_supplement_preflight import (  # noqa: E402
    REPORT_PATH,
    validate_interface_supplement,
)
from eb_study import file_hash  # noqa: E402
from study_run import InputProvenance  # noqa: E402

PROVENANCE = InputProvenance(
    task_hash="sha256:task",
    harness_hash="sha256:harness",
    verifier_hash="sha256:verifier",
)
TASK_ID = "incident-investigation-dual-nerdctl-001"


def _task_toml() -> str:
    return f"""
difficulty_stratum = "dual_repo"

[task]
id = "{TASK_ID}"
task_type = "incident_investigation"
estimated_duration_minutes = 45
prompt = "Metadata is not the delivered agent instruction. Write {REPORT_PATH}."

[[repos]]
url = "https://github.com/containerd/nerdctl"
rev = "v2.0.0"
path = "nerdctl"
role = "primary"

[[repos]]
url = "https://github.com/containerd/containerd"
rev = "v1.7.24"
path = "containerd"
role = "dependency"

[artifacts]
required = ["incident_report"]

[[checkpoints]]
name = "root_cause"
weight = 1.0
verifier = "checks/check_root_cause.sh"
"""


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    task_dir = tmp_path / "benchmarks" / "incident_response" / TASK_ID
    checks_dir = task_dir / "checks"
    checks_dir.mkdir(parents=True)
    task_toml = task_dir / "task.toml"
    task_toml.write_text(_task_toml())
    (task_dir / "instruction.md").write_text(
        "Investigate both repositories and cite the code you find.\n"
        f"Write the result to `{REPORT_PATH}`.\n"
    )
    (checks_dir / "check_root_cause.sh").write_text(
        '#!/usr/bin/env bash\nREPORT="${WORKSPACE:-/workspace}'
        '/agent_output/INCIDENT_REPORT.md"\n'
    )
    (task_dir / "expected_solution.json").write_text(
        json.dumps(
            {
                "task_id": TASK_ID,
                "checkpoints": {
                    "root_cause": {
                        "expected_solution": "Identify the cross-repo root cause.",
                        "evaluation_criteria": ["Cite repo one", "Cite repo two"],
                    }
                },
            }
        )
    )

    curated = tmp_path / "candidate_manifest.json"
    curated.write_text(json.dumps({"status": "candidate", "task_ids": [TASK_ID]}))
    manifest = tmp_path / "pilot_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "locked-supplement",
                "study_id": "rryas-code-finder-interface-supplement-v1",
                "parent_study_id": "rryas-code-finder-interface-pilot-v1",
                "curated_manifest": "candidate_manifest.json",
                "curated_manifest_hash": file_hash(curated),
                "selection": {
                    "rule": (
                        "among previously unrun curated dual-repository incident "
                        "tasks, sort by declared duration then task_id; reject prompt "
                        "leakage or structural ineligibility; select the first "
                        "passing task"
                    ),
                    "candidate_outcomes_inspected": False,
                    "parent_invalidity_trigger": "output path only",
                    "candidate_order": [
                        "incident-investigation-dual-flux-001",
                        "incident-investigation-dual-prometheus-001",
                        "incident-investigation-dual-kafka-001",
                        TASK_ID,
                    ],
                    "rejections": [
                        {
                            "candidate_id": candidate,
                            "reason": "prompt_leakage",
                            "detail": "The delivered instruction supplies the oracle.",
                            "candidate_outcomes_inspected": False,
                        }
                        for candidate in (
                            "incident-investigation-dual-flux-001",
                            "incident-investigation-dual-prometheus-001",
                            "incident-investigation-dual-kafka-001",
                        )
                    ],
                    "selected": {
                        "task_id": TASK_ID,
                        "declared_duration_minutes": 45,
                        "prior_run_count": 0,
                        "prompt_leakage": "pass",
                        "structural_eligibility": "pass",
                        "candidate_outcomes_inspected": False,
                    },
                },
                "tasks": [
                    {
                        "task_id": TASK_ID,
                        "task_type": "incident_investigation",
                        "task_toml": str(task_toml.relative_to(tmp_path)),
                        "task_hash": file_hash(task_toml),
                        "graded_artifact_path": REPORT_PATH,
                        "expected_repositories": [
                            "github.com/sg-evals/nerdctl--v2.0.0",
                            "github.com/sg-evals/containerd--v1.7.24",
                        ],
                    }
                ],
                "treatment_contract": {
                    "finder_calls": "exactly_once_per_repository",
                    "other_sgx_retrieval_allowed": False,
                    "direct_sourcegraph_retrieval_allowed": False,
                    "local_repository_source_readable": False,
                    "same_proxy_telemetry_required": True,
                    "required_telemetry": [
                        "invocation_count",
                        "repository_scope",
                        "sourcegraphToolTelemetry",
                        "tool_inventory_sha256",
                        "code_finder_schema_sha256",
                        "interface_call_count",
                        "proxy_call_count",
                        "cache_isolation",
                    ],
                    "invalid_if": [
                        "zero_or_wrong_code_finder_call_count",
                        "interface_and_proxy_call_count_mismatch",
                        "ambiguous_or_wrong_repository_scope",
                        "any_other_sgx_retrieval_call",
                        "any_direct_sourcegraph_retrieval_call",
                        "failed_code_finder_response",
                        "missing_sourcegraphToolTelemetry",
                        "missing_or_malformed_proxy_trace",
                        "missing_or_invalid_cache_isolation_proof",
                        "cross_run_cache_read_tokens_nonzero",
                    ],
                },
                "cache_isolation": {
                    "schema_version": 1,
                    "required": True,
                    "comparison_rule": (
                        "valid proof and cross_run_cache_read_tokens == 0"
                    ),
                    "legacy_evidence": "comparison_ineligible",
                },
                "judge_configuration": {
                    "model": "cc:haiku",
                    "account": 1,
                    "executable": "claude-1",
                    "selection": "explicit --judge-account 1",
                    "provenance_required_in_scores": True,
                },
                "execution_configuration": {
                    "agent_account": 3,
                    "timeout_seconds": 600,
                    "build_timeout_seconds": 1800,
                    "verifier_timeout_seconds": 600,
                    "memory_mb": 8192,
                    "no_build": True,
                    "max_attempts": 1,
                    "execution_order": [
                        [TASK_ID, "mcp_code_finder", 1],
                        [TASK_ID, "cli_code_finder", 1],
                    ],
                },
                "estimands": {
                    "primary": "paired_task_score_difference_cli_minus_mcp",
                    "secondary": [
                        "reported_outer_cost_usd",
                        "elapsed_seconds",
                        "combined_tokens",
                        "finder_activity",
                    ],
                    "combined_analysis": "append one valid pair",
                    "inference": "descriptive_only_n3_after_valid_supplement",
                },
                "spend_guard": {
                    "slots": 2,
                    "max_attempts_per_slot": 1,
                    "paid_dispatch_requires_new_explicit_authorization": True,
                    "forecast_reported_outer_spend_usd": 3.61,
                    "forecast_basis": "observed incident-pair cost",
                    "inner_finder_cost": "unavailable",
                },
                "evidence_policy": {
                    "exclude_parent_invalid_pair_from_quality": True,
                    "parent_invalid_task_id": (
                        "incident-investigation-dual-istio-001"
                    ),
                    "promotion": "none",
                },
                "harness_hash": PROVENANCE.harness_hash,
                "verifier_hashes": {TASK_ID: PROVENANCE.verifier_hash},
            }
        )
    )
    spec = tmp_path / "study_spec.json"
    spec.write_text(
        json.dumps(
            {
                "study_id": "rryas-code-finder-interface-supplement-v1",
                "schema_version": 1,
                "task_manifest_hash": file_hash(manifest),
                "task_ids": [TASK_ID],
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
                "promotion_policy": "descriptive-interface-supplement-no-promotion",
            }
        )
    )
    return spec, manifest, curated


def _validate(tmp_path: Path):
    spec, manifest, curated = _write_fixture(tmp_path)
    return validate_interface_supplement(
        spec_path=spec,
        manifest_path=manifest,
        curated_manifest_path=curated,
        repo_root=tmp_path,
        revision_validator=lambda _revision, _paths: True,
        provenance_provider=lambda task_toml: InputProvenance(
            task_hash=file_hash(task_toml),
            harness_hash=PROVENANCE.harness_hash,
            verifier_hash=PROVENANCE.verifier_hash,
        ),
        mirror_probe=lambda _repository: True,
    )


def test_locked_supplement_compiles_two_spend_gated_slots(tmp_path: Path) -> None:
    evidence = _validate(tmp_path)

    assert evidence.slots == (
        (TASK_ID, "mcp_code_finder", 1),
        (TASK_ID, "cli_code_finder", 1),
    )
    assert evidence.graded_artifact_path == REPORT_PATH
    assert evidence.paid_dispatch_authorized is False


def test_corrected_v2_identity_preserves_the_same_locked_slots(
    tmp_path: Path,
) -> None:
    spec_path, manifest_path, curated = _write_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["study_id"] = "rryas-code-finder-interface-supplement-v2"
    manifest["parent_study_id"] = "rryas-code-finder-interface-supplement-v1"
    manifest_path.write_text(json.dumps(manifest))
    spec = json.loads(spec_path.read_text())
    spec["study_id"] = manifest["study_id"]
    spec["task_manifest_hash"] = file_hash(manifest_path)
    spec_path.write_text(json.dumps(spec))

    evidence = validate_interface_supplement(
        spec_path=spec_path,
        manifest_path=manifest_path,
        curated_manifest_path=curated,
        repo_root=tmp_path,
        revision_validator=lambda _revision, _paths: True,
        provenance_provider=lambda task_toml: InputProvenance(
            task_hash=file_hash(task_toml),
            harness_hash=PROVENANCE.harness_hash,
            verifier_hash=PROVENANCE.verifier_hash,
        ),
        mirror_probe=lambda _repository: True,
    )

    assert evidence.study_id == manifest["study_id"]
    assert len(evidence.slots) == 2
    assert evidence.paid_dispatch_authorized is False


@pytest.mark.parametrize(
    ("target", "field", "value", "message"),
    [
        ("spec", "max_attempts", 2, "supplement contract"),
        ("manifest", "spend_guard", {}, "spend guard"),
        (
            "manifest",
            "harness_hash",
            "sha256:drift",
            "current harness",
        ),
    ],
)
def test_contract_or_provenance_drift_fails_closed(
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
        validate_interface_supplement(
            spec_path=spec_path,
            manifest_path=manifest_path,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: InputProvenance(
                task_hash=file_hash(task_toml),
                harness_hash=PROVENANCE.harness_hash,
                verifier_hash=PROVENANCE.verifier_hash,
            ),
            mirror_probe=lambda _repository: True,
        )


def test_repo_local_report_path_fails_closed(tmp_path: Path) -> None:
    spec_path, manifest_path, curated = _write_fixture(tmp_path)
    task_dir = tmp_path / "benchmarks" / "incident_response" / TASK_ID
    repo_report = "/workspace/nerdctl/INCIDENT_REPORT.md"
    check = task_dir / "checks" / "check_root_cause.sh"
    check.write_text(
        '#!/usr/bin/env bash\nREPORT="${WORKSPACE:-/workspace}'
        '/nerdctl/INCIDENT_REPORT.md"\n'
    )
    manifest = json.loads(manifest_path.read_text())
    manifest["tasks"][0]["graded_artifact_path"] = repo_report
    manifest_path.write_text(json.dumps(manifest))
    spec = json.loads(spec_path.read_text())
    spec["task_manifest_hash"] = file_hash(manifest_path)
    spec_path.write_text(json.dumps(spec))

    with pytest.raises(ValueError, match="writable outside gated repositories"):
        validate_interface_supplement(
            spec_path=spec_path,
            manifest_path=manifest_path,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: InputProvenance(
                task_hash=file_hash(task_toml),
                harness_hash=PROVENANCE.harness_hash,
                verifier_hash=PROVENANCE.verifier_hash,
            ),
            mirror_probe=lambda _repository: True,
        )


def test_delivered_instruction_cannot_conflict_with_report_path(
    tmp_path: Path,
) -> None:
    spec, manifest, curated = _write_fixture(tmp_path)
    task_dir = tmp_path / "benchmarks" / "incident_response" / TASK_ID
    (task_dir / "instruction.md").write_text(
        "Write the result to `/workspace/agent_output/answer.json`."
    )

    with pytest.raises(ValueError, match="delivered instruction"):
        validate_interface_supplement(
            spec_path=spec,
            manifest_path=manifest,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: InputProvenance(
                task_hash=file_hash(task_toml),
                harness_hash=PROVENANCE.harness_hash,
                verifier_hash=PROVENANCE.verifier_hash,
            ),
            mirror_probe=lambda _repository: True,
        )


def test_runtime_checkpoint_names_must_match_expected_solution(
    tmp_path: Path,
) -> None:
    spec, manifest, curated = _write_fixture(tmp_path)
    expected = (
        tmp_path
        / "benchmarks"
        / "incident_response"
        / TASK_ID
        / "expected_solution.json"
    )
    payload = json.loads(expected.read_text())
    payload["checkpoints"] = {
        "check_root_cause": payload["checkpoints"]["root_cause"]
    }
    expected.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="runtime checkpoint names"):
        validate_interface_supplement(
            spec_path=spec,
            manifest_path=manifest,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: InputProvenance(
                task_hash=file_hash(task_toml),
                harness_hash=PROVENANCE.harness_hash,
                verifier_hash=PROVENANCE.verifier_hash,
            ),
            mirror_probe=lambda _repository: True,
        )


def test_unavailable_mirror_fails_closed(tmp_path: Path) -> None:
    spec, manifest, curated = _write_fixture(tmp_path)

    with pytest.raises(ValueError, match="Sourcegraph mirror is unavailable"):
        validate_interface_supplement(
            spec_path=spec,
            manifest_path=manifest,
            curated_manifest_path=curated,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: InputProvenance(
                task_hash=file_hash(task_toml),
                harness_hash=PROVENANCE.harness_hash,
                verifier_hash=PROVENANCE.verifier_hash,
            ),
            mirror_probe=lambda repository: not repository.endswith(
                "containerd--v1.7.24"
            ),
        )


def test_invalid_v1_supplement_is_frozen_as_historical_evidence() -> None:
    study_dir = (
        PROJECT_ROOT
        / "configs"
        / "studies"
        / "rryas_code_finder_interface_supplement_v1"
    )
    results_dir = (
        PROJECT_ROOT
        / "results"
        / "studies"
        / "rryas_code_finder_interface_supplement_v1"
    )

    with pytest.raises(ValueError, match="current harness"):
        validate_interface_supplement(
            spec_path=study_dir / "study_spec.json",
            manifest_path=study_dir / "pilot_manifest.json",
            curated_manifest_path=(
                PROJECT_ROOT
                / "results"
                / "rryas_dataset"
                / "candidate_manifest.json"
            ),
            repo_root=PROJECT_ROOT,
            mirror_probe=lambda _repository: True,
        )

    receipts = [
        json.loads(line)
        for line in (results_dir / "receipts.jsonl").read_text().splitlines()
    ]
    assert len(receipts) == 1
    assert receipts[0]["trial"] == {
        "study_id": "rryas-code-finder-interface-supplement-v1",
        "task_id": TASK_ID,
        "arm": "mcp_code_finder",
        "repetition": 1,
        "attempt": 1,
    }
    assert receipts[0]["status"] == "infra_invalid"
    assert receipts[0]["failure_class"] == "verifier_infra_error"
    assert receipts[0]["score"] is None


def test_cli_prints_spend_gated_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec, manifest, curated = _write_fixture(tmp_path)
    monkeypatch.setattr(preflight_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        preflight_module, "_default_mirror_probe", lambda _repository: True
    )
    monkeypatch.setattr(
        preflight_module,
        "_default_provenance_provider",
        lambda _repo_root: (
            lambda task_toml: InputProvenance(
                task_hash=file_hash(task_toml),
                harness_hash=PROVENANCE.harness_hash,
                verifier_hash=PROVENANCE.verifier_hash,
            )
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
                str(spec),
                "--manifest",
                str(manifest),
                "--curated-manifest",
                str(curated),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["paid_dispatch_authorized"] is False
