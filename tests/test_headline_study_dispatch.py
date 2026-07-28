from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for import_path in (
    PROJECT_ROOT / "lib",
    PROJECT_ROOT / "scripts" / "infra",
    PROJECT_ROOT / "scripts" / "orchestration",
):
    sys.path.insert(0, str(import_path))

from eb_study import StudySpec, TrialReceipt, file_hash, read_receipts  # noqa: E402
from headline_study_dispatch import (  # noqa: E402
    DispatchError,
    compile_run_command,
    dispatch_headline_study,
    load_dispatch_plan,
)


def _spec_payload(
    manifest_hash: str, *, study_id: str = "rryas-headline-v1"
) -> dict[str, object]:
    return {
        "study_id": study_id,
        "schema_version": 1,
        "task_manifest_hash": manifest_hash,
        "task_ids": ["task-a", "task-b"],
        "arms": [
            {
                "name": "baseline",
                "capability_fingerprint": "baseline:fingerprint",
            },
            {
                "name": "mcp_only",
                "capability_fingerprint": "mcp:fingerprint",
            },
            {"name": "cli", "capability_fingerprint": "cli:fingerprint"},
        ],
        "baseline_arm": "baseline",
        "repetitions": 1,
        "attempt_policy": "first_valid_attempt",
        "max_attempts": 1,
        "model": "claude-sonnet-5",
        "harness": "sha256:harness",
        "revision": "abc123",
        "token_source": "sdk_model_usage",
        "score_contract": "weighted-mean-v2",
        "promotion_policy": "paired-valid-complete-arms",
    }


def _row(
    task_id: str, arm: str, *, study_id: str = "rryas-headline-v1"
) -> dict[str, object]:
    return {
        "candidate_id": task_id,
        "task_id": task_id,
        "arm": arm,
        "repetition": 1,
        "attempt": 1,
        "agent_account": 3,
        "judge_account": 1,
        "output_dir": (
            f"results/studies/{study_id}/runs/{task_id}/{arm}/rep1/attempt1"
        ),
    }


def _write_fixture(
    tmp_path: Path,
    *,
    authorized: bool = False,
    ceiling: float = 20.0,
    per_slot_envelope: float = 2.0,
    study_id: str = "rryas-headline-v1",
) -> tuple[Path, Path, Path, Path, Path]:
    task_paths: dict[str, str] = {}
    for task_id in ("task-a", "task-b"):
        task_toml = tmp_path / "benchmarks" / task_id / "task.toml"
        task_toml.parent.mkdir(parents=True)
        task_toml.write_text(f'[task]\nid = "{task_id}"\n')
        task_paths[task_id] = str(task_toml.relative_to(tmp_path))

    rows = [
        _row("task-a", "baseline", study_id=study_id),
        _row("task-a", "mcp_only", study_id=study_id),
        _row("task-a", "cli", study_id=study_id),
        _row("task-b", "mcp_only", study_id=study_id),
        _row("task-b", "cli", study_id=study_id),
        _row("task-b", "baseline", study_id=study_id),
    ]
    manifest_path = tmp_path / "final_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "study_id": study_id,
                "status": "FINAL-NO-SPEND",
                "tasks": [
                    {"task_id": task_id, "task_toml": path}
                    for task_id, path in task_paths.items()
                ],
                "execution_configuration": {
                    "agent_account": 3,
                    "judge_account": 1,
                    "timeout_seconds": 600,
                    "build_timeout_seconds": 1800,
                    "verifier_timeout_seconds": 600,
                    "memory_mb": 8192,
                    "no_build": False,
                    "execution_order": rows,
                    "receipts": (f"results/studies/{study_id}/receipts.jsonl"),
                },
            },
            sort_keys=True,
        )
    )
    spec_path = tmp_path / "study_spec.json"
    spec_path.write_text(
        json.dumps(
            _spec_payload(file_hash(manifest_path), study_id=study_id),
            sort_keys=True,
        )
    )
    evidence_path = tmp_path / "preflight_evidence.json"
    evidence_path.write_text('{"paid_dispatch_authorized": false}\n')
    receipts_path = tmp_path / "results" / "studies" / study_id / "receipts.jsonl"
    receipts_path.parent.mkdir(parents=True)
    sample_path = tmp_path / "sample_receipts.jsonl"
    sample_path.write_text(
        json.dumps(
            {
                "usage": {"cost_usd": per_slot_envelope},
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

    plan_path = tmp_path / "dispatch_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "study_id": study_id,
                "status": "LOCKED-NO-SPEND",
                "study_spec": str(spec_path.relative_to(tmp_path)),
                "study_spec_file_hash": file_hash(spec_path),
                "study_spec_hash": StudySpec.load(spec_path).spec_hash,
                "final_manifest": str(manifest_path.relative_to(tmp_path)),
                "final_manifest_hash": file_hash(manifest_path),
                "preflight_evidence": str(evidence_path.relative_to(tmp_path)),
                "preflight_evidence_hash": file_hash(evidence_path),
                "cost_forecast": {
                    "basis": "fixture",
                    "sample_receipts": [
                        {
                            "path": str(sample_path.relative_to(tmp_path)),
                            "sha256": file_hash(sample_path),
                        }
                    ],
                    "sample_attempts": 1,
                    "sample_outer_spend_usd": per_slot_envelope,
                    "mean_per_slot_usd": per_slot_envelope,
                    "forecast_outer_spend_usd": per_slot_envelope * 6,
                    "max_observed_per_slot_usd": per_slot_envelope,
                    "empirical_slot_count_envelope_usd": per_slot_envelope * 6,
                    "authorization_outer_spend_ceiling_usd": ceiling,
                    "uncovered_costs": ["fixture-uncovered"],
                },
                "authorization": {
                    "paid_dispatch_authorized": authorized,
                    "authorization_reference": (
                        "test-authorization" if authorized else None
                    ),
                },
            },
            sort_keys=True,
        )
    )
    return plan_path, spec_path, manifest_path, evidence_path, receipts_path


