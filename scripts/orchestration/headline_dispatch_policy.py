"""Paid-dispatch safety policy for the v3 headline capsule."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tomllib
from typing import Any, Iterator, Mapping, Sequence

from eb_study import file_hash
from headline_protocol import HEADLINE_BATCH_POLICIES


class DispatchPolicyError(ValueError):
    """A paid-dispatch control is missing, inconsistent, or stale."""


@dataclass(frozen=True)
class V3DispatchControls:
    authorized_completed_prefix: int | None
    authorized_end_prefix: int | None
    authorized_batch_hash: str | None
    max_slots_per_dispatch: int
    agent_max_budget_usd_per_slot: float
    judge_max_budget_usd_per_call: float
    outer_spend_hard_cap_per_slot_usd: float
    provider_capacity_confirmed: bool
    capacity_confirmed_prefix: int | None


def strict_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_committed_authorization(
    plan_path: Path,
    *,
    repo_root: Path,
) -> None:
    """Reject paid plans that are not immutable in the current Git tree."""

    if not (repo_root / ".git").exists():
        return
    relative = plan_path.relative_to(repo_root)
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(relative)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            str(relative),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0 or status.returncode != 0 or status.stdout.strip():
        raise DispatchPolicyError(
            "paid v3 authorization plan must be committed and clean"
        )


def authorization_batch_hash(
    plan: Any,
    commands: Sequence[Sequence[str]],
    *,
    start_prefix: int,
    end_prefix: int,
) -> str:
    """Bind one approval to the exact immutable command batch and spend cap."""

    payload = {
        "study_id": plan.spec.study_id,
        "study_spec_hash": plan.spec.spec_hash,
        "manifest_hash": file_hash(plan.manifest_path),
        "preflight_evidence_hash": file_hash(plan.preflight_evidence_path),
        "start_prefix": start_prefix,
        "end_prefix": end_prefix,
        "authorization_outer_spend_ceiling_usd": (
            plan.authorization_ceiling_usd
        ),
        "outer_spend_hard_cap_per_slot_usd": (
            plan.v3_controls.outer_spend_hard_cap_per_slot_usd
            if plan.v3_controls is not None
            else None
        ),
        "commands": [list(command) for command in commands],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _max_declared_judge_calls(task_paths: Sequence[Path]) -> int:
    maximum = 0
    for task_path in set(task_paths):
        try:
            task = tomllib.loads(task_path.read_text())
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise DispatchPolicyError(
                f"cannot inspect judge calls in {task_path}: {exc}"
            ) from exc
        checkpoints = task.get("checkpoints", [])
        if not isinstance(checkpoints, list):
            raise DispatchPolicyError(
                f"task {task_path} checkpoints must be a list"
            )
        maximum = max(maximum, len(checkpoints))
    return maximum


def validate_v3_dispatch_controls(
    *,
    study_id: str,
    authorized: bool,
    authorization: Mapping[str, Any],
    batch_policy: Any,
    provider_capacity: Any,
    task_paths: Sequence[Path],
    slot_count: int,
    ceiling: float,
) -> V3DispatchControls:
    """Validate all frozen successor batch, capacity, and authorization controls."""

    frozen = HEADLINE_BATCH_POLICIES.get(study_id)
    if frozen is None:
        raise DispatchPolicyError(f"{study_id} has no frozen batch policy")
    frozen_batch_size = frozen["max_slots_per_dispatch"]

    prefix = authorization.get("authorized_completed_prefix")
    end_prefix = authorization.get("authorized_end_prefix")
    batch_hash = authorization.get("authorized_batch_hash")
    authorized_ceiling = authorization.get("authorized_outer_spend_ceiling_usd")
    if authorized and (
        not strict_non_negative_int(prefix)
        or not strict_non_negative_int(end_prefix)
        or end_prefix <= prefix
        or end_prefix != min(prefix + frozen_batch_size, slot_count)
        or not nonblank(batch_hash)
        or not isinstance(authorized_ceiling, (int, float))
        or isinstance(authorized_ceiling, bool)
        or not math.isfinite(authorized_ceiling)
        or not math.isclose(
            float(authorized_ceiling),
            ceiling,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
    ):
        raise DispatchPolicyError(
            "v3 authorization must bind the exact prefix, batch, and "
            "authorized spend ceiling"
        )
    if not authorized and any(
        value is not None
        for value in (prefix, end_prefix, batch_hash, authorized_ceiling)
    ):
        raise DispatchPolicyError(
            "closed v3 authorization cannot retain paid batch bindings"
        )

    if not isinstance(batch_policy, dict):
        raise DispatchPolicyError("v3 batch_policy must be an object")
    batch_size = batch_policy.get("max_slots_per_dispatch")
    agent_budget = batch_policy.get("agent_max_budget_usd_per_slot")
    judge_budget = batch_policy.get("judge_max_budget_usd_per_call")
    max_judge_calls = batch_policy.get("max_judge_calls_per_slot")
    max_judge_attempts = batch_policy.get("max_judge_attempts_per_call")
    hard_cap = batch_policy.get("outer_spend_hard_cap_per_slot_usd")
    if (
        not strict_non_negative_int(batch_size)
        or batch_size != frozen_batch_size
        or agent_budget != frozen["agent_max_budget_usd_per_slot"]
        or judge_budget != frozen["judge_max_budget_usd_per_call"]
        or not strict_non_negative_int(max_judge_calls)
        or max_judge_calls != frozen["max_judge_calls_per_slot"]
        or not strict_non_negative_int(max_judge_attempts)
        or max_judge_attempts != frozen["max_judge_attempts_per_call"]
        or hard_cap != frozen["outer_spend_hard_cap_per_slot_usd"]
        or batch_policy.get("complete_task_triplets") is not True
        or batch_policy.get("score_independent_boundaries") is not True
    ):
        raise DispatchPolicyError(
            f"{study_id} batch policy must use exactly {frozen_batch_size} "
            "slots and the frozen provider-side budget caps"
        )
    if _max_declared_judge_calls(task_paths) > max_judge_calls:
        raise DispatchPolicyError("v3 task exceeds the frozen judge-call budget")
    if ceiling < hard_cap * slot_count:
        raise DispatchPolicyError(
            "v3 authorization ceiling does not cover every hard-capped slot"
        )

    if not isinstance(provider_capacity, dict):
        raise DispatchPolicyError("v3 provider_capacity must be an object")
    capacity_confirmed = provider_capacity.get("confirmed")
    capacity_reference = provider_capacity.get("capacity_reference")
    capacity_prefix = provider_capacity.get("confirmed_completed_prefix")
    capacity_max_slots = provider_capacity.get("confirmed_max_slots")
    if (
        not isinstance(capacity_confirmed, bool)
        or (
            capacity_confirmed
            and (
                not nonblank(capacity_reference)
                or not strict_non_negative_int(capacity_prefix)
                or not strict_non_negative_int(capacity_max_slots)
                or capacity_max_slots != frozen_batch_size
            )
        )
        or (
            not capacity_confirmed
            and any(
                value is not None
                for value in (
                    capacity_reference,
                    capacity_prefix,
                    capacity_max_slots,
                )
            )
        )
    ):
        raise DispatchPolicyError(
            "v3 provider capacity state/reference is inconsistent"
        )

    return V3DispatchControls(
        authorized_completed_prefix=prefix,
        authorized_end_prefix=end_prefix,
        authorized_batch_hash=batch_hash,
        max_slots_per_dispatch=batch_size,
        agent_max_budget_usd_per_slot=float(agent_budget),
        judge_max_budget_usd_per_call=float(judge_budget),
        outer_spend_hard_cap_per_slot_usd=float(hard_cap),
        provider_capacity_confirmed=capacity_confirmed,
        capacity_confirmed_prefix=capacity_prefix,
    )


@contextmanager
def exclusive_dispatch_lock(
    plan_path: Path,
    *,
    repo_root: Path,
) -> Iterator[None]:
    """Hold one non-blocking lock shared by every plan in a study directory."""

    resolved_plan = plan_path.resolve()
    try:
        resolved_plan.relative_to(repo_root)
    except ValueError as exc:
        raise DispatchPolicyError(
            "dispatch plan must live inside the repository"
        ) from exc
    lock_target = resolved_plan.parent / "dispatch_plan.json"
    try:
        handle = lock_target.open("rb")
    except OSError as exc:
        raise DispatchPolicyError(
            f"cannot open canonical dispatch lock: {exc}"
        ) from exc
    acquired = False
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as exc:
            raise DispatchPolicyError(
                f"headline dispatch is already active for {lock_target.parent}"
            ) from exc
        yield
    finally:
        if acquired:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
