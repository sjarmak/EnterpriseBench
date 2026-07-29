from __future__ import annotations

import fcntl
import json
import subprocess
import sys
import traceback
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for import_path in (
    PROJECT_ROOT / "lib",
    PROJECT_ROOT / "scripts" / "infra",
    PROJECT_ROOT / "scripts" / "orchestration",
):
    sys.path.insert(0, str(import_path))

from eb_study import (  # noqa: E402
    ReceiptError,
    StudySpec,
    TrialReceipt,
    file_hash,
    read_receipts,
)
import headline_study_dispatch as dispatch_module  # noqa: E402
from headline_study_dispatch import (  # noqa: E402
    DispatchError,
    authorization_batch_hash,
    compile_run_command,
    dispatch_headline_study,
    load_dispatch_plan,
)


def _v4_capacity_payload(
    *,
    fetched_at: datetime | None = None,
    agent_five_hour: float = 25.0,
    judge_five_hour: float = 7.0,
    agent_seven_day: float = 48.0,
    judge_seven_day: float = 45.0,
) -> dict[str, object]:
    from headline_dispatch_policy import capacity_evidence_hash

    evidence = {
        "schema_version": 2,
        "source": "anthropic-rate-limit-response-headers",
        "eligibility_policy": (
            "fresh-account-specific-utilization-below-100-percent"
        ),
        "confound_policy": (
            "accept-and-report-observed-nonzero-provider-utilization"
        ),
        "fetched_at": (fetched_at or datetime.now(timezone.utc)).isoformat(),
        "max_age_seconds": 600,
        "accounts": {
            "agent": {
                "account": 3,
                "fetched_at": (
                    fetched_at or datetime.now(timezone.utc)
                ).isoformat(),
                "five_hour_utilization_pct": agent_five_hour,
                "five_hour_resets_at": "2026-07-29T06:00:00+00:00",
                "seven_day_utilization_pct": agent_seven_day,
                "seven_day_resets_at": "2026-08-01T16:00:00+00:00",
            },
            "judge": {
                "account": 1,
                "fetched_at": (
                    fetched_at or datetime.now(timezone.utc)
                ).isoformat(),
                "five_hour_utilization_pct": judge_five_hour,
                "five_hour_resets_at": "2026-07-29T06:00:00+00:00",
                "seven_day_utilization_pct": judge_seven_day,
                "seven_day_resets_at": "2026-07-30T02:00:00+00:00",
            },
        },
    }
    return {
        "confirmed": True,
        "capacity_reference": capacity_evidence_hash(evidence),
        "confirmed_completed_prefix": 0,
        "confirmed_max_slots": 9,
        "eligibility_policy": (
            "fresh-account-specific-utilization-below-100-percent"
        ),
        "confound_policy": (
            "accept-and-report-observed-nonzero-provider-utilization"
        ),
        "evidence": evidence,
    }


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
    capacity_confirmed: bool = False,
    authorized_completed_prefix: int | None = None,
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
    capacity_gated = study_id in {
        "rryas-headline-v4",
        "rryas-headline-v5",
        "rryas-headline-v6",
    }
    paid_batch = study_id == "rryas-headline-v3" or capacity_gated
    receipts_path.parent.mkdir(parents=True)
    sample_path = tmp_path / "sample_receipts.jsonl"
    sample_path.write_text(
        json.dumps(
            _receipt(
                StudySpec.load(spec_path),
                task_id="task-a",
                arm="baseline",
                cost=per_slot_envelope,
            ).to_json()
        )
        + "\n"
    )

    if study_id == "rryas-headline-v3" and ceiling == 20.0:
        ceiling = 890.0
    if capacity_gated and ceiling == 20.0:
        ceiling = 990.0
    plan_payload = {
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
                    "paid_dispatch_authorized": False,
                    "authorization_reference": None,
                },
            }
    if paid_batch:
        judge_budget = 0.1 if capacity_gated else 0.01
        hard_cap = 10.6 if capacity_gated else 9.25
        plan_payload.update(
            {
                "batch_policy": {
                    "max_slots_per_dispatch": (
                        9 if capacity_gated else 12
                    ),
                    "complete_task_triplets": True,
                    "score_independent_boundaries": True,
                    "agent_max_budget_usd_per_slot": 9.1,
                    "judge_max_budget_usd_per_call": judge_budget,
                    "max_judge_calls_per_slot": 5,
                    "max_judge_attempts_per_call": 3,
                    "outer_spend_hard_cap_per_slot_usd": hard_cap,
                },
                "provider_capacity": {
                    "confirmed": False,
                    "capacity_reference": None,
                    "confirmed_completed_prefix": None,
                    "confirmed_max_slots": None,
                    **(
                        {
                            "eligibility_policy": (
                                "fresh-account-specific-utilization-"
                                "below-100-percent"
                            ),
                            "confound_policy": (
                                "accept-and-report-observed-nonzero-"
                                "provider-utilization"
                            ),
                        }
                        if capacity_gated
                        else {}
                    ),
                },
            }
        )
        plan_payload["authorization"].update(
            {
                "authorized_completed_prefix": None,
                "authorized_end_prefix": None,
                "authorized_batch_hash": None,
                "authorized_outer_spend_ceiling_usd": None,
            }
        )
    plan_path = tmp_path / "dispatch_plan.json"
    plan_path.write_text(json.dumps(plan_payload, sort_keys=True))
    if paid_batch and (authorized or capacity_confirmed):
        prefix = authorized_completed_prefix if authorized_completed_prefix is not None else 0
        if capacity_confirmed:
            plan_payload["provider_capacity"] = {
                "confirmed": True,
                "capacity_reference": "test-capacity",
                "confirmed_completed_prefix": prefix,
                "confirmed_max_slots": (
                    9 if capacity_gated else 12
                ),
            }
            if capacity_gated:
                plan_payload["provider_capacity"] = _v4_capacity_payload()
                plan_payload["provider_capacity"][
                    "confirmed_completed_prefix"
                ] = prefix
            plan_path.write_text(json.dumps(plan_payload, sort_keys=True))
        if authorized:
            preview_plan = load_dispatch_plan(plan_path, repo_root=tmp_path)
            batch_size = 9 if capacity_gated else 12
            end_prefix = min(prefix + batch_size, len(preview_plan.slots))
            commands = tuple(
                compile_run_command(slot, plan=preview_plan, repo_root=tmp_path)
                for slot in preview_plan.slots[prefix:end_prefix]
            )
            plan_payload["authorization"] = {
                "paid_dispatch_authorized": True,
                "authorization_reference": "test-authorization",
                "authorized_completed_prefix": prefix,
                "authorized_end_prefix": end_prefix,
                "authorized_batch_hash": authorization_batch_hash(
                    preview_plan,
                    commands,
                    start_prefix=prefix,
                    end_prefix=end_prefix,
                ),
                "authorized_outer_spend_ceiling_usd": ceiling,
            }
        plan_path.write_text(json.dumps(plan_payload, sort_keys=True))
    elif authorized:
        plan_payload["authorization"] = {
            "paid_dispatch_authorized": True,
            "authorization_reference": "test-authorization",
        }
        plan_path.write_text(json.dumps(plan_payload, sort_keys=True))
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