def _receipt(
    spec: StudySpec,
    *,
    task_id: str,
    arm: str,
    cost: float,
    status: str = "valid",
) -> TrialReceipt:
    valid = status == "valid"
    return TrialReceipt.from_json(
        {
            "schema_version": 1,
            "trial": {
                "study_id": spec.study_id,
                "task_id": task_id,
                "arm": arm,
                "repetition": 1,
                "attempt": 1,
            },
            "spec_hash": spec.spec_hash,
            "task_manifest_hash": spec.task_manifest_hash,
            "status": status,
            "failure_class": None if valid else "infra_failure",
            "image_digest": "sha256:image" if valid else None,
            "arm_gate_proof": "mode_gate:proof" if valid else None,
            "task_hash": "sha256:task" if valid else None,
            "harness_hash": spec.harness if valid else None,
            "verifier_hash": "sha256:verifier" if valid else None,
            "score": 0.5 if valid else None,
            "score_contract": spec.score_contract if valid else None,
            "usage": {
                "source": spec.token_source,
                "cost_usd": cost,
                "model_usage": {
                    spec.model: {
                        "input_tokens": 100,
                        "output_tokens": 10,
                        "cache_write_tokens": 0,
                        "cache_read_tokens": 0,
                        "cost_usd": cost,
                    }
                },
            },
            "tool_use": {
                "cache_isolation": {
                    "valid": True,
                    "cache_write_tokens": 0,
                    "cross_run_cache_read_tokens": 0,
                }
            },
            "artifacts": {"results.json": "sha256:result"},
            "started_at": "2026-07-28T00:00:00Z",
            "ended_at": "2026-07-28T00:01:00Z",
        }
    )


