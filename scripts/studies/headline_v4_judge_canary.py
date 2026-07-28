#!/usr/bin/env python3
"""Run one authorized, non-replayable v4 judge-only canary."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (
    REPO_ROOT / "lib",
    REPO_ROOT / "scripts" / "orchestration",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from eb_study import file_hash  # noqa: E402
from eb_verify.judge import CheckpointJudgeInput, LLMJudge  # noqa: E402
from headline_dispatch_policy import (  # noqa: E402
    nonblank,
    validate_committed_authorization,
)

STUDY_ID = "rryas-headline-v4-judge-canary"
BACKEND_PATH = Path("lib/eb_verify/judge/backends.py")
ENGINE_PATH = Path("lib/eb_verify/judge/engine.py")


class CanaryError(RuntimeError):
    """The judge-only canary is unsafe or could not be recorded."""


@dataclass(frozen=True)
class CanaryPlan:
    path: Path
    authorization_reference: str
    account: int
    model: str
    max_budget_usd: float
    input_chars: int
    output: Path


JudgeFactory = Callable[..., Any]


def _repo_path(repo_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CanaryError(f"{label} must be a repository-relative path")
    relative = Path(value)
    if relative.is_absolute():
        raise CanaryError(f"{label} must be repository-relative")
    resolved = (repo_root / relative).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise CanaryError(f"{label} escapes the repository") from exc
    return resolved


def load_canary_plan(plan_path: Path, *, repo_root: Path) -> CanaryPlan:
    """Validate the exact one-shot judge authorization and code hashes."""

    repo_root = repo_root.resolve()
    try:
        payload = json.loads(plan_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CanaryError(f"cannot read canary plan: {exc}") from exc
    if not isinstance(payload, dict):
        raise CanaryError("canary plan must be a JSON object")
    if (
        payload.get("schema_version") != 1
        or payload.get("study_id") != STUDY_ID
        or payload.get("status") != "AUTHORIZED"
        or payload.get("paid_dispatch_authorized") is not True
        or not nonblank(payload.get("authorization_reference"))
    ):
        raise CanaryError("judge-only canary is not authorized")
    if (
        payload.get("account") != 1
        or payload.get("model") != "cc:haiku"
        or payload.get("max_budget_usd") != 0.1
        or payload.get("input_chars") != 12000
    ):
        raise CanaryError("judge-only canary contract drifted")
    if payload.get("backend_hash") != file_hash(repo_root / BACKEND_PATH):
        raise CanaryError("judge backend hash drifted")
    if payload.get("engine_hash") != file_hash(repo_root / ENGINE_PATH):
        raise CanaryError("judge engine hash drifted")
    output = _repo_path(repo_root, payload.get("output"), "canary output")
    if output.exists():
        raise CanaryError(f"canary output already exists: {output}")
    try:
        validate_committed_authorization(
            plan_path.resolve(),
            repo_root=repo_root,
        )
    except (ValueError, OSError) as exc:
        raise CanaryError(str(exc)) from exc
    return CanaryPlan(
        path=plan_path.resolve(),
        authorization_reference=str(payload["authorization_reference"]),
        account=1,
        model="cc:haiku",
        max_budget_usd=0.1,
        input_chars=12000,
        output=output,
    )


def _synthetic_agent_output(chars: int) -> str:
    seed = (
        "Observed evidence: repository alpha calls repository beta through "
        "symbol ResolveDependency; the expected boundary and failure mode are "
        "explicitly cited. "
    )
    return (seed * ((chars // len(seed)) + 1))[:chars]


def _write_result(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise CanaryError(f"canary output already exists: {path}") from exc
    except OSError as exc:
        raise CanaryError(f"cannot write canary output: {exc}") from exc


def run_canary(
    plan: CanaryPlan,
    *,
    repo_root: Path,
    judge_factory: JudgeFactory = LLMJudge,
) -> dict[str, Any]:
    """Dispatch exactly one judge call and persist its operational result."""

    if plan.output.exists():
        raise CanaryError(f"canary output already exists: {plan.output}")
    agent_output = _synthetic_agent_output(plan.input_chars)
    judge = judge_factory(
        model=plan.model,
        account=plan.account,
        max_budget_usd=plan.max_budget_usd,
    )
    started = datetime.now(timezone.utc)
    start_clock = time.monotonic()
    result = judge.evaluate_checkpoint(
        CheckpointJudgeInput(
            task_id="already-exposed-v3-synthetic-boundary",
            checkpoint_name="judge_isolation_canary",
            agent_output=agent_output,
            expected_solution=(
                "The answer must identify ResolveDependency as the cross-repository "
                "boundary and describe its failure mode."
            ),
            evaluation_criteria=[
                "Identify ResolveDependency",
                "Describe a cross-repository boundary",
                "State a failure mode",
            ],
            checkpoint_weight=1.0,
        ),
        task_description=(
            "Operational canary for the isolated EnterpriseBench judge path."
        ),
        checkpoint_description=(
            "Return a structurally valid checkpoint score from a maximum-length input."
        ),
    )
    payload = {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "status": "COMPLETE-OPERATIONAL-VALID",
        "authorization_reference": plan.authorization_reference,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - start_clock, 6),
        "paid_inference_dispatched": True,
        "agent_inference_dispatched": False,
        "judge_calls": 1,
        "input_chars": len(agent_output),
        "input_sha256": (
            f"sha256:{hashlib.sha256(agent_output.encode()).hexdigest()}"
        ),
        "judge_provenance": dict(judge.provenance),
        "result": asdict(result),
    }
    _write_result(plan.output, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        plan = load_canary_plan(args.plan, repo_root=REPO_ROOT)
        result = run_canary(plan, repo_root=REPO_ROOT)
    except CanaryError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
