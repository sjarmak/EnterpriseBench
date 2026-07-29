"""Trusted provider-capacity probes and cross-study account locks."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
from typing import Any

from fetch_usage import fetch_usage_for_token, load_token
from headline_dispatch_policy import (
    DispatchPolicyError,
    V4_CAPACITY_CONFOUND_POLICY,
    V4_CAPACITY_ELIGIBILITY_POLICY,
    V4_CAPACITY_MAX_AGE_SECONDS,
    V4_CAPACITY_SCHEMA_VERSION,
    V4_CAPACITY_SOURCE,
    capacity_evidence_hash,
    nonblank,
    validate_capacity_evidence_freshness,
    validate_v4_capacity_evidence,
)


CLAUDE_HOMES = Path.home() / ".claude-homes"
DEFAULT_LOCK_DIR = Path.home() / ".cache" / "enterprisebench" / "provider-locks"


class CapacityProbeError(RuntimeError):
    """Live provider capacity cannot be trusted or exclusively consumed."""


UsageFetcher = Callable[[int], Mapping[str, Any]]
LiveCapacityProbe = Callable[..., Mapping[str, Any]]


def fetch_provider_usage(account_number: int) -> dict[str, Any]:
    """Fetch rate-limit headers using the fixed credential home for an account."""

    if (
        not isinstance(account_number, int)
        or isinstance(account_number, bool)
        or account_number <= 0
    ):
        raise CapacityProbeError("provider account number must be a positive integer")
    account_dir = CLAUDE_HOMES / f"account{account_number}"
    token = load_token(account_dir)
    if not token:
        raise CapacityProbeError(
            f"account{account_number} has no unexpired OAuth token"
        )
    try:
        usage = fetch_usage_for_token(token)
    except Exception as exc:
        raise CapacityProbeError(
            f"account{account_number} provider usage request failed: "
            f"{type(exc).__name__}"
        ) from None
    if not isinstance(usage, dict):
        raise CapacityProbeError(
            f"account{account_number} returned no provider usage headers"
        )
    return {
        **usage,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _redacted_observation(
    account_number: int,
    usage: Mapping[str, Any],
) -> dict[str, Any]:
    five_hour = usage.get("five_hour")
    seven_day = usage.get("seven_day")
    if not isinstance(five_hour, dict) or not isinstance(seven_day, dict):
        raise CapacityProbeError(
            f"account{account_number} usage windows are incomplete"
        )
    return {
        "account": account_number,
        "fetched_at": usage.get("fetched_at"),
        "five_hour_utilization_pct": five_hour.get("utilization"),
        "five_hour_resets_at": five_hour.get("resets_at"),
        "seven_day_utilization_pct": seven_day.get("utilization"),
        "seven_day_resets_at": seven_day.get("resets_at"),
    }


def build_live_capacity_evidence(
    *,
    agent_account: int,
    judge_account: int,
    fetcher: UsageFetcher = fetch_provider_usage,
) -> dict[str, Any]:
    """Fetch and redact the exact agent and judge capacity observations."""

    agent_usage = fetcher(agent_account)
    judge_usage = fetcher(judge_account)
    observations = {
        "agent": _redacted_observation(agent_account, agent_usage),
        "judge": _redacted_observation(judge_account, judge_usage),
    }
    fetched_at = max(
        observation["fetched_at"] for observation in observations.values()
    )
    return {
        "schema_version": V4_CAPACITY_SCHEMA_VERSION,
        "source": V4_CAPACITY_SOURCE,
        "eligibility_policy": V4_CAPACITY_ELIGIBILITY_POLICY,
        "confound_policy": V4_CAPACITY_CONFOUND_POLICY,
        "fetched_at": fetched_at,
        "max_age_seconds": V4_CAPACITY_MAX_AGE_SECONDS,
        "accounts": observations,
    }


def _capacity_recheck_path(plan: Any, suffix: str) -> Path:
    controls = plan.v3_controls
    if controls is None or not nonblank(controls.authorized_batch_hash):
        raise CapacityProbeError("capacity recheck has no authorized batch identity")
    output_dir = plan.receipts_path.parent / "capacity_rechecks"
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    return output_dir / f"{controls.authorized_batch_hash[7:]}.{suffix}.json"


def _write_recheck_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    try:
        with path.open("x") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o400)
    except FileExistsError as exc:
        raise CapacityProbeError(
            "capacity recheck artifact already exists; refusing batch replay"
        ) from exc


def _start_capacity_recheck(plan: Any) -> None:
    controls = plan.v3_controls
    if controls is None:
        raise CapacityProbeError("capacity recheck has no dispatch controls")
    _write_recheck_exclusive(
        _capacity_recheck_path(plan, "started"),
        {
            "schema_version": 1,
            "status": "started",
            "study_id": plan.spec.study_id,
            "authorization_reference": plan.authorization_reference,
            "authorized_batch_hash": controls.authorized_batch_hash,
        },
    )


def _finish_capacity_recheck(
    *,
    plan: Any,
    status: str,
    evidence: Mapping[str, Any] | None,
    invalid_reason: str | None,
) -> None:
    controls = plan.v3_controls
    if controls is None:
        raise CapacityProbeError("capacity recheck has no dispatch controls")
    _write_recheck_exclusive(
        _capacity_recheck_path(plan, "result"),
        {
            "schema_version": 1,
            "status": status,
            "study_id": plan.spec.study_id,
            "authorization_reference": plan.authorization_reference,
            "authorized_batch_hash": controls.authorized_batch_hash,
            "capacity_evidence_hash": (
                capacity_evidence_hash(evidence) if evidence is not None else None
            ),
            "evidence": evidence,
            "invalid_reason": invalid_reason,
        },
    )


def _redact_live_capacity_evidence(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    accounts = evidence.get("accounts")
    if not isinstance(accounts, dict):
        raise CapacityProbeError("live capacity evidence accounts are malformed")
    allowed = (
        "account",
        "fetched_at",
        "five_hour_utilization_pct",
        "five_hour_resets_at",
        "seven_day_utilization_pct",
        "seven_day_resets_at",
    )
    redacted_accounts = {}
    for role in ("agent", "judge"):
        observed = accounts.get(role)
        if not isinstance(observed, dict):
            raise CapacityProbeError(
                f"live capacity evidence {role} account is malformed"
            )
        redacted_accounts[role] = {
            field: observed.get(field) for field in allowed
        }
    return {
        "schema_version": evidence.get("schema_version"),
        "source": evidence.get("source"),
        "eligibility_policy": evidence.get("eligibility_policy"),
        "confound_policy": evidence.get("confound_policy"),
        "fetched_at": evidence.get("fetched_at"),
        "max_age_seconds": evidence.get("max_age_seconds"),
        "accounts": redacted_accounts,
    }


def prepare_v4_capacity_dispatch(
    *,
    plan: Any,
    completed_prefix: int,
    provider_lock_fds: Mapping[int, int] | None,
    capacity_probe: LiveCapacityProbe = build_live_capacity_evidence,
) -> tuple[dict[str, str], tuple[int, ...]]:
    """Consume one authorization, recheck live capacity, and bind child locks."""

    controls = plan.v3_controls
    if controls is None or controls.capacity_evidence is None:
        raise CapacityProbeError("v4 capacity controls are missing")
    validate_capacity_evidence_freshness(controls.capacity_evidence)
    agent_accounts = {slot.agent_account for slot in plan.slots}
    judge_accounts = {slot.judge_account for slot in plan.slots}
    locked_accounts = sorted(agent_accounts | judge_accounts)
    if provider_lock_fds is None or set(provider_lock_fds) != set(locked_accounts):
        raise CapacityProbeError("v4 provider account lock descriptors are missing")
    _start_capacity_recheck(plan)
    try:
        live_evidence = _redact_live_capacity_evidence(
            capacity_probe(
                agent_account=next(iter(agent_accounts)),
                judge_account=next(iter(judge_accounts)),
            )
        )
    except Exception as exc:
        normalized = (
            exc
            if isinstance(exc, CapacityProbeError)
            else CapacityProbeError(
                f"live provider capacity probe failed: {type(exc).__name__}"
            )
        )
        _finish_capacity_recheck(
            plan=plan,
            status="error",
            evidence=None,
            invalid_reason=str(normalized),
        )
        raise normalized from None
    live_capacity = {
        "confirmed": True,
        "capacity_reference": capacity_evidence_hash(live_evidence),
        "confirmed_completed_prefix": completed_prefix,
        "confirmed_max_slots": controls.max_slots_per_dispatch,
        "eligibility_policy": V4_CAPACITY_ELIGIBILITY_POLICY,
        "confound_policy": V4_CAPACITY_CONFOUND_POLICY,
        "evidence": live_evidence,
    }
    try:
        validated_live = validate_v4_capacity_evidence(
            live_capacity,
            agent_accounts=agent_accounts,
            judge_accounts=judge_accounts,
        )
        validate_capacity_evidence_freshness(validated_live)
    except DispatchPolicyError as exc:
        _finish_capacity_recheck(
            plan=plan,
            status="rejected",
            evidence=live_evidence,
            invalid_reason=str(exc),
        )
        raise
    _finish_capacity_recheck(
        plan=plan,
        status="accepted",
        evidence=validated_live,
        invalid_reason=None,
    )
    marker = ",".join(
        f"{account}:{provider_lock_fds[account]}" for account in locked_accounts
    )
    return (
        {
            **os.environ,
            "ENTERPRISEBENCH_PROVIDER_ACCOUNT_LOCK_FDS": marker,
        },
        tuple(provider_lock_fds[account] for account in locked_accounts),
    )


@contextmanager
def exclusive_provider_account_locks(
    account_numbers: set[int],
    *,
    lock_dir: Path = DEFAULT_LOCK_DIR,
) -> Iterator[dict[int, int]]:
    """Hold non-blocking locks for all provider accounts in sorted order."""

    if not account_numbers or any(
        not isinstance(account, int)
        or isinstance(account, bool)
        or account <= 0
        for account in account_numbers
    ):
        raise CapacityProbeError("provider lock accounts must be positive integers")
    lock_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(lock_dir, 0o700)
    handles: list[tuple[int, Any]] = []
    try:
        for account in sorted(account_numbers):
            lock_path = lock_dir / f"account{account}.lock"
            handle = lock_path.open("a+")
            os.chmod(lock_path, 0o600)
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                handle.close()
                raise CapacityProbeError(
                    f"account{account} is already locked by another provider consumer"
                ) from exc
            handles.append((account, handle))
        yield {account: handle.fileno() for account, handle in handles}
    finally:
        for _account, handle in reversed(handles):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
