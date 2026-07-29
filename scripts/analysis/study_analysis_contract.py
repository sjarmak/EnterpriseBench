"""Strict byte-bound contract for confirmatory study analysis."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from eb_study import CapsuleError, StudySpec, content_hash, strict_json_loads

PRIMARY_CONFIDENCE_LEVEL = 0.95
REQUIRED_BOOTSTRAP_REPETITIONS = 10_000
TASK_TYPE_RE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")

PLAN_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "claim_scope",
        "score",
        "primary_estimands",
        "secondary_estimands",
        "descriptive_only",
        "inference",
        "reward_parity_gate_for_efficiency_claims",
        "missing_invalid_handling",
        "reporting",
        "protocol_amendment",
    }
)
MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "purpose",
        "candidate_lock_revision",
        "candidate_manifest",
        "candidate_manifest_hash",
        "analysis_plan",
        "analysis_plan_hash",
        "selection",
        "tasks",
        "arms",
        "evidence_policy",
        "execution_configuration",
        "cache_isolation",
        "judge_configuration",
        "harness_hash",
        "verifier_hashes",
        "spend_guard",
    }
)
TASK_FIELDS = frozenset(
    {
        "candidate_id",
        "task_id",
        "task_type",
        "difficulty_stratum",
        "task_toml",
        "task_hash",
        "graded_artifact_path",
        "expected_repositories",
    }
)
EXECUTION_FIELDS = frozenset(
    {
        "agent_account",
        "timeout_seconds",
        "build_timeout_seconds",
        "verifier_timeout_seconds",
        "memory_mb",
        "no_build",
        "repetitions",
        "max_attempts",
        "concurrency",
        "output_root",
        "receipts",
        "order_policy",
        "execution_order",
    }
)
ORDER_FIELDS = frozenset(
    {
        "candidate_id",
        "task_id",
        "arm",
        "repetition",
        "attempt",
        "agent_account",
        "judge_account",
        "output_dir",
    }
)
JUDGE_FIELDS = frozenset(
    {
        "model",
        "account",
        "executable",
        "selection",
        "provenance_required_in_scores",
        "isolation",
    }
)
SELECTION_FIELDS = frozenset(
    {
        "rule",
        "candidate_outcomes_inspected",
        "candidate_count",
        "selected_count",
        "post_lock_exposures",
    }
)
EXPOSURE_FIELDS = frozenset({"candidate_id", "reason", "evidence"})
CACHE_ISOLATION_FIELDS = frozenset(
    {
        "schema_version",
        "required",
        "mechanism",
        "scope",
        "comparison_rule",
        "legacy_evidence",
    }
)
EVIDENCE_POLICY_FIELDS = frozenset(
    {
        "confirmatory_population",
        "historical_pilots",
        "forced_code_finder",
        "codex_opencode",
        "invalid_slot",
        "image_identity",
    }
)
SPEND_GUARD_FIELDS = frozenset(
    {
        "slots",
        "max_attempts_per_slot",
        "paid_dispatch_requires_new_explicit_authorization",
        "paid_dispatch_authorized",
        "forecast_reported_outer_spend_usd",
        "forecast_basis",
    }
)
PROTOCOL_AMENDMENT_FIELDS = frozenset(
    {
        "predecessor",
        "reason",
        "selection_rule",
        "excluded_candidate_ids",
        "predecessor_terminal_evidence",
        "predecessor_terminal_evidence_sha256",
        "predecessor_receipts",
        "predecessor_receipts_sha256",
        "unexposed_failed_task_ids",
        "predecessor_analysis_use",
    }
)


@dataclass(frozen=True)
class AnalysisContract:
    """Validated immutable inputs to the confirmatory analysis."""

    plan_hash: str
    manifest_hash: str
    confidence_level: float
    bootstrap_repetitions: int
    bootstrap_seed: int
    parity_margin: float
    primary_contrasts: tuple[tuple[str, str], ...]
    descriptive_contrast: tuple[str, str]
    descriptive_reason: str
    task_types: Mapping[str, str]
    task_hashes: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    task_paths: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    verifier_hashes: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    candidate_manifest_hash: str | None = None
    candidate_lock_revision: str | None = None
    execution_order_hash: str | None = None
    execution_order_count: int = 0
    agent_account: int | None = None
    judge_account: int | None = None
    stratum_counts: Mapping[str, int] = field(
        default_factory=lambda: MappingProxyType({})
    )


def load_analysis_contract(
    spec: StudySpec,
    analysis_plan_path: Path,
    task_manifest_path: Path,
) -> AnalysisContract:
    """Read and validate one exact plan/manifest byte pair."""

    try:
        plan_source = analysis_plan_path.read_bytes()
        manifest_source = task_manifest_path.read_bytes()
    except OSError as exc:
        raise CapsuleError("analysis contract input is unreadable") from exc
    return parse_analysis_contract(spec, plan_source, manifest_source)


def parse_analysis_contract(
    spec: StudySpec,
    analysis_plan_source: bytes,
    task_manifest_source: bytes,
) -> AnalysisContract:
    """Validate the transitive spec -> manifest -> plan hash chain."""

    manifest_hash = _bytes_hash(task_manifest_source)
    if manifest_hash != spec.task_manifest_hash:
        raise CapsuleError("task manifest bytes do not match the StudySpec")
    manifest = _read_object(task_manifest_source, "task manifest")
    plan = _read_object(analysis_plan_source, "analysis plan")
    plan_hash = _bytes_hash(analysis_plan_source)
    _reject_unknown(manifest, MANIFEST_FIELDS, "task manifest")
    _reject_unknown(plan, PLAN_FIELDS, "analysis plan")
    _require_values(
        manifest,
        {
            "schema_version": 1,
            "status": "FINAL-NO-SPEND",
            "study_id": spec.study_id,
            "analysis_plan_hash": plan_hash,
        },
        "task manifest",
    )
    _require_values(
        plan,
        {
            "schema_version": 1,
            "status": "LOCKED-BEFORE-HEADLINE-INFERENCE",
            "study_id": spec.study_id,
        },
        "analysis plan",
    )

    _validate_nested_shapes(manifest, plan, spec)
    _validate_selection(manifest, spec)
    task_types, task_hashes, task_paths = _task_entries(manifest, spec)
    verifier_hashes = _verifier_hashes(manifest, spec)
    primary = _primary_contrasts(plan, spec)
    descriptive, descriptive_reason = _descriptive_contrast(plan, spec)
    seed = _validate_inference(plan)
    parity_margin = _validate_parity(plan)
    _validate_score(plan, spec)
    _validate_missing(plan, spec)
    _validate_reporting(plan)
    execution = _execution_provenance(manifest, spec)
    if "harness_hash" in manifest and manifest["harness_hash"] != spec.harness:
        raise CapsuleError("task manifest harness hash does not match the StudySpec")

    counts = {
        task_type: sum(value == task_type for value in task_types.values())
        for task_type in sorted(set(task_types.values()))
    }
    return AnalysisContract(
        plan_hash=plan_hash,
        manifest_hash=manifest_hash,
        confidence_level=PRIMARY_CONFIDENCE_LEVEL,
        bootstrap_repetitions=REQUIRED_BOOTSTRAP_REPETITIONS,
        bootstrap_seed=seed,
        parity_margin=parity_margin,
        primary_contrasts=primary,
        descriptive_contrast=descriptive,
        descriptive_reason=descriptive_reason,
        task_types=MappingProxyType(task_types),
        task_hashes=MappingProxyType(task_hashes),
        task_paths=MappingProxyType(task_paths),
        verifier_hashes=MappingProxyType(verifier_hashes),
        candidate_manifest_hash=_optional_hash(
            manifest, "candidate_manifest_hash", "task manifest"
        ),
        candidate_lock_revision=_optional_string(
            manifest, "candidate_lock_revision", "task manifest"
        ),
        execution_order_hash=execution["execution_order_hash"],
        execution_order_count=execution["execution_order_count"],
        agent_account=execution["agent_account"],
        judge_account=execution["judge_account"],
        stratum_counts=MappingProxyType(counts),
    )


def _validate_nested_shapes(
    manifest: Mapping[str, Any],
    plan: Mapping[str, Any],
    spec: StudySpec,
) -> None:
    for key, fields, label in (
        ("cache_isolation", CACHE_ISOLATION_FIELDS, "cache isolation"),
        ("evidence_policy", EVIDENCE_POLICY_FIELDS, "evidence policy"),
        ("spend_guard", SPEND_GUARD_FIELDS, "spend guard"),
    ):
        if key in manifest:
            _reject_unknown(_object(manifest, key, "task manifest"), fields, label)
    if "protocol_amendment" in plan:
        _reject_unknown(
            _object(plan, "protocol_amendment", "analysis plan"),
            PROTOCOL_AMENDMENT_FIELDS,
            "protocol amendment",
        )

    if "arms" in manifest:
        arms = _object(manifest, "arms", "task manifest")
        if set(arms) != set(spec.arm_names) or any(
            not isinstance(description, str) or not description.strip()
            for description in arms.values()
        ):
            raise CapsuleError("task manifest arm mapping does not match the StudySpec")

    if "verifier_hashes" in manifest:
        verifier_hashes = _object(manifest, "verifier_hashes", "task manifest")
        if set(verifier_hashes) != set(spec.task_ids) or any(
            not isinstance(value, str) or SHA256_RE.fullmatch(value) is None
            for value in verifier_hashes.values()
        ):
            raise CapsuleError(
                "task manifest verifier-hash mapping does not match the StudySpec"
            )


def _validate_selection(manifest: Mapping[str, Any], spec: StudySpec) -> None:
    if "selection" not in manifest:
        return
    selection = _object(manifest, "selection", "task manifest")
    _reject_unknown(selection, SELECTION_FIELDS, "task selection")
    rule = selection.get("rule")
    inspected = selection.get("candidate_outcomes_inspected")
    candidate_count = selection.get("candidate_count")
    selected_count = selection.get("selected_count")
    exposures = selection.get("post_lock_exposures")
    if (
        not isinstance(rule, str)
        or not rule.strip()
        or not isinstance(inspected, bool)
        or not _plain_int(candidate_count)
        or not _plain_int(selected_count)
        or candidate_count < selected_count
        or selected_count != len(spec.task_ids)
        or not isinstance(exposures, list)
    ):
        raise CapsuleError("task selection does not match the locked study")
    for exposure in exposures:
        if not isinstance(exposure, dict):
            raise CapsuleError("task selection exposure must be an object")
        _reject_unknown(exposure, EXPOSURE_FIELDS, "task selection exposure")
        if (
            not isinstance(exposure.get("candidate_id"), str)
            or not isinstance(exposure.get("reason"), str)
            or not isinstance(exposure.get("evidence"), list)
            or not exposure["evidence"]
            or any(
                not isinstance(item, str) or not item for item in exposure["evidence"]
            )
        ):
            raise CapsuleError("task selection exposure is invalid")


def _task_entries(
    manifest: Mapping[str, Any],
    spec: StudySpec,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        raise CapsuleError("task manifest tasks must be an array")
    parsed: list[tuple[str, str]] = []
    task_hashes: dict[str, str] = {}
    task_paths: dict[str, str] = {}
    for task in tasks:
        if not isinstance(task, dict):
            raise CapsuleError("task manifest entries must be objects")
        _reject_unknown(task, TASK_FIELDS, "task manifest entry")
        task_id = task.get("task_id")
        task_type = task.get("task_type")
        if (
            not isinstance(task_id, str)
            or not isinstance(task_type, str)
            or TASK_TYPE_RE.fullmatch(task_type) is None
        ):
            raise CapsuleError("task manifest entry has invalid identity or type")
        parsed.append((task_id, task_type))
        if "task_hash" in task:
            task_hash = task["task_hash"]
            if not isinstance(task_hash, str) or SHA256_RE.fullmatch(task_hash) is None:
                raise CapsuleError("task manifest entry has invalid task hash")
            task_hashes[task_id] = task_hash
        if "task_toml" in task:
            task_path = task["task_toml"]
            if (
                not isinstance(task_path, str)
                or not task_path
                or Path(task_path).is_absolute()
                or ".." in Path(task_path).parts
            ):
                raise CapsuleError("task manifest entry has invalid task path")
            task_paths[task_id] = task_path
    ids = tuple(task_id for task_id, _task_type in parsed)
    if ids != spec.task_ids or len(ids) != len(set(ids)):
        raise CapsuleError("task manifest task order does not match the StudySpec")
    if task_hashes and set(task_hashes) != set(spec.task_ids):
        raise CapsuleError("task manifest must hash every declared task")
    if task_paths and set(task_paths) != set(spec.task_ids):
        raise CapsuleError("task manifest must name every declared task path")
    return dict(parsed), task_hashes, task_paths


def _verifier_hashes(
    manifest: Mapping[str, Any],
    spec: StudySpec,
) -> dict[str, str]:
    if "verifier_hashes" not in manifest:
        return {}
    verifier_hashes = _object(manifest, "verifier_hashes", "task manifest")
    if set(verifier_hashes) != set(spec.task_ids) or any(
        not isinstance(value, str) or SHA256_RE.fullmatch(value) is None
        for value in verifier_hashes.values()
    ):
        raise CapsuleError(
            "task manifest verifier-hash mapping does not match the StudySpec"
        )
    return dict(verifier_hashes)


def _primary_contrasts(
    plan: Mapping[str, Any], spec: StudySpec
) -> tuple[tuple[str, str], ...]:
    estimands = plan.get("primary_estimands")
    if not isinstance(estimands, list):
        raise CapsuleError("analysis plan primary estimands must be an array")
    contrasts: list[tuple[str, str]] = []
    for estimand in estimands:
        if not isinstance(estimand, dict):
            raise CapsuleError("analysis plan primary estimand must be an object")
        _reject_unknown(
            estimand,
            {"name", "contrast", "aggregation"},
            "analysis plan primary estimand",
        )
        contrast = estimand.get("contrast")
        if (
            not isinstance(contrast, list)
            or len(contrast) != 2
            or any(not isinstance(arm, str) for arm in contrast)
        ):
            raise CapsuleError("analysis plan primary contrast is invalid")
        contrasts.append((contrast[0], contrast[1]))
    expected = tuple((arm, spec.baseline_arm) for arm in spec.contrast_arms)
    if tuple(contrasts) != expected:
        raise CapsuleError("analysis plan primary contrasts do not match the StudySpec")
    return tuple(contrasts)


def _descriptive_contrast(
    plan: Mapping[str, Any], spec: StudySpec
) -> tuple[tuple[str, str], str]:
    descriptive = _object(plan, "descriptive_only", "analysis plan")
    _reject_unknown(
        descriptive, {"contrast", "reason"}, "analysis plan descriptive contrast"
    )
    raw = descriptive.get("contrast")
    reason = descriptive.get("reason")
    if (
        not isinstance(raw, str)
        or raw.count("_minus_") != 1
        or not isinstance(reason, str)
        or not reason.strip()
    ):
        raise CapsuleError("analysis plan descriptive contrast is invalid")
    candidate, baseline = raw.split("_minus_")
    if (
        candidate not in spec.arm_names
        or baseline not in spec.arm_names
        or candidate == baseline
    ):
        raise CapsuleError("analysis plan descriptive contrast names invalid arms")
    return (candidate, baseline), reason


def _validate_inference(plan: Mapping[str, Any]) -> int:
    inference = _object(plan, "inference", "analysis plan")
    expected = {
        "confidence_level": PRIMARY_CONFIDENCE_LEVEL,
        "bootstrap_repetitions": REQUIRED_BOOTSTRAP_REPETITIONS,
        "bootstrap_unit": "paired task",
        "stratification": "task_type with locked observed stratum sizes",
        "interval": "percentile paired bootstrap",
        "multiplicity": (
            "Holm correction at familywise alpha 0.05 for the two primary contrasts"
        ),
    }
    _reject_unknown(inference, {*expected, "bootstrap_seed"}, "analysis inference")
    _require_values(inference, expected, "analysis inference")
    return _nonnegative_int(inference, "bootstrap_seed", "analysis inference")


def _validate_parity(plan: Mapping[str, Any]) -> float:
    parity = _object(plan, "reward_parity_gate_for_efficiency_claims", "analysis plan")
    _reject_unknown(
        parity,
        {"method", "absolute_task_score_margin", "claim_rule"},
        "reward parity gate",
    )
    _require_values(
        parity,
        {"method": ("two one-sided tests using a 90% paired-bootstrap interval")},
        "reward parity gate",
    )
    margin = _finite_number(parity, "absolute_task_score_margin", "reward parity gate")
    if not 0 < margin < 1:
        raise CapsuleError("reward parity margin must be between zero and one")
    return margin


def _validate_score(plan: Mapping[str, Any], spec: StudySpec) -> None:
    score = _object(plan, "score", "analysis plan")
    expected = {
        "field": "task_score",
        "contract": spec.score_contract,
        "range": [0.0, 1.0],
        "unit": "task",
    }
    _reject_unknown(score, set(expected), "analysis score")
    _require_values(score, expected, "analysis score")


def _validate_missing(plan: Mapping[str, Any], spec: StudySpec) -> None:
    policy = _object(plan, "missing_invalid_handling", "analysis plan")
    slot_key = f"headline_requires_all_{len(spec.slots())}_slots_valid"
    expected = {
        "max_attempts_per_slot": spec.max_attempts,
        "retry_after_observing_output_or_score": False,
        slot_key: True,
        "incomplete_pair": "no headline promotion or confirmatory inference",
    }
    _reject_unknown(policy, {*expected, "all_attempts"}, "missing/invalid policy")
    _require_values(policy, expected, "missing/invalid policy")


def _validate_reporting(plan: Mapping[str, Any]) -> None:
    reporting = _object(plan, "reporting", "analysis plan")
    fields = {
        "type_counts_and_per_type_results_required",
        "absolute_arm_means_required",
        "paired_differences_and_intervals_required",
        "all_attempt_spend_required",
        "account_order_and_revision_provenance_required",
        "no_generalization_to_structured_deliverables",
    }
    _reject_unknown(reporting, fields, "reporting policy")
    _require_values(reporting, dict.fromkeys(fields, True), "reporting policy")


def _execution_provenance(
    manifest: Mapping[str, Any], spec: StudySpec
) -> dict[str, Any]:
    execution = manifest.get("execution_configuration")
    judge = manifest.get("judge_configuration")
    if execution is None and judge is None:
        return {
            "execution_order_hash": None,
            "execution_order_count": 0,
            "agent_account": None,
            "judge_account": None,
        }
    if not isinstance(execution, dict) or not isinstance(judge, dict):
        raise CapsuleError("task manifest execution provenance is incomplete")
    _reject_unknown(execution, EXECUTION_FIELDS, "execution configuration")
    _reject_unknown(judge, JUDGE_FIELDS, "judge configuration")
    agent = _nonnegative_int(execution, "agent_account", "execution configuration")
    judge_account = _nonnegative_int(judge, "account", "judge configuration")
    order = execution.get("execution_order")
    if not isinstance(order, list):
        raise CapsuleError("execution order must be an array")
    slots: list[tuple[str, str, int]] = []
    for row in order:
        if not isinstance(row, dict):
            raise CapsuleError("execution order entry must be an object")
        _reject_unknown(row, ORDER_FIELDS, "execution order entry")
        task_id, arm, repetition, attempt = (
            row.get("task_id"),
            row.get("arm"),
            row.get("repetition"),
            row.get("attempt"),
        )
        if (
            not isinstance(task_id, str)
            or not isinstance(arm, str)
            or not _plain_int(repetition)
            or not _plain_int(attempt)
            or attempt != 1
            or row.get("agent_account") != agent
            or row.get("judge_account") != judge_account
        ):
            raise CapsuleError("execution order entry violates the locked policy")
        slots.append((task_id, arm, repetition))
    if len(slots) != len(set(slots)) or set(slots) != set(spec.slots()):
        raise CapsuleError("execution order does not cover the StudySpec exactly once")
    return {
        "execution_order_hash": content_hash(order),
        "execution_order_count": len(order),
        "agent_account": agent,
        "judge_account": judge_account,
    }


def _read_object(source: bytes, label: str) -> dict[str, Any]:
    try:
        payload = strict_json_loads(source.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CapsuleError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise CapsuleError(f"{label} must be a JSON object")
    return payload


def _object(payload: Mapping[str, Any], key: str, label: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise CapsuleError(f"{label} {key} must be an object")
    return value


def _reject_unknown(
    payload: Mapping[str, Any],
    allowed: set[str] | frozenset[str],
    label: str,
) -> None:
    if unknown := sorted(set(payload) - set(allowed)):
        raise CapsuleError(f"{label} has unknown field(s): {', '.join(unknown)}")


def _require_values(
    payload: Mapping[str, Any], expected: Mapping[str, Any], label: str
) -> None:
    for key, value in expected.items():
        if key not in payload or type(payload[key]) is not type(value):
            raise CapsuleError(f"{label} {key} does not match the locked contract")
        if payload[key] != value:
            raise CapsuleError(f"{label} {key} does not match the locked contract")


def _nonnegative_int(payload: Mapping[str, Any], key: str, label: str) -> int:
    value = payload.get(key)
    if not _plain_int(value) or value < 0:
        raise CapsuleError(f"{label} {key} must be a non-negative integer")
    return value


def _finite_number(payload: Mapping[str, Any], key: str, label: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise CapsuleError(f"{label} {key} must be finite")
    try:
        parsed = float(value)
    except OverflowError as exc:
        raise CapsuleError(f"{label} {key} must be finite") from exc
    if not math.isfinite(parsed):
        raise CapsuleError(f"{label} {key} must be finite")
    return parsed


def _optional_hash(payload: Mapping[str, Any], key: str, label: str) -> str | None:
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CapsuleError(f"{label} {key} must be a SHA-256 digest")
    return value


def _optional_string(payload: Mapping[str, Any], key: str, label: str) -> str | None:
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, str) or not value:
        raise CapsuleError(f"{label} {key} must be a non-empty string")
    return value


def _plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _bytes_hash(source: bytes) -> str:
    return f"sha256:{hashlib.sha256(source).hexdigest()}"