def _pre_agent_infra_receipt(
    spec: StudySpec,
    *,
    task_id: str,
    arm: str,
) -> TrialReceipt:
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
            "status": "infra_invalid",
            "failure_class": "infra_mcp_preflight",
            "image_digest": "sha256:image",
            "arm_gate_proof": None,
            "task_hash": "sha256:task",
            "harness_hash": spec.harness,
            "verifier_hash": "sha256:verifier",
            "score": None,
            "score_contract": None,
            "usage": None,
            "tool_use": {},
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


def test_pre_agent_infra_receipt_reports_terminal_status_before_cost(
    tmp_path: Path,
) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path, authorized=True
    )
    spec = StudySpec.load(spec_path)
    calls = 0

    def runner(_command, **_kwargs):
        nonlocal calls
        calls += 1
        _append(
            receipts_path,
            _pre_agent_infra_receipt(
                spec,
                task_id="task-a",
                arm="baseline",
            ),
        )
        return type("Completed", (), {"returncode": 2})()

    with pytest.raises(
        DispatchError,
        match=r"status 'infra_invalid'.*reported trial cost \$0\.000000",
    ):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=lambda **_kwargs: object(),
        )

    assert calls == 1


def test_valid_receipt_without_outer_cost_still_fails_closed(
    tmp_path: Path,
) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path, authorized=True
    )
    spec = StudySpec.load(spec_path)
    receipt = _receipt(spec, task_id="task-a", arm="baseline", cost=0.5)
    assert receipt.usage is not None
    receipt_without_outer_cost = replace(
        receipt,
        usage=replace(receipt.usage, cost_usd=None),
    )

    def runner(_command, **_kwargs):
        _append(receipts_path, receipt_without_outer_cost)
        return type("Completed", (), {"returncode": 0})()

    with pytest.raises(DispatchError, match="has no outer cost"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=lambda **_kwargs: object(),
        )


