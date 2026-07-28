#!/usr/bin/env python3
"""Sequential, fail-closed dispatcher for the frozen rryas headline study."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (
    REPO_ROOT / "lib",
    REPO_ROOT / "scripts" / "infra",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from eb_study import (  # noqa: E402
    STATUS_VALID,
    StudyCapsule,
    StudySpec,
    TrialReceipt,
    file_hash,
    read_receipts,
)
from headline_study_preflight import (  # noqa: E402
    STUDY_ID,
    validate_headline_study,
)


class DispatchError(RuntimeError):
    """The dispatcher cannot safely start or continue the frozen study."""


@dataclass(frozen=True)
class DispatchSlot:
    task_id: str
    arm: str
    repetition: int
    attempt: int
    agent_account: int
    judge_account: int
    task_toml: Path
    output_dir: Path


@dataclass(frozen=True)
class DispatchPlan:
    path: Path
    spec_path: Path
    manifest_path: Path
    preflight_evidence_path: Path
    receipts_path: Path
    spec: StudySpec
    slots: tuple[DispatchSlot, ...]
    execution: Mapping[str, Any]
    sample_attempts: int
    forecast_outer_spend_usd: float
    empirical_envelope_usd: float
    per_slot_envelope_usd: float
    authorization_ceiling_usd: float
    paid_dispatch_authorized: bool
    authorization_reference: str | None


@dataclass(frozen=True)
class DispatchSummary:
    planned_slots: int
    completed_slots: int
    executed_slots: int
    outer_spend_usd: float
    commands: tuple[tuple[str, ...], ...]


Runner = Callable[..., Any]
Preflight = Callable[..., Any]


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        raise DispatchError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DispatchError(f"{label} {path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DispatchError(f"{label} must be a JSON object")
    return payload


def _repo_path(repo_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise DispatchError(f"{label} must be a non-empty repository-relative path")
    relative = Path(value)
    if relative.is_absolute():
        raise DispatchError(f"{label} must be repository-relative")
    resolved = (repo_root / relative).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise DispatchError(f"{label} escapes the repository") from exc
    return resolved


def _required_number(payload: Mapping[str, Any], field: str) -> float:
    value = payload.get(field)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise DispatchError(f"cost_forecast.{field} must be a finite number >= 0")
    return float(value)


def _validate_file_hash(
    plan: Mapping[str, Any],
    *,
    field: str,
    path: Path,
) -> None:
    expected = plan.get(field)
    actual = file_hash(path)
    if expected != actual:
        raise DispatchError(f"{field} is {expected!r}, current file hashes to {actual}")


def _sample_costs(
    entries: Any,
    *,
    repo_root: Path,
) -> tuple[float, ...]:
    if not isinstance(entries, list) or not entries:
        raise DispatchError("cost_forecast.sample_receipts must be a non-empty list")
    costs: list[float] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise DispatchError("sample receipt entries must contain path and sha256")
        path = _repo_path(repo_root, entry["path"], "sample receipt")
        if entry["sha256"] != file_hash(path):
            raise DispatchError(f"sample receipt hash drifted: {path}")
        try:
            lines = path.read_text().splitlines()
        except OSError as exc:
            raise DispatchError(f"cannot read sample receipt {path}: {exc}") from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                receipt = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DispatchError(
                    f"sample receipt {path}:{line_number} is invalid JSON"
                ) from exc
            usage = receipt.get("usage")
            isolation = receipt.get("tool_use", {}).get("cache_isolation")
            cost = usage.get("cost_usd") if isinstance(usage, dict) else None
            if (
                not isinstance(cost, (int, float))
                or isinstance(cost, bool)
                or not math.isfinite(cost)
                or cost < 0
                or not isinstance(isolation, dict)
                or isolation.get("valid") is not True
                or isolation.get("cache_write_tokens") != 0
                or isolation.get("cross_run_cache_read_tokens") != 0
            ):
                raise DispatchError(
                    f"sample receipt {path}:{line_number} lacks cache-isolated cost"
                )
            costs.append(float(cost))
    return tuple(costs)


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-6)


def _validate_cost_forecast(
    payload: Any,
    *,
    slot_count: int,
    repo_root: Path,
) -> tuple[int, float, float, float, float]:
    if not isinstance(payload, dict):
        raise DispatchError("dispatch plan cost_forecast must be an object")
    costs = _sample_costs(payload.get("sample_receipts"), repo_root=repo_root)
    sample_attempts = payload.get("sample_attempts")
    if sample_attempts != len(costs):
        raise DispatchError("cost_forecast.sample_attempts does not match evidence")

    sample_spend = _required_number(payload, "sample_outer_spend_usd")
    mean = _required_number(payload, "mean_per_slot_usd")
    forecast = _required_number(payload, "forecast_outer_spend_usd")
    per_slot = _required_number(payload, "max_observed_per_slot_usd")
    envelope = _required_number(payload, "empirical_slot_count_envelope_usd")
    ceiling = _required_number(payload, "authorization_outer_spend_ceiling_usd")
    uncovered = payload.get("uncovered_costs")
    if (
        not isinstance(uncovered, list)
        or not uncovered
        or not all(isinstance(item, str) and item for item in uncovered)
    ):
        raise DispatchError("cost_forecast must explicitly name uncovered costs")

    actual_spend = sum(costs)
    expected_mean = actual_spend / len(costs)
    if not (
        _close(sample_spend, actual_spend)
        and _close(mean, expected_mean)
        and _close(forecast, expected_mean * slot_count)
        and _close(per_slot, max(costs))
        and _close(envelope, max(costs) * slot_count)
        and ceiling >= envelope
    ):
        raise DispatchError("cost_forecast does not recompute from frozen evidence")
    return sample_attempts, forecast, envelope, per_slot, ceiling


def _load_slots(
    manifest: Mapping[str, Any],
    *,
    spec: StudySpec,
    repo_root: Path,
) -> tuple[tuple[DispatchSlot, ...], Path, Mapping[str, Any]]:
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        raise DispatchError("final manifest tasks must be a list")
    task_paths: dict[str, Path] = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise DispatchError("final manifest task entries must be objects")
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or task_id in task_paths:
            raise DispatchError("final manifest task IDs must be unique strings")
        task_paths[task_id] = _repo_path(
            repo_root, task.get("task_toml"), f"task {task_id} task_toml"
        )

    execution = manifest.get("execution_configuration")
    if not isinstance(execution, dict):
        raise DispatchError("execution_configuration must be an object")
    rows = execution.get("execution_order")
    if not isinstance(rows, list):
        raise DispatchError("execution_order must be a list")
    slots: list[DispatchSlot] = []
    for row in rows:
        if not isinstance(row, dict):
            raise DispatchError("execution_order entries must be objects")
        task_id = row.get("task_id")
        if task_id not in task_paths:
            raise DispatchError(f"execution_order names unknown task {task_id!r}")
        slots.append(
            DispatchSlot(
                task_id=task_id,
                arm=str(row.get("arm")),
                repetition=int(row.get("repetition", 0)),
                attempt=int(row.get("attempt", 0)),
                agent_account=int(row.get("agent_account", 0)),
                judge_account=int(row.get("judge_account", 0)),
                task_toml=task_paths[task_id],
                output_dir=_repo_path(
                    repo_root, row.get("output_dir"), f"slot {task_id} output_dir"
                ),
            )
        )
    expected = {
        spec.trial_id(task_id, arm, repetition, attempt)
        for task_id, arm, repetition in spec.slots()
        for attempt in (1,)
    }
    actual = {
        spec.trial_id(slot.task_id, slot.arm, slot.repetition, slot.attempt)
        for slot in slots
    }
    if len(slots) != len(expected) or len(actual) != len(slots) or actual != expected:
        raise DispatchError("execution_order is not the exact StudySpec slot set")
    receipts_path = _repo_path(
        repo_root, execution.get("receipts"), "execution receipts"
    )
    return tuple(slots), receipts_path, execution


def load_dispatch_plan(plan_path: Path, *, repo_root: Path) -> DispatchPlan:
    """Load and re-derive every immutable dispatch and cost input."""

    repo_root = repo_root.resolve()
    plan_path = plan_path.resolve()
    try:
        plan_path.relative_to(repo_root)
    except ValueError as exc:
        raise DispatchError("dispatch plan must live inside the repository") from exc
    plan = _load_object(plan_path, "dispatch plan")
    if (
        plan.get("schema_version") != 1
        or plan.get("study_id") != STUDY_ID
        or plan.get("status") != "LOCKED-NO-SPEND"
    ):
        raise DispatchError("dispatch plan identity/status is not locked")

    spec_path = _repo_path(repo_root, plan.get("study_spec"), "study_spec")
    manifest_path = _repo_path(repo_root, plan.get("final_manifest"), "final_manifest")
    evidence_path = _repo_path(
        repo_root, plan.get("preflight_evidence"), "preflight_evidence"
    )
    _validate_file_hash(plan, field="study_spec_file_hash", path=spec_path)
    _validate_file_hash(plan, field="final_manifest_hash", path=manifest_path)
    _validate_file_hash(plan, field="preflight_evidence_hash", path=evidence_path)

    spec = StudySpec.load(spec_path)
    manifest = _load_object(manifest_path, "final manifest")
    if (
        spec.study_id != STUDY_ID
        or plan.get("study_spec_hash") != spec.spec_hash
        or spec.task_manifest_hash != file_hash(manifest_path)
        or manifest.get("study_id") != STUDY_ID
        or manifest.get("status") != "FINAL-NO-SPEND"
    ):
        raise DispatchError("dispatch plan does not bind the frozen headline capsule")

    slots, receipts_path, execution = _load_slots(
        manifest, spec=spec, repo_root=repo_root
    )
    sample_attempts, forecast, envelope, per_slot, ceiling = _validate_cost_forecast(
        plan.get("cost_forecast"),
        slot_count=len(slots),
        repo_root=repo_root,
    )
    authorization = plan.get("authorization")
    if not isinstance(authorization, dict):
        raise DispatchError("dispatch plan authorization must be an object")
    authorized = authorization.get("paid_dispatch_authorized")
    reference = authorization.get("authorization_reference")
    if (
        not isinstance(authorized, bool)
        or (authorized and (not isinstance(reference, str) or not reference))
        or (not authorized and reference is not None)
    ):
        raise DispatchError("dispatch authorization state/reference is inconsistent")

    return DispatchPlan(
        path=plan_path,
        spec_path=spec_path,
        manifest_path=manifest_path,
        preflight_evidence_path=evidence_path,
        receipts_path=receipts_path,
        spec=spec,
        slots=slots,
        execution=execution,
        sample_attempts=sample_attempts,
        forecast_outer_spend_usd=forecast,
        empirical_envelope_usd=envelope,
        per_slot_envelope_usd=per_slot,
        authorization_ceiling_usd=ceiling,
        paid_dispatch_authorized=authorized,
        authorization_reference=reference,
    )


def compile_run_command(
    slot: DispatchSlot,
    *,
    plan: DispatchPlan,
    repo_root: Path,
) -> tuple[str, ...]:
    """Compile one exact run_task invocation from the locked manifest."""

    execution = plan.execution
    expected_suffix = (
        f"rep{slot.repetition}",
        f"attempt{slot.attempt}",
    )
    if (slot.output_dir.parent.name, slot.output_dir.name) != expected_suffix:
        raise DispatchError(
            f"slot output_dir does not end in {expected_suffix}: {slot.output_dir}"
        )
    output_base = slot.output_dir.parent.parent
    command = [
        sys.executable,
        str(repo_root / "scripts" / "orchestration" / "run_task.py"),
        str(slot.task_toml),
        "--source",
        "mirror",
        "--harness",
        "claude",
        "--model",
        plan.spec.model,
        "--mode",
        slot.arm,
        "--account",
        str(slot.agent_account),
        "--judge-model",
        "cc:haiku",
        "--judge-account",
        str(slot.judge_account),
        "--timeout",
        str(execution["timeout_seconds"]),
        "--build-timeout",
        str(execution["build_timeout_seconds"]),
        "--verifier-timeout",
        str(execution["verifier_timeout_seconds"]),
        "--memory",
        str(execution["memory_mb"]),
        "--output-dir",
        str(output_base),
        "--rep",
        str(slot.repetition),
        "--study-spec",
        str(plan.spec_path),
        "--study-receipts",
        str(plan.receipts_path),
        "--attempt",
        str(slot.attempt),
    ]
    if execution.get("no_build") is True:
        command.append("--no-build")
    return tuple(command)


def _receipt_cost(receipt: TrialReceipt) -> float:
    if receipt.usage is None or receipt.usage.cost_usd is None:
        raise DispatchError(f"receipt {receipt.trial.key} has no outer cost")
    return receipt.usage.cost_usd


def _validate_cache_isolation(receipt: TrialReceipt) -> None:
    isolation = receipt.tool_use.get("cache_isolation")
    if (
        not isinstance(isolation, dict)
        or isolation.get("valid") is not True
        or isolation.get("cache_write_tokens") != 0
        or isolation.get("cross_run_cache_read_tokens") != 0
    ):
        raise DispatchError(
            f"receipt {receipt.trial.key} lacks zero-cache isolation proof"
        )


def _existing_receipts(plan: DispatchPlan) -> tuple[list[TrialReceipt], float]:
    if not plan.receipts_path.exists():
        return [], 0.0
    receipts = read_receipts(plan.receipts_path)
    if not receipts:
        return [], 0.0
    StudyCapsule.build(plan.spec, receipts)
    if len(receipts) > len(plan.slots):
        raise DispatchError("receipt log contains more trials than the execution plan")
    spend = 0.0
    for receipt, slot in zip(receipts, plan.slots):
        expected = plan.spec.trial_id(
            slot.task_id, slot.arm, slot.repetition, slot.attempt
        )
        if receipt.trial != expected:
            raise DispatchError("receipts are not an exact execution-order prefix")
        if receipt.status != STATUS_VALID:
            raise DispatchError(
                f"receipt {receipt.trial.key} has status {receipt.status!r}"
            )
        if not slot.output_dir.is_dir():
            raise DispatchError(f"completed slot output is missing: {slot.output_dir}")
        _validate_cache_isolation(receipt)
        spend += _receipt_cost(receipt)
    return receipts, spend


def _run_preflight(
    preflight: Preflight,
    *,
    plan: DispatchPlan,
    repo_root: Path,
    require_clean_output_root: bool,
) -> None:
    preflight(
        spec_path=plan.spec_path,
        manifest_path=plan.manifest_path,
        candidate_manifest_path=(
            repo_root / "results" / "rryas_dataset" / "candidate_manifest.json"
        ),
        analysis_plan_path=plan.manifest_path.parent / "analysis_plan.json",
        repo_root=repo_root,
        require_clean_output_root=require_clean_output_root,
    )


def dispatch_headline_study(
    *,
    plan_path: Path,
    repo_root: Path,
    execute: bool,
    runner: Runner = subprocess.run,
    preflight: Preflight = validate_headline_study,
) -> DispatchSummary:
    """Validate, preview, or sequentially execute the remaining frozen slots."""

    repo_root = repo_root.resolve()
    plan = load_dispatch_plan(plan_path, repo_root=repo_root)
    if execute and not plan.paid_dispatch_authorized:
        raise DispatchError("paid headline dispatch is not authorized")

    receipts, spend = _existing_receipts(plan)
    _run_preflight(
        preflight,
        plan=plan,
        repo_root=repo_root,
        require_clean_output_root=not receipts,
    )
    remaining = plan.slots[len(receipts) :]
    commands = tuple(
        compile_run_command(slot, plan=plan, repo_root=repo_root) for slot in remaining
    )
    if not execute:
        return DispatchSummary(
            planned_slots=len(plan.slots),
            completed_slots=len(receipts),
            executed_slots=0,
            outer_spend_usd=spend,
            commands=commands,
        )

    executed = 0
    for slot, command in zip(remaining, commands):
        if spend + plan.per_slot_envelope_usd > plan.authorization_ceiling_usd:
            raise DispatchError(
                "outer spend reserve is insufficient for the next empirical slot "
                f"envelope: spent ${spend:.6f}, reserve "
                f"${plan.per_slot_envelope_usd:.6f}, ceiling "
                f"${plan.authorization_ceiling_usd:.6f}"
            )
        before_count = len(receipts)
        completed = runner(
            command,
            cwd=repo_root,
            check=False,
        )
        updated = read_receipts(plan.receipts_path)
        if len(updated) != before_count + 1:
            raise DispatchError(
                "run_task must append exactly one receipt before dispatch can continue"
            )
        StudyCapsule.build(plan.spec, updated)
        receipt = updated[-1]
        expected = plan.spec.trial_id(
            slot.task_id, slot.arm, slot.repetition, slot.attempt
        )
        if receipt.trial != expected:
            raise DispatchError(
                f"run appended receipt {receipt.trial.key}, expected {expected.key}"
            )
        spend += _receipt_cost(receipt)
        if completed.returncode != 0:
            raise DispatchError(
                f"run_task exited {completed.returncode} for {receipt.trial.key}"
            )
        if receipt.status != STATUS_VALID:
            raise DispatchError(
                f"receipt {receipt.trial.key} has status {receipt.status!r}"
            )
        _validate_cache_isolation(receipt)
        if spend > plan.authorization_ceiling_usd:
            raise DispatchError(
                f"outer spend ${spend:.6f} exceeded the authorization ceiling"
            )
        receipts = updated
        executed += 1

    return DispatchSummary(
        planned_slots=len(plan.slots),
        completed_slots=len(receipts),
        executed_slots=executed,
        outer_spend_usd=spend,
        commands=commands,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan",
        type=Path,
        default=(REPO_ROOT / "configs" / "studies" / STUDY_ID / "dispatch_plan.json"),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Dispatch paid slots; default is a no-inference command preview.",
    )
    args = parser.parse_args(argv)
    try:
        summary = dispatch_headline_study(
            plan_path=args.plan,
            repo_root=REPO_ROOT,
            execute=args.execute,
        )
    except DispatchError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "planned_slots": summary.planned_slots,
                "completed_slots": summary.completed_slots,
                "executed_slots": summary.executed_slots,
                "outer_spend_usd": summary.outer_spend_usd,
                "commands": [list(command) for command in summary.commands],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
