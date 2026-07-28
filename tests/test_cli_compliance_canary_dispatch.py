from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for import_path in (
    PROJECT_ROOT / "lib",
    PROJECT_ROOT / "scripts" / "infra",
    PROJECT_ROOT / "scripts" / "orchestration",
):
    sys.path.insert(0, str(import_path))

from cli_compliance_canary_dispatch import (  # noqa: E402
    CanaryDispatchError,
    compile_canary_command,
    dispatch_cli_compliance_canary,
    load_canary_dispatch_plan,
)
from eb_study import StudySpec, file_hash  # noqa: E402


def _write_fixture(tmp_path: Path, *, authorized: bool = False) -> tuple[Path, Path]:
    task_toml = tmp_path / "benchmarks" / "task-a" / "task.toml"
    task_toml.parent.mkdir(parents=True)
    task_toml.write_text('[task]\nid = "task-a"\n')
    manifest = {
        "schema_version": 1,
        "study_id": "rryas-headline-v2-cli-compliance-canary",
        "status": "FINAL-NO-SPEND",
        "purpose": "operational CLI compliance only",
        "task_id": "task-a",
        "task_toml": str(task_toml.relative_to(tmp_path)),
        "mode": "cli",
        "harness": "claude",
        "model": "claude-sonnet-5",
        "agent_account": 3,
        "judge_account": 1,
        "max_attempts": 1,
        "harness_hash": "sha256:harness",
        "revision": "a" * 40,
        "output_root": "results/studies/canary",
        "receipts": "results/studies/canary/receipts.jsonl",
        "success_criterion": "sgx_tool_calls > 0",
        "execution": {
            "timeout_seconds": 600,
            "build_timeout_seconds": 1800,
            "verifier_timeout_seconds": 600,
            "memory_mb": 8192,
            "no_build": False,
        },
    }
    manifest_path = tmp_path / "canary_manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    spec_path = tmp_path / "canary_spec.json"
    spec_payload = {
        "study_id": manifest["study_id"],
        "schema_version": 1,
        "task_manifest_hash": file_hash(manifest_path),
        "task_ids": ["task-a"],
        "arms": [
            {
                "name": "cli",
                "capability_fingerprint": (
                    "sgx-cli:local-repos-readable:retrieval-before-local:"
                    "cache-isolated:v3"
                ),
            }
        ],
        "baseline_arm": "cli",
        "repetitions": 1,
        "attempt_policy": "first_valid_attempt",
        "max_attempts": 1,
        "model": "claude-sonnet-5",
        "harness": "sha256:harness",
        "revision": "a" * 40,
        "token_source": "sdk_model_usage",
        "score_contract": "weighted-mean-v2",
        "promotion_policy": "operational-cli-compliance-no-promotion",
    }
    spec_path.write_text(json.dumps(spec_payload))
    sample_path = tmp_path / "sample_receipts.jsonl"
    sample_path.write_text(
        json.dumps(
            {
                "usage": {"cost_usd": 9.0},
                "tool_use": {
                    "cache_isolation": {
                        "valid": True,
                        "cache_write_tokens": 0,
                        "cross_run_cache_read_tokens": 0,
                    }
                },
            }
        )
        + "\n"
    )
    plan_path = tmp_path / "canary_dispatch.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "study_id": manifest["study_id"],
                "status": "LOCKED-NO-SPEND",
                "manifest": str(manifest_path.relative_to(tmp_path)),
                "manifest_hash": file_hash(manifest_path),
                "study_spec": str(spec_path.relative_to(tmp_path)),
                "study_spec_file_hash": file_hash(spec_path),
                "study_spec_hash": StudySpec.load(spec_path).spec_hash,
                "cost_forecast": {
                    "sample_receipts": [
                        {
                            "path": str(sample_path.relative_to(tmp_path)),
                            "sha256": file_hash(sample_path),
                        }
                    ],
                    "sample_attempts": 1,
                    "sample_outer_spend_usd": 9.0,
                    "mean_per_slot_usd": 9.0,
                    "forecast_outer_spend_usd": 9.0,
                    "max_observed_per_slot_usd": 9.0,
                    "empirical_slot_count_envelope_usd": 9.0,
                    "authorization_outer_spend_ceiling_usd": 10.0,
                    "uncovered_costs": ["fixture"],
                },
                "authorization": {
                    "paid_dispatch_authorized": authorized,
                    "authorization_reference": "test-auth" if authorized else None,
                },
            }
        )
    )
    return plan_path, tmp_path / manifest["receipts"]


def _load(plan_path: Path):
    return load_canary_dispatch_plan(
        plan_path,
        repo_root=plan_path.parent,
        provenance_provider=lambda _task: SimpleNamespace(
            task_hash="unused",
            harness_hash="sha256:harness",
            verifier_hash="unused",
        ),
        revision_validator=lambda _revision, _paths: True,
    )


def test_preview_compiles_exactly_one_cli_command_without_creating_outputs(
    tmp_path: Path,
) -> None:
    plan_path, receipts_path = _write_fixture(tmp_path)

    summary = dispatch_cli_compliance_canary(
        plan_path,
        repo_root=tmp_path,
        execute=False,
        plan_loader=_load,
    )

    assert summary.executed is False
    assert summary.command == compile_canary_command(_load(plan_path), tmp_path)
    assert "--mode" in summary.command
    assert summary.command[summary.command.index("--mode") + 1] == "cli"
    assert not receipts_path.parent.exists()


def test_execute_requires_fresh_paid_authorization(tmp_path: Path) -> None:
    plan_path, _receipts_path = _write_fixture(tmp_path)

    with pytest.raises(CanaryDispatchError, match="not authorized"):
        dispatch_cli_compliance_canary(
            plan_path,
            repo_root=tmp_path,
            execute=True,
            plan_loader=_load,
        )


def test_repository_canary_is_previewable_and_spend_locked() -> None:
    plan_path = (
        PROJECT_ROOT / "configs/studies/rryas-headline-v2/"
        "cli_compliance_canary_dispatch_plan.json"
    )

    plan = load_canary_dispatch_plan(plan_path, repo_root=PROJECT_ROOT)
    command = compile_canary_command(plan, PROJECT_ROOT)

    assert plan.paid_dispatch_authorized is False
    assert plan.spec.slots() == (("api-contract-dual-envoy-istio-001", "cli", 1),)
    assert command.count("--attempt") == 1