def test_zero_cost_infra_receipt_rejects_agent_provenance(
    tmp_path: Path,
) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path, authorized=True
    )
    spec = StudySpec.load(spec_path)
    receipt = _pre_agent_infra_receipt(
        spec,
        task_id="task-a",
        arm="baseline",
    )
    contradictory = replace(
        receipt,
        arm_gate_proof="mode_gate:agent-started",
        artifacts={
            **receipt.artifacts,
            "agent_trace.jsonl": "sha256:trace",
        },
    )

    def runner(_command, **_kwargs):
        _append(receipts_path, contradictory)
        return type("Completed", (), {"returncode": 2})()

    with pytest.raises(DispatchError, match="has no outer cost"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=lambda **_kwargs: object(),
        )


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


def test_runner_failure_without_receipt_is_a_bounded_dispatch_error(
    tmp_path: Path,
) -> None:
    plan_path, *_rest, receipts_path = _write_fixture(
        tmp_path,
        authorized=True,
    )
    calls = 0

    def runner(_command, **_kwargs):
        nonlocal calls
        calls += 1
        return type("Completed", (), {"returncode": 1})()

    with pytest.raises(
        DispatchError,
        match=r"run_task exited 1 .* without a readable appended receipt",
    ):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=lambda **_kwargs: object(),
        )

    assert calls == 1
    assert receipts_path.exists() is False


def test_receipt_error_cause_is_not_exposed_in_dispatch_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path, *_ = _write_fixture(tmp_path, authorized=True)
    sentinel = "SECRET-RECEIPT-TOKEN"

    def fail_read(_path: Path) -> list[TrialReceipt]:
        raise ReceiptError(f"malformed receipt {sentinel}")

    monkeypatch.setattr(dispatch_module, "read_receipts", fail_read)

    try:
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=lambda *_args, **_kwargs: type(
                "Completed",
                (),
                {"returncode": 1},
            )(),
            preflight=lambda **_kwargs: object(),
        )
    except DispatchError as exc:
        assert sentinel not in str(exc)
        assert sentinel not in traceback.format_exc()
    else:
        pytest.fail("receipt failure must stop dispatch")


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


def test_dispatch_plan_must_share_the_frozen_capsule_directory(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(tmp_path)
    copied_dir = tmp_path / "copied"
    copied_dir.mkdir()
    copied_plan = copied_dir / "dispatch_plan.json"
    copied_plan.write_text(plan_path.read_text())

    with pytest.raises(DispatchError, match="capsule directory"):
        load_dispatch_plan(copied_plan, repo_root=tmp_path)


def test_dispatcher_loads_a_supported_v2_plan(tmp_path: Path) -> None:
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v2")

    plan = load_dispatch_plan(plan_path, repo_root=tmp_path)

    assert plan.spec.study_id == "rryas-headline-v2"
    assert all("rryas-headline-v2" in str(slot.output_dir) for slot in plan.slots)


def test_v3_preview_is_limited_to_one_complete_task_triplet(tmp_path: Path) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
    )

    summary = dispatch_headline_study(
        plan_path=plan_path,
        repo_root=tmp_path,
        execute=False,
        preflight=lambda **_kwargs: object(),
    )

    assert summary.planned_slots == 6
    assert summary.completed_slots == 0
    assert len(summary.commands) == 6