def _append(path: Path, receipt: TrialReceipt) -> None:
    output_dir = (
        path.parent
        / "runs"
        / receipt.trial.task_id
        / receipt.trial.arm
        / f"rep{receipt.trial.repetition}"
        / f"attempt{receipt.trial.attempt}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(receipt.to_json(), sort_keys=True) + "\n")


def test_compile_run_command_matches_the_frozen_execution_contract(
    tmp_path: Path,
) -> None:
    plan_path, _, _, _, receipts_path = _write_fixture(tmp_path)
    plan = load_dispatch_plan(plan_path, repo_root=tmp_path)
    command = compile_run_command(plan.slots[0], plan=plan, repo_root=tmp_path)

    assert command[:3] == (
        sys.executable,
        str(tmp_path / "scripts" / "orchestration" / "run_task.py"),
        str(tmp_path / "benchmarks" / "task-a" / "task.toml"),
    )
    assert command[command.index("--mode") + 1] == "baseline"
    assert command[command.index("--account") + 1] == "3"
    assert command[command.index("--judge-account") + 1] == "1"
    assert command[command.index("--study-receipts") + 1] == str(receipts_path)
    assert command[command.index("--output-dir") + 1] == str(
        tmp_path
        / "results"
        / "studies"
        / "rryas-headline-v1"
        / "runs"
        / "task-a"
        / "baseline"
    )
    assert "--no-build" not in command


def test_paid_execution_refuses_a_closed_authorization_gate(tmp_path: Path) -> None:
    plan_path, *_ = _write_fixture(tmp_path, authorized=False)
    called = False

    def runner(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner must not be called")

    with pytest.raises(DispatchError, match="not authorized"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=lambda **_kwargs: object(),
        )

    assert called is False


def test_dry_run_emits_every_slot_without_dispatch(tmp_path: Path) -> None:
    plan_path, *_ = _write_fixture(tmp_path, authorized=False)
    preflight_calls = 0

    def preflight(**_kwargs):
        nonlocal preflight_calls
        preflight_calls += 1
        return object()

    summary = dispatch_headline_study(
        plan_path=plan_path,
        repo_root=tmp_path,
        execute=False,
        runner=lambda *_args, **_kwargs: pytest.fail("must not dispatch"),
        preflight=preflight,
    )

    assert preflight_calls == 1
    assert summary.planned_slots == 6
    assert summary.executed_slots == 0
    assert len(summary.commands) == 6


def test_resume_receipts_must_be_an_exact_valid_prefix(tmp_path: Path) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path, authorized=True
    )
    spec = StudySpec.load(spec_path)
    _append(
        receipts_path,
        _receipt(spec, task_id="task-a", arm="mcp_only", cost=0.5),
    )

    with pytest.raises(DispatchError, match="exact execution-order prefix"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=False,
            preflight=lambda **_kwargs: object(),
        )


def test_execution_is_sequential_and_stops_on_an_invalid_receipt(
    tmp_path: Path,
) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path, authorized=True
    )
    spec = StudySpec.load(spec_path)
    calls: list[tuple[str, ...]] = []

    def runner(command, **_kwargs):
        calls.append(tuple(command))
        index = len(calls) - 1
        slot = (("task-a", "baseline"), ("task-a", "mcp_only"))[index]
        _append(
            receipts_path,
            _receipt(
                spec,
                task_id=slot[0],
                arm=slot[1],
                cost=0.5,
                status="valid" if index == 0 else "infra_invalid",
            ),
        )
        return type("Completed", (), {"returncode": 0})()

    with pytest.raises(DispatchError, match="status 'infra_invalid'"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=lambda **_kwargs: object(),
        )

    assert len(calls) == 2


def test_clean_start_creates_receipt_parent_after_preflight(tmp_path: Path) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path, authorized=True
    )
    spec = StudySpec.load(spec_path)
    receipts_path.parent.rmdir()
    preflight_completed = False

    def preflight(**_kwargs):
        nonlocal preflight_completed
        assert receipts_path.parent.exists() is False
        preflight_completed = True

    def runner(_command, **_kwargs):
        assert preflight_completed is True
        assert receipts_path.parent.is_dir()
        _append(
            receipts_path,
            _receipt(spec, task_id="task-a", arm="baseline", cost=0.5),
        )
        return type("Completed", (), {"returncode": 1})()

    with pytest.raises(DispatchError, match="run_task exited 1"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=preflight,
        )


