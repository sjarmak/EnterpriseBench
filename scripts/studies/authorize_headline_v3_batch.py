#!/usr/bin/env python3
"""Create one non-replayable headline paid-batch artifact after approval."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (
    REPO_ROOT / "lib",
    REPO_ROOT / "scripts" / "infra",
    REPO_ROOT / "scripts" / "orchestration",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from headline_dispatch_policy import (  # noqa: E402
    DispatchPolicyError,
    V4_CAPACITY_CONFOUND_POLICY,
    V4_CAPACITY_ELIGIBILITY_POLICY,
    authorization_batch_hash,
    capacity_evidence_hash,
    nonblank,
    validate_capacity_evidence_freshness,
    validate_v4_capacity_evidence,
)
from headline_provider_capacity import (  # noqa: E402
    CapacityProbeError,
    UsageFetcher,
    build_live_capacity_evidence,
    exclusive_provider_account_locks,
    fetch_provider_usage,
)
from headline_protocol import CAPACITY_GATED_STUDY_IDS  # noqa: E402
from headline_study_dispatch import (  # noqa: E402
    DispatchError,
    _existing_receipts,
    compile_run_command,
    load_dispatch_plan,
)


class AuthorizationError(RuntimeError):
    """The requested one-shot authorization artifact is unsafe."""


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizationError(f"cannot read base dispatch plan: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuthorizationError("base dispatch plan must be a JSON object")
    return payload


def _build_v4_capacity(
    *,
    plan: Any,
    fetcher: UsageFetcher,
    now: datetime | None,
    completed_prefix: int,
) -> dict[str, Any]:
    agent_accounts = {slot.agent_account for slot in plan.slots}
    judge_accounts = {slot.judge_account for slot in plan.slots}
    if len(agent_accounts) != 1 or len(judge_accounts) != 1:
        raise AuthorizationError("v4 requires one agent and one judge account")
    try:
        evidence = build_live_capacity_evidence(
            agent_account=next(iter(agent_accounts)),
            judge_account=next(iter(judge_accounts)),
            fetcher=fetcher,
        )
        provider_capacity = {
            "confirmed": True,
            "capacity_reference": capacity_evidence_hash(evidence),
            "confirmed_completed_prefix": completed_prefix,
            "confirmed_max_slots": plan.v3_controls.max_slots_per_dispatch,
            "eligibility_policy": V4_CAPACITY_ELIGIBILITY_POLICY,
            "confound_policy": V4_CAPACITY_CONFOUND_POLICY,
            "evidence": evidence,
        }
        validated = validate_v4_capacity_evidence(
            provider_capacity,
            agent_accounts=agent_accounts,
            judge_accounts=judge_accounts,
        )
        validate_capacity_evidence_freshness(
            validated,
            now=now or datetime.now(timezone.utc),
        )
    except (CapacityProbeError, DispatchPolicyError) as exc:
        raise AuthorizationError(str(exc)) from exc
    return provider_capacity


def build_authorized_plan(
    *,
    plan_path: Path,
    repo_root: Path,
    authorization_reference: str,
    capacity_reference: str | None,
    capacity_fetcher: UsageFetcher | None = None,
    capacity_lock_factory=None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Bind approval and current capacity evidence to one exact pending batch."""

    if not nonblank(authorization_reference):
        raise AuthorizationError("authorization reference must be non-blank")
    try:
        plan = load_dispatch_plan(plan_path, repo_root=repo_root)
        receipts, _spend = _existing_receipts(plan)
    except DispatchError as exc:
        raise AuthorizationError(str(exc)) from exc
    controls = plan.v3_controls
    if controls is None or plan.paid_dispatch_authorized:
        raise AuthorizationError("base plan must be a closed v3 dispatch plan")

    start_prefix = len(receipts)
    end_prefix = min(
        start_prefix + controls.max_slots_per_dispatch,
        len(plan.slots),
    )
    if end_prefix == start_prefix:
        raise AuthorizationError("v3 study has no pending batch to authorize")
    commands = tuple(
        compile_run_command(slot, plan=plan, repo_root=repo_root)
        for slot in plan.slots[start_prefix:end_prefix]
    )
    payload = deepcopy(_load_payload(plan_path))
    if plan.spec.study_id in CAPACITY_GATED_STUDY_IDS:
        accounts = {
            account
            for slot in plan.slots
            for account in (slot.agent_account, slot.judge_account)
        }
        lock_factory = capacity_lock_factory or exclusive_provider_account_locks
        lock = lock_factory(accounts)
        try:
            with lock:
                payload["provider_capacity"] = _build_v4_capacity(
                    plan=plan,
                    fetcher=capacity_fetcher or fetch_provider_usage,
                    now=now,
                    completed_prefix=start_prefix,
                )
        except CapacityProbeError as exc:
            raise AuthorizationError(str(exc)) from exc
        bound_capacity_reference = payload["provider_capacity"][
            "capacity_reference"
        ]
    else:
        if not nonblank(capacity_reference):
            raise AuthorizationError(
                "authorization and capacity references must be non-blank"
            )
        bound_capacity_reference = capacity_reference
        payload["provider_capacity"] = {
            "confirmed": True,
            "capacity_reference": bound_capacity_reference,
            "confirmed_completed_prefix": start_prefix,
            "confirmed_max_slots": controls.max_slots_per_dispatch,
        }
    payload["authorization"] = {
        "paid_dispatch_authorized": True,
        "authorization_reference": authorization_reference,
        "authorized_completed_prefix": start_prefix,
        "authorized_end_prefix": end_prefix,
        "authorized_batch_hash": authorization_batch_hash(
            plan,
            commands,
            start_prefix=start_prefix,
            end_prefix=end_prefix,
            capacity_reference=bound_capacity_reference,
        ),
        "authorized_outer_spend_ceiling_usd": (
            plan.authorization_ceiling_usd
        ),
    }
    return payload


def write_authorized_plan(
    output_path: Path,
    payload: Mapping[str, Any],
) -> None:
    """Create an authorization artifact exclusively without overwriting."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise AuthorizationError(
            f"authorization artifact already exists: {output_path}"
        ) from exc
    except OSError as exc:
        raise AuthorizationError(
            f"cannot write authorization artifact {output_path}: {exc}"
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--capacity-reference")
    args = parser.parse_args(argv)
    if args.output.resolve().parent != args.plan.resolve().parent:
        parser.error("authorization output must share the capsule directory")
    try:
        payload = build_authorized_plan(
            plan_path=args.plan,
            repo_root=REPO_ROOT,
            authorization_reference=args.authorization_reference,
            capacity_reference=args.capacity_reference,
        )
        write_authorized_plan(args.output, payload)
    except AuthorizationError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "authorized_completed_prefix": payload["authorization"][
                    "authorized_completed_prefix"
                ],
                "authorized_end_prefix": payload["authorization"][
                    "authorized_end_prefix"
                ],
                "authorized_batch_hash": payload["authorization"][
                    "authorized_batch_hash"
                ],
                "authorization_outer_spend_ceiling_usd": payload[
                    "authorization"
                ]["authorized_outer_spend_ceiling_usd"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
