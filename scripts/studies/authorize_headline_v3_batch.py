#!/usr/bin/env python3
"""Create one non-replayable v3 paid-batch artifact after explicit approval."""

from __future__ import annotations

import argparse
from copy import deepcopy
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
    authorization_batch_hash,
    nonblank,
)
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


def build_authorized_plan(
    *,
    plan_path: Path,
    repo_root: Path,
    authorization_reference: str,
    capacity_reference: str,
) -> dict[str, Any]:
    """Bind approval and current capacity evidence to one exact pending batch."""

    if not nonblank(authorization_reference) or not nonblank(capacity_reference):
        raise AuthorizationError(
            "authorization and capacity references must be non-blank"
        )
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
    payload["provider_capacity"] = {
        "confirmed": True,
        "capacity_reference": capacity_reference,
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
    parser.add_argument("--capacity-reference", required=True)
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