def test_v3_rejects_a_batch_limit_above_the_frozen_twelve_slots(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v3")
    payload = json.loads(plan_path.read_text())
    payload["batch_policy"]["max_slots_per_dispatch"] = 15
    plan_path.write_text(json.dumps(payload))

    with pytest.raises(DispatchError, match="exactly 12 slots"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("max_slots_per_dispatch", 12.0),
        ("max_judge_calls_per_slot", 5.0),
        ("max_judge_attempts_per_call", 3.0),
    ),
)
def test_v3_rejects_float_values_for_integer_batch_controls(
    tmp_path: Path,
    field: str,
    value: float,
) -> None:
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v3")
    payload = json.loads(plan_path.read_text())
    payload["batch_policy"][field] = value
    plan_path.write_text(json.dumps(payload))

    with pytest.raises(DispatchError, match="provider-side budget caps"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


def test_v3_rejects_a_float_capacity_slot_count(tmp_path: Path) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        capacity_confirmed=True,
    )
    payload = json.loads(plan_path.read_text())
    payload["provider_capacity"]["confirmed_max_slots"] = 12.0
    plan_path.write_text(json.dumps(payload))

    with pytest.raises(DispatchError, match="capacity state/reference"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


def test_v3_commands_apply_native_agent_and_judge_budget_caps(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v3")
    plan = load_dispatch_plan(plan_path, repo_root=tmp_path)

    command = compile_run_command(plan.slots[0], plan=plan, repo_root=tmp_path)

    agent_command = command[command.index("--agent") + 1]
    assert "--max-budget-usd 9.1" in agent_command
    assert command[command.index("--judge-max-budget-usd") + 1] == "0.01"


def test_v4_commands_apply_corrected_native_judge_budget_cap(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(tmp_path, study_id="rryas-headline-v4")
    plan = load_dispatch_plan(plan_path, repo_root=tmp_path)

    command = compile_run_command(plan.slots[0], plan=plan, repo_root=tmp_path)

    agent_command = command[command.index("--agent") + 1]
    assert "--max-budget-usd 9.1" in agent_command
    assert command[command.index("--judge-max-budget-usd") + 1] == "0.1"


def test_v3_execution_refuses_a_concurrent_dispatcher(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        authorized=True,
        capacity_confirmed=True,
        authorized_completed_prefix=0,
    )
    runner_called = False

    def forbidden_runner(*_args: object, **_kwargs: object) -> None:
        nonlocal runner_called
        runner_called = True

    with plan_path.open("rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(DispatchError, match="dispatch is already active"):
            dispatch_headline_study(
                plan_path=plan_path,
                repo_root=tmp_path,
                execute=True,
                runner=forbidden_runner,
                preflight=lambda **_kwargs: object(),
            )

    assert runner_called is False


def test_v3_authorization_binds_the_outer_spend_ceiling(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        authorized=True,
        capacity_confirmed=True,
        authorized_completed_prefix=0,
    )
    payload = json.loads(plan_path.read_text())
    payload["cost_forecast"]["authorization_outer_spend_ceiling_usd"] = 1e9
    plan_path.write_text(json.dumps(payload))

    with pytest.raises(DispatchError, match="whole-study spend ceiling"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


@pytest.mark.parametrize(
    "batch_ceiling",
    (True, -1.0, float("nan"), 55.4, 890.1),
)
def test_v3_rejects_invalid_batch_authorization_ceiling(
    tmp_path: Path,
    batch_ceiling: object,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        authorized=True,
        capacity_confirmed=True,
        authorized_completed_prefix=0,
    )
    payload = json.loads(plan_path.read_text())
    payload["authorization"][
        "authorized_outer_spend_ceiling_usd"
    ] = batch_ceiling
    plan_path.write_text(json.dumps(payload))

    with pytest.raises(DispatchError, match="authorization"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


def test_v5_rejects_ceiling_without_prior_spend_before_external_checks(
    tmp_path: Path,
) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v5",
        authorized=True,
        capacity_confirmed=True,
        authorized_completed_prefix=3,
    )
    spec = StudySpec.load(spec_path)
    original = load_dispatch_plan(plan_path, repo_root=tmp_path)
    for slot in original.slots[:3]:
        slot.output_dir.mkdir(parents=True)
        _append(
            receipts_path,
            _receipt(
                spec,
                task_id=slot.task_id,
                arm=slot.arm,
                cost=9.0,
            ),
        )

    payload = json.loads(plan_path.read_text())
    payload["authorization"][
        "authorized_outer_spend_ceiling_usd"
    ] = 31.8
    plan_path.write_text(json.dumps(payload))
    malformed = load_dispatch_plan(plan_path, repo_root=tmp_path)
    commands = tuple(
        compile_run_command(slot, plan=malformed, repo_root=tmp_path)
        for slot in malformed.slots[3:6]
    )
    payload["authorization"]["authorized_batch_hash"] = authorization_batch_hash(
        malformed,
        commands,
        start_prefix=3,
        end_prefix=6,
    )
    plan_path.write_text(json.dumps(payload))

    external_calls: list[str] = []
    with pytest.raises(DispatchError, match="cumulative spend"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=lambda *_args, **_kwargs: external_calls.append("runner"),
            preflight=lambda **_kwargs: external_calls.append("preflight"),
            capacity_probe=lambda **_kwargs: external_calls.append("capacity"),
        )

    assert external_calls == []


def test_v3_authorization_hash_binds_the_exact_pending_commands(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        authorized=True,
        capacity_confirmed=True,
        authorized_completed_prefix=0,
    )
    payload = json.loads(plan_path.read_text())
    payload["authorization"]["authorized_batch_hash"] = "sha256:" + "0" * 64
    plan_path.write_text(json.dumps(payload))

    with pytest.raises(DispatchError, match="exact pending command batch"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=lambda *_args, **_kwargs: pytest.fail("must not dispatch"),
            preflight=lambda **_kwargs: object(),
        )


def test_v3_paid_authorization_plan_must_be_committed_and_clean(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        authorized=True,
        capacity_confirmed=True,
        authorized_completed_prefix=0,
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "eval@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Eval Test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "test fixture"],
        cwd=tmp_path,
        check=True,
    )
    plan_path.write_text(plan_path.read_text() + "\n")

    with pytest.raises(DispatchError, match="committed and clean"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=lambda *_args, **_kwargs: pytest.fail("must not dispatch"),
            preflight=lambda **_kwargs: object(),
        )


def test_v3_rejects_an_agent_receipt_above_the_native_agent_cap(
    tmp_path: Path,
) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        authorized=True,
        capacity_confirmed=True,
        authorized_completed_prefix=0,
    )
    spec = StudySpec.load(spec_path)

    def runner(_command: tuple[str, ...], **_kwargs: object) -> object:
        _append(
            receipts_path,
            _receipt(spec, task_id="task-a", arm="baseline", cost=9.2),
        )
        return type("Completed", (), {"returncode": 0})()

    with pytest.raises(DispatchError, match="exceeded the native agent cap"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=lambda **_kwargs: object(),
        )


def test_v3_invalid_receipt_still_enforces_provider_budget_caps(
    tmp_path: Path,
) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        authorized=True,
        capacity_confirmed=True,
        authorized_completed_prefix=0,
    )
    spec = StudySpec.load(spec_path)

    def runner(_command: tuple[str, ...], **_kwargs: object) -> object:
        _append(
            receipts_path,
            _receipt(
                spec,
                task_id="task-a",
                arm="baseline",
                cost=9.2,
                status="infra_invalid",
            ),
        )
        return type("Completed", (), {"returncode": 1})()

    with pytest.raises(DispatchError, match="exceeded the native agent cap"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=lambda **_kwargs: object(),
        )


def test_v3_rejects_blank_capacity_and_authorization_references(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        authorized=True,
        capacity_confirmed=True,
        authorized_completed_prefix=0,
    )
    payload = json.loads(plan_path.read_text())
    payload["authorization"]["authorization_reference"] = "   "
    payload["provider_capacity"]["capacity_reference"] = "\t"
    plan_path.write_text(json.dumps(payload))

    with pytest.raises(DispatchError, match="authorization state/reference"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


def test_dispatch_plan_rejects_boolean_schema_and_sample_counts(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(tmp_path)
    payload = json.loads(plan_path.read_text())
    payload["schema_version"] = True
    plan_path.write_text(json.dumps(payload))
    with pytest.raises(DispatchError, match="identity/status"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)

    payload["schema_version"] = 1
    payload["cost_forecast"]["sample_attempts"] = True
    plan_path.write_text(json.dumps(payload))
    with pytest.raises(DispatchError, match="sample_attempts"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


def test_v3_paid_batch_requires_provider_capacity_confirmation(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        authorized=True,
        authorized_completed_prefix=0,
    )
    runner_called = False

    def forbidden_runner(*args: object, **kwargs: object) -> None:
        nonlocal runner_called
        runner_called = True

    with pytest.raises(DispatchError, match="provider capacity is not confirmed"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=forbidden_runner,
            preflight=lambda **_kwargs: object(),
        )
    assert runner_called is False


def test_v4_paid_dispatch_rejects_capacity_that_expired_before_runner(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v4",
        authorized=True,
        capacity_confirmed=True,
    )
    payload = json.loads(plan_path.read_text())
    stale = datetime.now(timezone.utc) - timedelta(seconds=601)
    payload["provider_capacity"] = _v4_capacity_payload(fetched_at=stale)
    plan_path.write_text(json.dumps(payload, sort_keys=True))
    plan = load_dispatch_plan(plan_path, repo_root=tmp_path)
    commands = tuple(
        compile_run_command(slot, plan=plan, repo_root=tmp_path)
        for slot in plan.slots
    )
    payload["authorization"]["authorized_batch_hash"] = authorization_batch_hash(
        plan,
        commands,
        start_prefix=0,
        end_prefix=6,
    )
    plan_path.write_text(json.dumps(payload, sort_keys=True))

    with pytest.raises(DispatchError, match="capacity evidence is stale"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=lambda *_args, **_kwargs: pytest.fail("must not dispatch"),
            preflight=lambda **_kwargs: object(),
        )


def test_v4_load_rejects_capacity_evidence_account_mismatch(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v4",
        capacity_confirmed=True,
    )
    payload = json.loads(plan_path.read_text())
    payload["provider_capacity"]["evidence"]["accounts"]["agent"]["account"] = 4
    from headline_dispatch_policy import capacity_evidence_hash

    payload["provider_capacity"]["capacity_reference"] = capacity_evidence_hash(
        payload["provider_capacity"]["evidence"]
    )
    plan_path.write_text(json.dumps(payload, sort_keys=True))

    with pytest.raises(DispatchError, match="agent account"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


def test_v4_load_rejects_capacity_reference_not_matching_evidence(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v4",
        capacity_confirmed=True,
    )
    payload = json.loads(plan_path.read_text())
    payload["provider_capacity"]["capacity_reference"] = "sha256:" + "0" * 64
    plan_path.write_text(json.dumps(payload, sort_keys=True))

    with pytest.raises(DispatchError, match="capacity evidence identity"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


def test_v4_load_rejects_boolean_five_hour_usage(tmp_path: Path) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v4",
        capacity_confirmed=True,
    )
    payload = json.loads(plan_path.read_text())
    evidence = payload["provider_capacity"]["evidence"]
    evidence["accounts"]["agent"]["five_hour_utilization_pct"] = False
    from headline_dispatch_policy import capacity_evidence_hash

    payload["provider_capacity"]["capacity_reference"] = capacity_evidence_hash(evidence)
    plan_path.write_text(json.dumps(payload, sort_keys=True))

    with pytest.raises(DispatchError, match="capacity evidence.*malformed"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


def test_v4_load_rejects_extra_capacity_evidence_fields(tmp_path: Path) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v4",
        capacity_confirmed=True,
    )
    payload = json.loads(plan_path.read_text())
    evidence = payload["provider_capacity"]["evidence"]
    evidence["raw_authorization_header"] = "must-not-be-retained"
    from headline_dispatch_policy import capacity_evidence_hash

    payload["provider_capacity"]["capacity_reference"] = capacity_evidence_hash(evidence)
    plan_path.write_text(json.dumps(payload, sort_keys=True))

    with pytest.raises(DispatchError, match="capacity evidence identity"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


@pytest.mark.parametrize("section", ("authorization", "provider_capacity"))
def test_v4_closed_plan_rejects_extra_control_fields(
    tmp_path: Path,
    section: str,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v4",
    )
    payload = json.loads(plan_path.read_text())
    payload[section]["raw_authorization_header"] = "must-not-be-retained"
    plan_path.write_text(json.dumps(payload, sort_keys=True))

    with pytest.raises(DispatchError, match="v4 .* fields"):
        load_dispatch_plan(plan_path, repo_root=tmp_path)


def test_v3_incidental_evidence_does_not_activate_v4_freshness(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        capacity_confirmed=True,
    )
    payload = json.loads(plan_path.read_text())
    payload["provider_capacity"]["evidence"] = {"legacy": True}
    plan_path.write_text(json.dumps(payload, sort_keys=True))

    plan = load_dispatch_plan(plan_path, repo_root=tmp_path)

    assert plan.v3_controls is not None
    assert plan.v3_controls.capacity_evidence is None


def test_v5_loads_same_nonzero_capacity_contract_and_nine_slot_batch(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v5",
        authorized=True,
        capacity_confirmed=True,
    )

    summary = dispatch_headline_study(
        plan_path=plan_path,
        repo_root=tmp_path,
        execute=False,
        preflight=lambda **_kwargs: object(),
    )
    plan = load_dispatch_plan(plan_path, repo_root=tmp_path)

    assert summary.executed_slots == 0
    assert len(summary.commands) == 6
    assert plan.v3_controls is not None
    assert plan.v3_controls.capacity_evidence is not None
    assert plan.v3_controls.capacity_evidence["accounts"]["agent"][
        "five_hour_utilization_pct"
    ] == 25.0


@pytest.mark.parametrize(
    "live",
    (
        _v4_capacity_payload(agent_five_hour=100.0)["evidence"],
        _v4_capacity_payload(judge_seven_day=100.0)["evidence"],
    ),
)
def test_v4_live_capacity_recheck_rejects_exhausted_account_before_runner(
    tmp_path: Path,
    live: object,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v4",
        authorized=True,
        capacity_confirmed=True,
    )
    runner_called = False

    def runner(*_args: object, **_kwargs: object) -> None:
        nonlocal runner_called
        runner_called = True

    with pytest.raises(DispatchError, match="remaining provider capacity"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=lambda **_kwargs: object(),
            capacity_probe=lambda **_kwargs: live,
        )

    assert runner_called is False
    captures = sorted(
        (
            tmp_path
            / "results"
            / "studies"
            / "rryas-headline-v4"
            / "capacity_rechecks"
        ).glob("*.json")
    )
    assert [path.name.rsplit(".", 2)[-2] for path in captures] == [
        "result",
        "started",
    ]
    result = json.loads(
        next(path for path in captures if path.name.endswith(".result.json")).read_text()
    )
    assert result["status"] == "rejected"
    assert "remaining provider capacity" in result["invalid_reason"]


def test_v4_live_recheck_runs_after_preflight_and_is_captured_before_runner(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v4",
        authorized=True,
        capacity_confirmed=True,
    )
    live = _v4_capacity_payload()["evidence"]
    events: list[str] = []

    def preflight(**_kwargs: object) -> object:
        events.append("preflight")
        return object()

    def probe(**_kwargs: object) -> dict[str, object]:
        events.append("probe")
        return live

    def runner(
        _command: tuple[str, ...],
        *,
        env: dict[str, str],
        **_kwargs: object,
    ) -> None:
        events.append("runner")
        marker = env["ENTERPRISEBENCH_PROVIDER_ACCOUNT_LOCK_FDS"]
        inherited_accounts = {
            int(item.split(":", 1)[0]) for item in marker.split(",")
        }
        assert inherited_accounts == {1, 3}
        assert len(_kwargs["pass_fds"]) == 2
        captures = list(
            (
                tmp_path
                / "results"
                / "studies"
                / "rryas-headline-v4"
                / "capacity_rechecks"
            ).glob("*.json")
        )
        assert len(captures) == 2
        result = json.loads(
            next(
                path
                for path in captures
                if path.name.endswith(".result.json")
            ).read_text()
        )
        assert result["status"] == "accepted"
        raise RuntimeError("stop after first runner boundary")

    with pytest.raises(RuntimeError, match="runner boundary"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=runner,
            preflight=preflight,
            capacity_probe=probe,
        )

    assert events == ["preflight", "probe", "runner"]


def test_v4_failed_live_probe_consumes_authorization_before_retry(
    tmp_path: Path,
) -> None:
    plan_path, *_ = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v4",
        authorized=True,
        capacity_confirmed=True,
    )
    calls = 0

    def failing_probe(**_kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise TimeoutError("transport SECRET-SENTINEL")

    with pytest.raises(DispatchError, match="TimeoutError") as failure:
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=lambda *_args, **_kwargs: pytest.fail("must not dispatch"),
            preflight=lambda **_kwargs: object(),
            capacity_probe=failing_probe,
        )
    rendered_traceback = "".join(
        traceback.format_exception(
            failure.type,
            failure.value,
            failure.tb,
        )
    )
    assert "SECRET-SENTINEL" not in rendered_traceback

    with pytest.raises(DispatchError, match="already exists"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=lambda *_args, **_kwargs: pytest.fail("must not dispatch"),
            preflight=lambda **_kwargs: object(),
            capacity_probe=failing_probe,
        )

    assert calls == 1
    result_path = next(
        (
            tmp_path
            / "results"
            / "studies"
            / "rryas-headline-v4"
            / "capacity_rechecks"
        ).glob("*.result.json")
    )
    result = json.loads(result_path.read_text())
    assert result["status"] == "error"
    assert "SECRET-SENTINEL" not in result_path.read_text()


def test_v3_authorization_is_bound_to_one_completed_prefix(
    tmp_path: Path,
) -> None:
    plan_path, spec_path, *_rest, receipts_path = _write_fixture(
        tmp_path,
        study_id="rryas-headline-v3",
        authorized=True,
        capacity_confirmed=True,
        authorized_completed_prefix=0,
    )
    spec = StudySpec.load(spec_path)
    slots = iter(
        (
            ("task-a", "baseline"),
            ("task-a", "mcp_only"),
            ("task-a", "cli"),
            ("task-b", "mcp_only"),
            ("task-b", "cli"),
            ("task-b", "baseline"),
        )
    )
    calls = 0

    def runner(_command: tuple[str, ...], **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        task_id, arm = next(slots)
        _append(receipts_path, _receipt(spec, task_id=task_id, arm=arm, cost=0.5))
        return type("Completed", (), {"returncode": 0})()

    summary = dispatch_headline_study(
        plan_path=plan_path,
        repo_root=tmp_path,
        execute=True,
        runner=runner,
        preflight=lambda **_kwargs: object(),
    )

    assert calls == 6
    assert summary.completed_slots == 6
    assert summary.executed_slots == 6

    with pytest.raises(DispatchError, match="completed-prefix authorization"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=tmp_path,
            execute=True,
            runner=lambda *_args, **_kwargs: pytest.fail("must not replay"),
            preflight=lambda **_kwargs: object(),
        )


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


def test_repository_v2_aborted_run_is_consumed_and_not_replayable() -> None:
    config_dir = PROJECT_ROOT / "configs" / "studies" / "rryas-headline-v2"
    study_dir = PROJECT_ROOT / "results" / "studies" / "rryas-headline-v2"
    plan_path = config_dir / "dispatch_plan.authorized-2026-07-28.json"
    plan = json.loads(plan_path.read_text())
    status = json.loads((study_dir / "study_status.json").read_text())
    receipts_path = study_dir / "receipts.jsonl"
    receipts = read_receipts(receipts_path)
    runner_called = False

    def forbidden_runner(*args: object, **kwargs: object) -> None:
        nonlocal runner_called
        runner_called = True
        raise AssertionError("consumed authorization reached the runner")

    with pytest.raises(DispatchError, match="identity/status is not locked"):
        dispatch_headline_study(
            plan_path=plan_path,
            repo_root=PROJECT_ROOT,
            execute=True,
            runner=forbidden_runner,
        )

    assert runner_called is False
    assert plan["status"] == "CONSUMED"
    assert plan["authorization"] == {
        "authorization_reference": None,
        "paid_dispatch_authorized": False,
    }
    assert status["status"] == "ABORTED-OPERATIONAL-INVALID"
    assert status["disposition"]["headline_eligible"] is False
    assert status["disposition"]["promotion_eligible"] is False
    assert status["receipts_hash"] == file_hash(receipts_path)
    assert plan["consumption"]["receipts_hash"] == status["receipts_hash"]
    assert len(receipts) == status["attempted_slots"] == 23
    assert sum(receipt.status == "valid" for receipt in receipts) == 22
    assert sum(receipt.status == "infra_invalid" for receipt in receipts) == 1
    assert receipts[-1].failure_class == "verifier_infra_error"
    assert sum(receipt.usage.cost_usd for receipt in receipts) == pytest.approx(
        status["outer_spend_usd"]
    )
    assert status["outer_spend_usd"] == pytest.approx(95.775424)
    isolation = [
        receipt.tool_use["cache_isolation"]
        for receipt in receipts
    ]
    assert all(proof["valid"] is True for proof in isolation)
    assert sum(proof["cross_run_cache_read_tokens"] for proof in isolation) == 0
    assert sum(proof["cache_write_tokens"] for proof in isolation) == 0
