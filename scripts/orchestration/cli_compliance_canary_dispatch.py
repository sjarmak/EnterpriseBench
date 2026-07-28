#!/usr/bin/env python3
"""Preview or run the one-shot headline-v2 CLI compliance canary."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (REPO_ROOT / "lib", REPO_ROOT / "scripts" / "infra"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from code_finder_interface_pilot_preflight import (  # noqa: E402
    ProvenanceProvider,
    RevisionValidator,
    _default_provenance_provider,
    _git_revision_matches,
)
from eb_study import STATUS_VALID, StudySpec, TrialReceipt, file_hash, read_receipts  # noqa: E402
from headline_study_dispatch import _validate_cost_forecast  # noqa: E402
from study_run import harness_input_paths  # noqa: E402

CANARY_STUDY_ID = "rryas-headline-v2-cli-compliance-canary"
CANARY_PROMOTION_POLICY = "operational-cli-compliance-no-promotion"


class CanaryDispatchError(RuntimeError):
    """The one-shot canary cannot be started or accepted safely."""


@dataclass(frozen=True)
class CanaryDispatchPlan:
    plan_path: Path
    manifest_path: Path
    spec_path: Path
    receipts_path: Path
    task_toml: Path
    output_root: Path
    spec: StudySpec
    manifest: dict[str, Any]
    authorization_ceiling_usd: float
    paid_dispatch_authorized: bool
    authorization_reference: str | None


@dataclass(frozen=True)
class CanaryDispatchSummary:
    executed: bool
    command: tuple[str, ...]
    receipt_count: int
    outer_spend_usd: float
    sgx_tool_calls: int


PlanLoader = Callable[[Path], CanaryDispatchPlan]
Runner = Callable[..., Any]


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CanaryDispatchError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CanaryDispatchError(f"{label} must be a JSON object")
    return payload


def _repo_path(repo_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CanaryDispatchError(f"{label} must be a repository-relative path")
    relative = Path(value)
    if relative.is_absolute():
        raise CanaryDispatchError(f"{label} must be repository-relative")
    resolved = (repo_root / relative).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise CanaryDispatchError(f"{label} escapes the repository") from exc
    return resolved


def _validate_spec(spec: StudySpec, manifest: dict[str, Any]) -> None:
    arms = tuple((arm.name, arm.capability_fingerprint) for arm in spec.arms)
    expected_slot = ((str(manifest.get("task_id")), "cli", 1),)
    if (
        spec.study_id != CANARY_STUDY_ID
        or spec.task_manifest_hash is None
        or spec.task_ids != (manifest.get("task_id"),)
        or len(arms) != 1
        or arms[0][0] != "cli"
        or "retrieval-before-local:cache-isolated:v3" not in arms[0][1]
        or spec.slots() != expected_slot
        or spec.baseline_arm != "cli"
        or spec.max_attempts != 1
        or spec.model != "claude-sonnet-5"
        or spec.token_source != "sdk_model_usage"
        or spec.promotion_policy != CANARY_PROMOTION_POLICY
    ):
        raise CanaryDispatchError(
            "canary StudySpec is not the locked one-shot contract"
        )


def _validate_manifest(manifest: dict[str, Any]) -> None:
    execution = manifest.get("execution")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("study_id") != CANARY_STUDY_ID
        or manifest.get("canary_id") not in (None, CANARY_STUDY_ID)
        or manifest.get("status") != "FINAL-NO-SPEND"
        or manifest.get("mode") != "cli"
        or manifest.get("harness") != "claude"
        or manifest.get("model") != "claude-sonnet-5"
        or manifest.get("max_attempts") != 1
        or manifest.get("success_criterion") != "sgx_tool_calls > 0"
        or not isinstance(execution, dict)
    ):
        raise CanaryDispatchError("canary manifest is not the locked CLI contract")


def _validate_authorization(plan: dict[str, Any]) -> tuple[bool, str | None]:
    authorization = plan.get("authorization")
    if not isinstance(authorization, dict):
        raise CanaryDispatchError("canary authorization must be an object")
    authorized = authorization.get("paid_dispatch_authorized")
    reference = authorization.get("authorization_reference")
    if (
        not isinstance(authorized, bool)
        or (authorized and (not isinstance(reference, str) or not reference))
        or (not authorized and reference is not None)
    ):
        raise CanaryDispatchError(
            "canary authorization state/reference is inconsistent"
        )
    return authorized, reference


def load_canary_dispatch_plan(
    plan_path: Path,
    *,
    repo_root: Path,
    provenance_provider: ProvenanceProvider | None = None,
    revision_validator: RevisionValidator | None = None,
) -> CanaryDispatchPlan:
    """Re-derive all one-shot inputs without creating output or spending."""

    repo_root = repo_root.resolve()
    plan_path = plan_path.resolve()
    plan = _load_object(plan_path, "canary dispatch plan")
    if (
        plan.get("schema_version") != 1
        or plan.get("study_id") != CANARY_STUDY_ID
        or plan.get("status") != "LOCKED-NO-SPEND"
    ):
        raise CanaryDispatchError("canary dispatch identity/status is not locked")
    manifest_path = _repo_path(repo_root, plan.get("manifest"), "canary manifest")
    spec_path = _repo_path(repo_root, plan.get("study_spec"), "canary study spec")
    if plan.get("manifest_hash") != file_hash(manifest_path):
        raise CanaryDispatchError("canary manifest hash drifted")
    if plan.get("study_spec_file_hash") != file_hash(spec_path):
        raise CanaryDispatchError("canary StudySpec file hash drifted")

    manifest = _load_object(manifest_path, "canary manifest")
    _validate_manifest(manifest)
    spec = StudySpec.load(spec_path)
    _validate_spec(spec, manifest)
    if (
        spec.task_manifest_hash != file_hash(manifest_path)
        or plan.get("study_spec_hash") != spec.spec_hash
        or spec.harness != manifest.get("harness_hash")
        or spec.revision != manifest.get("revision")
    ):
        raise CanaryDispatchError("canary files do not bind one immutable capsule")

    task_toml = _repo_path(repo_root, manifest.get("task_toml"), "canary task")
    task_dir = task_toml.parent
    provider = provenance_provider or _default_provenance_provider(repo_root)
    if provider(task_toml).harness_hash != spec.harness:
        raise CanaryDispatchError("canary harness hash does not match current inputs")
    validator = revision_validator or (
        lambda revision, paths: _git_revision_matches(
            revision, paths, repo_root=repo_root
        )
    )
    if not validator(spec.revision, (*harness_input_paths(repo_root), task_dir)):
        raise CanaryDispatchError("canary revision does not match current inputs")

    output_root = _repo_path(repo_root, manifest.get("output_root"), "output root")
    receipts_path = _repo_path(repo_root, manifest.get("receipts"), "receipts")
    if receipts_path.parent != output_root or receipts_path.name != "receipts.jsonl":
        raise CanaryDispatchError("canary receipts must live in the output root")
    if output_root.exists() and any(output_root.iterdir()):
        raise CanaryDispatchError("canary output root is not clean")
    _sample_count, _forecast, _envelope, _per_slot, ceiling = _validate_cost_forecast(
        plan.get("cost_forecast"), slot_count=1, repo_root=repo_root
    )
    authorized, reference = _validate_authorization(plan)
    return CanaryDispatchPlan(
        plan_path=plan_path,
        manifest_path=manifest_path,
        spec_path=spec_path,
        receipts_path=receipts_path,
        task_toml=task_toml,
        output_root=output_root,
        spec=spec,
        manifest=manifest,
        authorization_ceiling_usd=ceiling,
        paid_dispatch_authorized=authorized,
        authorization_reference=reference,
    )


def compile_canary_command(
    plan: CanaryDispatchPlan, repo_root: Path
) -> tuple[str, ...]:
    execution = plan.manifest["execution"]
    output_dir = plan.output_root / "runs" / str(plan.manifest["task_id"]) / "cli"
    command = [
        sys.executable,
        str(repo_root / "scripts/orchestration/run_task.py"),
        str(plan.task_toml),
        "--source",
        "mirror",
        "--harness",
        "claude",
        "--model",
        plan.spec.model,
        "--mode",
        "cli",
        "--account",
        str(plan.manifest["agent_account"]),
        "--judge-model",
        "cc:haiku",
        "--judge-account",
        str(plan.manifest["judge_account"]),
        "--timeout",
        str(execution["timeout_seconds"]),
        "--build-timeout",
        str(execution["build_timeout_seconds"]),
        "--verifier-timeout",
        str(execution["verifier_timeout_seconds"]),
        "--memory",
        str(execution["memory_mb"]),
        "--output-dir",
        str(output_dir),
        "--rep",
        "1",
        "--study-spec",
        str(plan.spec_path),
        "--study-receipts",
        str(plan.receipts_path),
        "--attempt",
        "1",
    ]
    if execution.get("no_build") is True:
        command.append("--no-build")
    return tuple(command)


def _validate_receipt(
    plan: CanaryDispatchPlan, receipt: TrialReceipt
) -> tuple[float, int]:
    expected = plan.spec.trial_id(str(plan.manifest["task_id"]), "cli", 1, 1)
    isolation = receipt.tool_use.get("cache_isolation")
    sgx_calls = receipt.tool_use.get("sgx_tool_calls")
    if (
        receipt.trial != expected
        or receipt.status != STATUS_VALID
        or receipt.spec_hash != plan.spec.spec_hash
        or not isinstance(isolation, dict)
        or isolation.get("valid") is not True
        or isolation.get("cache_write_tokens") != 0
        or isolation.get("cross_run_cache_read_tokens") != 0
        or not isinstance(sgx_calls, int)
        or isinstance(sgx_calls, bool)
        or sgx_calls <= 0
        or receipt.usage is None
        or receipt.usage.cost_usd is None
        or receipt.usage.cost_usd > plan.authorization_ceiling_usd
    ):
        raise CanaryDispatchError("canary receipt failed compliance or spend gates")
    return receipt.usage.cost_usd, sgx_calls


def dispatch_cli_compliance_canary(
    plan_path: Path,
    *,
    repo_root: Path,
    execute: bool,
    runner: Runner = subprocess.run,
    plan_loader: PlanLoader | None = None,
) -> CanaryDispatchSummary:
    loader = plan_loader or (
        lambda path: load_canary_dispatch_plan(path, repo_root=repo_root)
    )
    plan = loader(plan_path)
    command = compile_canary_command(plan, repo_root)
    if not execute:
        return CanaryDispatchSummary(False, command, 0, 0.0, 0)
    if not plan.paid_dispatch_authorized:
        raise CanaryDispatchError("paid canary dispatch is not authorized")

    plan.receipts_path.parent.mkdir(parents=True, exist_ok=True)
    result = runner(command, cwd=repo_root, check=False)
    receipts = read_receipts(plan.receipts_path)
    if result.returncode != 0 or len(receipts) != 1:
        raise CanaryDispatchError(
            "canary subprocess failed or receipt count is not one"
        )
    spend, sgx_calls = _validate_receipt(plan, receipts[0])
    return CanaryDispatchSummary(True, command, 1, spend, sgx_calls)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = dispatch_cli_compliance_canary(
            args.plan, repo_root=REPO_ROOT, execute=args.execute
        )
    except (CanaryDispatchError, ValueError) as exc:
        print(f"canary dispatch blocked: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