def test_budget_reserve_stops_before_starting_the_next_slot(tmp_path: Path) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path,
        authorized=True,
        ceiling=9.0,
        per_slot_envelope=1.5,
    )
    spec = StudySpec.load(spec_path)
    _append(receipts_path, _receipt(spec, task_id="task-a", arm="baseline", cost=8.0))

    with pytest.raises(DispatchError, match="spend reserve"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=lambda *_args, **_kwargs: pytest.fail("must not dispatch"),
            preflight=lambda **_kwargs: object(),
        )


def test_plan_hash_drift_fails_closed(tmp_path: Path) -> None:
    plan_path, _spec, manifest, *_ = _write_fixture(tmp_path)
    manifest.write_text(manifest.read_text() + "\n")

    with pytest.raises(DispatchError, match="final_manifest_hash"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


def test_dispatch_plan_must_live_inside_repo_root(tmp_path: Path) -> None:
    plan_path, *_ = _write_fixture(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside-plan.json"
    outside.write_text(plan_path.read_text())
    try:
        with pytest.raises(DispatchError, match="inside the repository"):
            load_dispatch_plan(outside, repo_root=tmp_path)
    finally:
        outside.unlink()


def test_dispatcher_loads_a_supported_v2_plan(tmp_path: Path) -> None:
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v2")

    plan = load_dispatch_plan(plan_path, repo_root=tmp_path)

    assert plan.spec.study_id == "rryas-headline-v2"
    assert all("rryas-headline-v2" in str(slot.output_dir) for slot in plan.slots)


def test_repository_dispatch_plan_is_current_and_spend_gated() -> None:
    plan_path = (
        PROJECT_ROOT
        / "configs"
        / "studies"
        / "rryas-headline-v1"
        / "dispatch_plan.json"
    )
    plan = load_dispatch_plan(plan_path, repo_root=PROJECT_ROOT)

    assert len(plan.slots) == 129
    assert plan.paid_dispatch_authorized is False
    assert plan.authorization_reference is None
    assert plan.forecast_outer_spend_usd == pytest.approx(120.572258)
    assert plan.empirical_envelope_usd == pytest.approx(270.22791)
    assert plan.authorization_ceiling_usd == pytest.approx(275.0)
    assert plan.sample_attempts == 9


def test_repository_v2_dispatch_plan_is_current_and_spend_gated() -> None:
    plan_path = (
        PROJECT_ROOT
        / "configs"
        / "studies"
        / "rryas-headline-v2"
        / "dispatch_plan.json"
    )
    plan = load_dispatch_plan(plan_path, repo_root=PROJECT_ROOT)

    assert len(plan.slots) == 120
    assert plan.paid_dispatch_authorized is False
    assert plan.authorization_reference is None
    assert plan.forecast_outer_spend_usd == pytest.approx(625.217931)
    assert plan.empirical_envelope_usd == pytest.approx(1090.23432)
    assert plan.authorization_ceiling_usd == pytest.approx(1100.0)
    assert plan.sample_attempts == 7


def test_repository_aborted_run_is_immutable_and_not_promotable() -> None:
    study_dir = PROJECT_ROOT / "results" / "studies" / "rryas-headline-v1"
    status = json.loads((study_dir / "study_status.json").read_text())
    receipts_path = study_dir / "receipts.jsonl"
    receipts = read_receipts(receipts_path)

    assert status["status"] == "ABORTED-OPERATIONAL-INVALID"
    assert status["disposition"]["headline_eligible"] is False
    assert status["disposition"]["promotion_eligible"] is False
    assert status["receipts_hash"] == file_hash(receipts_path)
    assert len(receipts) == status["attempted_slots"] == 7
    assert sum(receipt.status == "valid" for receipt in receipts) == 6
    assert receipts[-1].status == "infra_invalid"
    assert receipts[-1].failure_class == "infra_sgx_unused"
    assert sum(receipt.usage.cost_usd for receipt in receipts) == pytest.approx(
        status["outer_spend_usd"]
    )
