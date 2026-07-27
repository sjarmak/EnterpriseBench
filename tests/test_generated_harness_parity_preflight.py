from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "orchestration"))

import generated_harness_parity_preflight as preflight_module  # noqa: E402
from eb_study import file_hash  # noqa: E402
from generated_harness_parity_preflight import (  # noqa: E402
    CAPSULE_ID,
    CODEX_STUDY_ID,
    OPENCODE_STUDY_ID,
    REPORT_PATH,
    TASK_ID,
    validate_generated_harness_parity,
)
from study_run import InputProvenance  # noqa: E402

PROVENANCE = InputProvenance(
    task_hash="sha256:task",
    harness_hash="sha256:harness",
    verifier_hash="sha256:verifier",
)


def _task_toml() -> str:
    return f"""
difficulty_stratum = "dual_repo"

[task]
id = "{TASK_ID}"
task_type = "incident_investigation"
estimated_duration_minutes = 45
prompt = "Write {REPORT_PATH}."

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

    manifest_path = tmp_path / "parity_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "locked-no-spend-capsule",
                "capsule_id": CAPSULE_ID,
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
                "bundles": [
                    {
                        "harness": "codex",
                        "study_id": CODEX_STUDY_ID,
                        "model": "gpt-5.6-sol",
                        "study_spec": "codex_study_spec.json",
                        "output_root": "results/studies/codex-parity",
                        "receipts": "results/studies/codex-parity/receipts.jsonl",
                    },
                    {
                        "harness": "opencode",
                        "study_id": OPENCODE_STUDY_ID,
                        "model": "openrouter/moonshotai/kimi-k3",
                        "study_spec": "opencode_study_spec.json",
                        "output_root": "results/studies/opencode-parity",
                        "receipts": "results/studies/opencode-parity/receipts.jsonl",
                    },
                ],
                "treatment_contract": preflight_module.REQUIRED_TREATMENT_CONTRACT,
                "cache_isolation": preflight_module.REQUIRED_CACHE_ISOLATION,
                "judge_configuration": preflight_module.REQUIRED_JUDGE,
                "execution_configuration": preflight_module.REQUIRED_EXECUTION,
                "comparison_policy": preflight_module.REQUIRED_COMPARISON_POLICY,
                "spend_guard": preflight_module.REQUIRED_SPEND_GUARD,
                "harness_hash": PROVENANCE.harness_hash,
                "verifier_hashes": {TASK_ID: PROVENANCE.verifier_hash},
            }
        )
    )

    specs = []
    for harness, study_id, model in (
        ("codex", CODEX_STUDY_ID, "gpt-5.6-sol"),
        ("opencode", OPENCODE_STUDY_ID, "openrouter/moonshotai/kimi-k3"),
    ):
        path = tmp_path / f"{harness}_study_spec.json"
        path.write_text(
            json.dumps(
                {
                    "study_id": study_id,
                    "schema_version": 1,
                    "task_manifest_hash": file_hash(manifest_path),
                    "task_ids": [TASK_ID],
                    "arms": [
                        {"name": name, "capability_fingerprint": fingerprint}
                        for name, fingerprint in preflight_module.REQUIRED_ARMS
                    ],
                    "baseline_arm": "mcp_code_finder",
                    "repetitions": 1,
                    "attempt_policy": "first_valid_attempt",
                    "max_attempts": 1,
                    "model": model,
                    "harness": PROVENANCE.harness_hash,
                    "revision": "abc123",
                    "token_source": "provider_native_usage",
                    "score_contract": "weighted-mean-v2",
                    "promotion_policy": (
                        "descriptive-generated-harness-parity-no-promotion"
                    ),
                }
            )
        )
        specs.append(path)
    return manifest_path, specs[0], specs[1]


def _validate(tmp_path: Path):
    manifest, codex_spec, opencode_spec = _write_fixture(tmp_path)
    return validate_generated_harness_parity(
        manifest_path=manifest,
        codex_spec_path=codex_spec,
        opencode_spec_path=opencode_spec,
        repo_root=tmp_path,
        revision_validator=lambda _revision, _paths: True,
        provenance_provider=lambda task_toml: InputProvenance(
            task_hash=file_hash(task_toml),
            harness_hash=PROVENANCE.harness_hash,
            verifier_hash=PROVENANCE.verifier_hash,
        ),
        mirror_probe=lambda _repository: True,
        auth_probe=lambda _credential: True,
    )


def test_locked_capsule_compiles_exactly_four_no_retry_slots(tmp_path: Path) -> None:
    evidence = _validate(tmp_path)

    assert evidence.slots == (
        ("codex", TASK_ID, "mcp_code_finder", 1, 1),
        ("codex", TASK_ID, "cli_code_finder", 1, 1),
        ("opencode", TASK_ID, "mcp_code_finder", 1, 1),
        ("opencode", TASK_ID, "cli_code_finder", 1, 1),
    )
    assert evidence.paid_dispatch_authorized is False
    assert evidence.graded_artifact_path == REPORT_PATH


def test_cross_bundle_claim_is_explicitly_descriptive(tmp_path: Path) -> None:
    evidence = _validate(tmp_path)

    assert evidence.comparison_label == "harness-model bundles; descriptive only"


@pytest.mark.parametrize(
    ("spec_name", "field", "value", "message"),
    [
        ("codex", "model", "gpt-5.5", "Codex study contract"),
        ("opencode", "max_attempts", 2, "OpenCode study contract"),
        ("opencode", "token_source", "sdk_model_usage", "OpenCode study contract"),
    ],
)
def test_study_contract_drift_fails_closed(
    tmp_path: Path,
    spec_name: str,
    field: str,
    value: object,
    message: str,
) -> None:
    manifest, codex_spec, opencode_spec = _write_fixture(tmp_path)
    path = codex_spec if spec_name == "codex" else opencode_spec
    payload = json.loads(path.read_text())
    payload[field] = value
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match=message):
        validate_generated_harness_parity(
            manifest_path=manifest,
            codex_spec_path=codex_spec,
            opencode_spec_path=opencode_spec,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: InputProvenance(
                task_hash=file_hash(task_toml),
                harness_hash=PROVENANCE.harness_hash,
                verifier_hash=PROVENANCE.verifier_hash,
            ),
            mirror_probe=lambda _repository: True,
            auth_probe=lambda _credential: True,
        )


def test_existing_run_output_fails_closed(tmp_path: Path) -> None:
    manifest, codex_spec, opencode_spec = _write_fixture(tmp_path)
    output = tmp_path / "results" / "studies" / "codex-parity"
    output.mkdir(parents=True)
    (output / "results.json").write_text("{}")

    with pytest.raises(ValueError, match="output root is not clean"):
        validate_generated_harness_parity(
            manifest_path=manifest,
            codex_spec_path=codex_spec,
            opencode_spec_path=opencode_spec,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: InputProvenance(
                task_hash=file_hash(task_toml),
                harness_hash=PROVENANCE.harness_hash,
                verifier_hash=PROVENANCE.verifier_hash,
            ),
            mirror_probe=lambda _repository: True,
            auth_probe=lambda _credential: True,
        )


def test_missing_credential_fails_closed_without_reading_a_secret(
    tmp_path: Path,
) -> None:
    manifest, codex_spec, opencode_spec = _write_fixture(tmp_path)

    with pytest.raises(ValueError, match="OpenRouter authentication"):
        validate_generated_harness_parity(
            manifest_path=manifest,
            codex_spec_path=codex_spec,
            opencode_spec_path=opencode_spec,
            repo_root=tmp_path,
            revision_validator=lambda _revision, _paths: True,
            provenance_provider=lambda task_toml: InputProvenance(
                task_hash=file_hash(task_toml),
                harness_hash=PROVENANCE.harness_hash,
                verifier_hash=PROVENANCE.verifier_hash,
            ),
            mirror_probe=lambda _repository: True,
            auth_probe=lambda credential: credential != "openrouter",
        )


def test_cli_prints_no_spend_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, codex_spec, opencode_spec = _write_fixture(tmp_path)
    monkeypatch.setattr(preflight_module, "REPO_ROOT", tmp_path)
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
    monkeypatch.setattr(
        preflight_module, "_default_mirror_probe", lambda _repository: True
    )
    monkeypatch.setattr(
        preflight_module, "_default_auth_probe", lambda _credential: True
    )

    assert (
        preflight_module.main(
            [
                "--manifest",
                str(manifest),
                "--codex-spec",
                str(codex_spec),
                "--opencode-spec",
                str(opencode_spec),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["paid_dispatch_authorized"] is False
    assert len(payload["slots"]) == 4
