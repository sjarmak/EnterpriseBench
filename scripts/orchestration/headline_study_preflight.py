#!/usr/bin/env python3
"""Fail-closed, no-inference validation for the rryas headline study."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import shutil
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (
    REPO_ROOT / "lib",
    REPO_ROOT / "scripts" / "infra",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from code_finder_interface_pilot_preflight import (  # noqa: E402
    MirrorProbe,
    ProvenanceProvider,
    RevisionValidator,
    _default_mirror_probe,
    _default_provenance_provider,
    _git_revision_matches,
    _load_object,
    _repo_file,
)
from eb_study import StudySpec, file_hash  # noqa: E402
from mirror_naming import derive_mirror_name  # noqa: E402
from mode_gate import IneligibleTask, check_eligibility  # noqa: E402
from run_task import (  # noqa: E402
    WORKSPACE_DIR,
    _derive_graded_artifact_path,
    _verifier_specs_by_name,
)
from study_run import harness_input_paths  # noqa: E402

STUDY_ID = "rryas-headline-v1"
CANDIDATE_LOCK_REVISION = "bb60d7e11cbdc77ae94e54dfcaceb7d975ed3e6e"
POST_LOCK_EXPOSURES = (
    "dep-graph-dual-junit-mockito-001",
    "dep-traversal-003",
    "error-prov-dual-otel-jaeger-001",
    "incident-investigation-dual-istio-001",
    "incident-investigation-dual-nerdctl-001",
)
POST_LOCK_EXPOSURE_EVIDENCE = {
    "dep-graph-dual-junit-mockito-001": (
        "configs/studies/rryas_code_finder_interface_pilot_v1/pilot_manifest.json",
    ),
    "dep-traversal-003": (
        "configs/studies/rryas_pilot_v1/pilot_manifest.json",
        "configs/studies/rryas_code_finder_canary_v1/canary_manifest.json",
        "configs/studies/rryas_code_finder_canary_v2/canary_manifest.json",
        "configs/studies/rryas_cli_code_finder_canary_v1/canary_manifest.json",
        "configs/studies/rryas_cli_code_finder_canary_v2/canary_manifest.json",
    ),
    "error-prov-dual-otel-jaeger-001": (
        "configs/studies/rryas_code_finder_interface_pilot_v1/pilot_manifest.json",
    ),
    "incident-investigation-dual-istio-001": (
        "configs/studies/rryas_code_finder_interface_pilot_v1/pilot_manifest.json",
    ),
    "incident-investigation-dual-nerdctl-001": (
        "configs/studies/rryas_code_finder_interface_supplement_v1/pilot_manifest.json",
        "configs/studies/rryas_code_finder_interface_supplement_v2/pilot_manifest.json",
    ),
}
V2_ADDITIONAL_EXPOSURES = (
    "api-contract-001",
    "api-contract-002",
    "api-contract-dual-envoy-istio-001",
)
V2_POST_LOCK_EXPOSURES = (
    *V2_ADDITIONAL_EXPOSURES,
    *POST_LOCK_EXPOSURES,
)
V2_POST_LOCK_EXPOSURE_EVIDENCE = {
    **POST_LOCK_EXPOSURE_EVIDENCE,
    **{
        candidate_id: ("results/studies/rryas-headline-v1/receipts.jsonl",)
        for candidate_id in V2_ADDITIONAL_EXPOSURES
    },
}


@dataclass(frozen=True)
class HeadlineProtocol:
    """Frozen population and slot counts for one confirmatory capsule."""

    study_id: str
    task_count: int
    slot_count: int
    post_lock_exposures: tuple[str, ...]
    post_lock_exposure_evidence: Mapping[str, tuple[str, ...]]
    arms: tuple[tuple[str, str], ...]
    arm_descriptions: Mapping[str, str]
    forecast_basis: str


REQUIRED_SELECTION_RULE = (
    "retain every structurally eligible candidate in candidate-manifest order "
    "except tasks with agent output after candidate lock; never inspect "
    "candidate reward or tool behavior to select confirmatory tasks"
)
REQUIRED_ARMS = (
    ("baseline", "local-repos:no-mcp:no-sgx:cache-isolated:v2"),
    ("mcp_only", "sourcegraph-mcp:local-repos-denied:cache-isolated:v2"),
    ("cli", "sgx-cli:local-repos-readable:usage-required:cache-isolated:v2"),
)
REQUIRED_ARM_DESCRIPTIONS = {
    "baseline": "local repositories; no Sourcegraph",
    "mcp_only": "Sourcegraph MCP; local repositories denied",
    "cli": "Sourcegraph CLI; local repositories readable; CLI use required",
}
V2_REQUIRED_ARMS = REQUIRED_ARMS[:2] + (
    (
        "cli",
        "sgx-cli:local-repos-readable:retrieval-before-local:cache-isolated:v3",
    ),
)
V2_REQUIRED_ARM_DESCRIPTIONS = {
    **REQUIRED_ARM_DESCRIPTIONS,
    "cli": (
        "Sourcegraph CLI required before local repository inspection; "
        "local repositories readable after first CLI call"
    ),
}
V1_PROTOCOL = HeadlineProtocol(
    study_id=STUDY_ID,
    task_count=43,
    slot_count=129,
    post_lock_exposures=POST_LOCK_EXPOSURES,
    post_lock_exposure_evidence=POST_LOCK_EXPOSURE_EVIDENCE,
    arms=REQUIRED_ARMS,
    arm_descriptions=REQUIRED_ARM_DESCRIPTIONS,
    forecast_basis=(
        "No extrapolation from confounded pilot costs; report actual "
        "provider usage before paid authorization."
    ),
)
V2_PROTOCOL = HeadlineProtocol(
    study_id="rryas-headline-v2",
    task_count=40,
    slot_count=120,
    post_lock_exposures=V2_POST_LOCK_EXPOSURES,
    post_lock_exposure_evidence=V2_POST_LOCK_EXPOSURE_EVIDENCE,
    arms=V2_REQUIRED_ARMS,
    arm_descriptions=V2_REQUIRED_ARM_DESCRIPTIONS,
    forecast_basis=(
        "No v2 spend authorization before a strengthened-CLI operational canary passes."
    ),
)
HEADLINE_PROTOCOLS = {
    protocol.study_id: protocol for protocol in (V1_PROTOCOL, V2_PROTOCOL)
}
REQUIRED_CACHE_ISOLATION = {
    "schema_version": 1,
    "required": True,
    "mechanism": "prompt-caching-disabled",
    "scope": "fresh random scope generated independently for every invocation",
    "comparison_rule": (
        "valid proof and cross_run_cache_read_tokens == 0 and cache_write_tokens == 0"
    ),
    "legacy_evidence": "comparison_ineligible",
}
REQUIRED_JUDGE = {
    "model": "cc:haiku",
    "account": 1,
    "executable": "claude-1",
    "selection": "explicit --judge-account 1",
    "provenance_required_in_scores": True,
}
REQUIRED_EXECUTION_BASE = {
    "agent_account": 3,
    "timeout_seconds": 600,
    "build_timeout_seconds": 1800,
    "verifier_timeout_seconds": 600,
    "memory_mb": 8192,
    "no_build": False,
    "repetitions": 1,
    "max_attempts": 1,
    "concurrency": 1,
}
REQUIRED_ORDER_POLICY = (
    "candidate-manifest order; rotate baseline,mcp_only,cli as a three-row "
    "Latin square by task index; execute sequentially on agent account 3; "
    "judge every completed slot on account 1"
)
REQUIRED_EVIDENCE_POLICY = {
    "confirmatory_population": "post-lock-unexposed-candidates-only",
    "historical_pilots": "operational evidence only; never headline evidence",
    "forced_code_finder": "separate descriptive study; never headline evidence",
    "codex_opencode": (
        "secondary harness-model bundles; never causal cross-model evidence"
    ),
    "invalid_slot": "stop promotion; retain receipt and all-attempt spend",
    "image_identity": (
        "record immutable built image and bound container digests per trial"
    ),
}
REQUIRED_ANALYSIS_PLAN = {
    "schema_version": 1,
    "status": "LOCKED-BEFORE-HEADLINE-INFERENCE",
    "study_id": STUDY_ID,
    "claim_scope": (
        "Claude Sonnet 5 on the 43-task EnterpriseBench markdown-report "
        "confirmatory population at the frozen revisions"
    ),
    "score": {
        "field": "task_score",
        "contract": "weighted-mean-v2",
        "range": [0.0, 1.0],
        "unit": "task",
    },
    "primary_estimands": [
        {
            "name": "mean_paired_reward_difference_mcp_only_minus_baseline",
            "contrast": ["mcp_only", "baseline"],
            "aggregation": "unweighted mean across all 43 paired tasks",
        },
        {
            "name": "mean_paired_reward_difference_cli_minus_baseline",
            "contrast": ["cli", "baseline"],
            "aggregation": "unweighted mean across all 43 paired tasks",
        },
    ],
    "secondary_estimands": [
        "per-arm mean task_score",
        "task-type-stratified paired reward differences",
        "reported_outer_cost_usd",
        "combined_tokens",
        "elapsed_seconds",
        "retrieval activity and validity gates",
    ],
    "descriptive_only": {
        "contrast": "cli_minus_mcp_only",
        "reason": ("the arms jointly change interface and local-source availability"),
    },
    "inference": {
        "confidence_level": 0.95,
        "bootstrap_repetitions": 10000,
        "bootstrap_seed": 20260728,
        "bootstrap_unit": "paired task",
        "stratification": "task_type with locked observed stratum sizes",
        "interval": "percentile paired bootstrap",
        "multiplicity": (
            "Holm correction at familywise alpha 0.05 for the two primary contrasts"
        ),
    },
    "reward_parity_gate_for_efficiency_claims": {
        "method": "two one-sided tests using a 90% paired-bootstrap interval",
        "absolute_task_score_margin": 0.05,
        "claim_rule": (
            "claim cheaper or faster at parity only when the complete 90% "
            "reward-difference interval is within [-0.05, 0.05]"
        ),
    },
    "missing_invalid_handling": {
        "max_attempts_per_slot": 1,
        "retry_after_observing_output_or_score": False,
        "headline_requires_all_129_slots_valid": True,
        "incomplete_pair": "no headline promotion or confirmatory inference",
        "all_attempts": "retain status, tokens, elapsed time, and cost",
    },
    "reporting": {
        "type_counts_and_per_type_results_required": True,
        "absolute_arm_means_required": True,
        "paired_differences_and_intervals_required": True,
        "all_attempt_spend_required": True,
        "account_order_and_revision_provenance_required": True,
        "no_generalization_to_structured_deliverables": True,
    },
}


def required_analysis_plan(protocol: HeadlineProtocol) -> dict[str, Any]:
    """Return the exact analysis plan required for a supported capsule."""

    plan = deepcopy(REQUIRED_ANALYSIS_PLAN)
    if protocol == V1_PROTOCOL:
        return plan
    plan["study_id"] = protocol.study_id
    plan["claim_scope"] = (
        "Claude Sonnet 5 on the 40-task EnterpriseBench markdown-report "
        "confirmatory population remaining after the disclosed v1 operational run"
    )
    for estimand in plan["primary_estimands"]:
        estimand["aggregation"] = (
            f"unweighted mean across all {protocol.task_count} paired tasks"
        )
    missing = plan["missing_invalid_handling"]
    missing.pop("headline_requires_all_129_slots_valid")
    missing[f"headline_requires_all_{protocol.slot_count}_slots_valid"] = True
    plan["protocol_amendment"] = {
        "predecessor": "rryas-headline-v1",
        "reason": "v1 stopped on a prespecified infra_sgx_unused CLI validity gate",
        "selection_rule": (
            "exclude every task with v1 agent output; retain all other locked "
            "candidates without inspecting reward"
        ),
        "excluded_candidate_ids": list(V2_ADDITIONAL_EXPOSURES),
        "v1_analysis_use": "operational pilot evidence only",
    }
    return plan


AuthProbe = Callable[[str], bool]


@dataclass(frozen=True)
class HeadlineEvidence:
    """The exact no-retry headline slots admitted by no-spend preflight."""

    study_id: str
    spec_hash: str
    task_manifest_hash: str
    analysis_plan_hash: str
    candidate_ids: tuple[str, ...]
    task_ids: tuple[str, ...]
    slots: tuple[tuple[str, str, int], ...]
    revision: str
    mirror_repositories: tuple[str, ...]
    output_root: str
    type_counts: tuple[tuple[str, int], ...]
    paid_dispatch_authorized: bool


def _validate_selection(
    manifest: dict[str, Any],
    candidate: dict[str, Any],
    *,
    protocol: HeadlineProtocol,
) -> tuple[str, ...]:
    candidate_ids = candidate.get("task_ids")
    if (
        candidate.get("count") != 48
        or not str(candidate.get("status", "")).startswith("CANDIDATE")
        or not isinstance(candidate_ids, list)
        or len(candidate_ids) != 48
        or not all(isinstance(task_id, str) and task_id for task_id in candidate_ids)
        or len(set(candidate_ids)) != 48
    ):
        raise ValueError("candidate manifest is not the locked 48-task population")
    if manifest.get("candidate_lock_revision") != CANDIDATE_LOCK_REVISION:
        raise ValueError("candidate lock revision does not match the curated lock")

    selection = manifest.get("selection")
    expected_exposures = [
        {
            "candidate_id": candidate_id,
            "reason": "post_lock_agent_output",
            "evidence": list(protocol.post_lock_exposure_evidence[candidate_id]),
        }
        for candidate_id in protocol.post_lock_exposures
    ]
    if (
        not isinstance(selection, dict)
        or selection.get("rule") != REQUIRED_SELECTION_RULE
        or selection.get("candidate_outcomes_inspected") is not False
        or selection.get("candidate_count") != 48
        or selection.get("selected_count") != protocol.task_count
    ):
        raise ValueError("headline selection is not the locked outcome-blind rule")
    if selection.get("post_lock_exposures") != expected_exposures:
        raise ValueError("headline exposure ledger is not exact")
    if not set(protocol.post_lock_exposures).issubset(candidate_ids):
        raise ValueError("headline exposure ledger names a non-candidate")
    return tuple(
        candidate_id
        for candidate_id in candidate_ids
        if candidate_id not in protocol.post_lock_exposures
    )


def _validate_task(
    entry: Any,
    *,
    candidate_id: str,
    repo_root: Path,
    mirror_probe: MirrorProbe,
) -> tuple[str, str, Path, Path, tuple[str, ...]]:
    if not isinstance(entry, dict) or entry.get("candidate_id") != candidate_id:
        raise ValueError("headline task order does not match selected candidates")
    task_toml = _repo_file(repo_root, entry.get("task_toml"), "task_toml")
    if task_toml.parent.name != candidate_id:
        raise ValueError(
            f"candidate {candidate_id!r} does not resolve to its exact path"
        )
    if entry.get("task_hash") != file_hash(task_toml):
        raise ValueError(f"task hash does not match {task_toml}")
    try:
        task_data = tomllib.loads(task_toml.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot parse task TOML {task_toml}: {exc}") from exc

    task = task_data.get("task", {})
    task_id = task.get("id")
    task_type = task.get("task_type")
    stratum = task_data.get("difficulty_stratum")
    if (
        not isinstance(task_id, str)
        or entry.get("task_id") != task_id
        or entry.get("task_type") != task_type
        or entry.get("difficulty_stratum") != stratum
    ):
        raise ValueError(
            f"candidate/task identity or type drifted for {candidate_id!r}"
        )

    task_dir = task_toml.parent
    artifact_path = _derive_graded_artifact_path(task_dir)
    if entry.get("graded_artifact_path") != artifact_path:
        raise ValueError(f"graded artifact path drifted for {candidate_id!r}")
    try:
        for arm, _fingerprint in REQUIRED_ARMS:
            check_eligibility(
                task_data,
                arm,
                graded_artifact_path=artifact_path,
                workspace=WORKSPACE_DIR,
            )
    except IneligibleTask as exc:
        raise ValueError(
            f"task {candidate_id!r} is ineligible for a declared arm"
        ) from exc

    expected_solution = _load_object(
        task_dir / "expected_solution.json", "expected solution"
    )
    expected_checkpoints = expected_solution.get("checkpoints")
    runtime_checkpoints = set(_verifier_specs_by_name(task_data.get("checkpoints", [])))
    if (
        expected_solution.get("task_id") != task_id
        or not isinstance(expected_checkpoints, dict)
        or runtime_checkpoints != set(expected_checkpoints)
    ):
        raise ValueError(f"checkpoint contract drifted for {candidate_id!r}")

    mirrors = _expected_headline_mirrors(task_data)
    if entry.get("expected_repositories") != list(mirrors):
        raise ValueError(f"mirror scope drifted for {candidate_id!r}")
    for repository in mirrors:
        if not mirror_probe(repository):
            raise ValueError(f"Sourcegraph mirror is unavailable: {repository}")
    return task_id, str(task_type), task_toml, task_dir, mirrors


def _expected_headline_mirrors(task_data: dict[str, Any]) -> tuple[str, ...]:
    repos = task_data.get("repos")
    if not isinstance(repos, list) or len(repos) < 2:
        raise ValueError("each headline task must declare at least two repos")
    mirrors: list[str] = []
    for repo in repos:
        if not isinstance(repo, dict):
            raise ValueError("headline task repo entry must be an object")
        url = repo.get("url")
        revision = repo.get("rev")
        if not isinstance(url, str) or not isinstance(revision, str):
            raise ValueError("headline task repo URL and revision must be strings")
        mirrors.append(f"github.com/{derive_mirror_name(url, revision)}")
    if len(set(mirrors)) != len(mirrors):
        raise ValueError("headline task mirror scopes must be unique")
    return tuple(mirrors)


def compile_execution_order(
    tasks: Sequence[dict[str, Any]],
    *,
    study_id: str = STUDY_ID,
) -> tuple[dict[str, Any], ...]:
    """Compile the locked Latin-square arm order for each task."""

    rotations = (
        ("baseline", "mcp_only", "cli"),
        ("mcp_only", "cli", "baseline"),
        ("cli", "baseline", "mcp_only"),
    )
    rows: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        for arm in rotations[index % len(rotations)]:
            task_id = task["task_id"]
            rows.append(
                {
                    "candidate_id": task["candidate_id"],
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
            )
    return tuple(rows)


def _validate_execution(
    manifest: dict[str, Any],
    tasks: Sequence[dict[str, Any]],
    *,
    repo_root: Path,
    require_clean_output_root: bool,
    protocol: HeadlineProtocol,
) -> str:
    execution = manifest.get("execution_configuration")
    if not isinstance(execution, dict) or any(
        execution.get(key) != value for key, value in REQUIRED_EXECUTION_BASE.items()
    ):
        raise ValueError("headline execution contract is not locked")
    expected_keys = {
        *REQUIRED_EXECUTION_BASE,
        "output_root",
        "receipts",
        "order_policy",
        "execution_order",
    }
    if (
        set(execution) != expected_keys
        or execution.get("order_policy") != REQUIRED_ORDER_POLICY
        or execution.get("execution_order")
        != [
            dict(row)
            for row in compile_execution_order(tasks, study_id=protocol.study_id)
        ]
    ):
        raise ValueError("headline execution order/account blocking is not locked")

    output_root_value = execution.get("output_root")
    output_root = _repo_relative_path(
        repo_root, output_root_value, "headline output_root"
    )
    if output_root.exists() and (
        not output_root.is_dir()
        or (require_clean_output_root and any(output_root.iterdir()))
    ):
        raise ValueError(f"headline output root is not clean: {output_root}")
    receipts = _repo_relative_path(
        repo_root, execution.get("receipts"), "headline receipts"
    )
    if receipts.parent != output_root or receipts.name != "receipts.jsonl":
        raise ValueError("headline receipts must live in the exact output root")
    output_dirs = [
        _repo_relative_path(repo_root, row["output_dir"], "slot output_dir")
        for row in execution["execution_order"]
    ]
    if (
        len(output_dirs) != protocol.slot_count
        or len(set(output_dirs)) != protocol.slot_count
        or any(output_root not in output.parents for output in output_dirs)
    ):
        raise ValueError("headline slot output directories are not unique and scoped")
    return str(output_root.relative_to(repo_root))


def _repo_relative_path(repo_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a repository-relative path")
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"{label} must be repository-relative")
    resolved = (repo_root / relative).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc
    return resolved


def _repo_file_or_clean_dir(repo_root: Path, value: Any, label: str) -> Path:
    path = _repo_relative_path(repo_root, value, label)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"headline output root is not clean: {path}")
    return path


def _validate_spend_guard(
    manifest: dict[str, Any], *, protocol: HeadlineProtocol
) -> None:
    expected = {
        "slots": protocol.slot_count,
        "max_attempts_per_slot": 1,
        "paid_dispatch_requires_new_explicit_authorization": True,
        "paid_dispatch_authorized": False,
        "forecast_reported_outer_spend_usd": None,
        "forecast_basis": protocol.forecast_basis,
    }
    if manifest.get("spend_guard") != expected:
        raise ValueError("headline spend guard is not locked")


def _default_auth_probe(credential: str) -> bool:
    executable = {
        "agent-account-3": "claude-3",
        "judge-account-1": "claude-1",
    }.get(credential)
    if executable is None or shutil.which(executable) is None:
        return False
    result = subprocess.run(
        [executable, "auth", "status", "--json"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and payload.get("loggedIn") is True


def _validate_auth(auth_probe: AuthProbe) -> None:
    for credential, label in (
        ("agent-account-3", "Claude agent account 3"),
        ("judge-account-1", "Claude judge account 1"),
    ):
        if not auth_probe(credential):
            raise ValueError(f"{label} authentication is unavailable")


def validate_headline_study(
    *,
    spec_path: Path,
    manifest_path: Path,
    candidate_manifest_path: Path,
    analysis_plan_path: Path,
    repo_root: Path,
    revision_validator: RevisionValidator | None = None,
    provenance_provider: ProvenanceProvider | None = None,
    mirror_probe: MirrorProbe | None = None,
    auth_probe: AuthProbe | None = None,
    require_clean_output_root: bool = True,
) -> HeadlineEvidence:
    """Validate a supported complete capsule without launching a model."""

    repo_root = repo_root.resolve()
    spec = StudySpec.load(spec_path)
    protocol = HEADLINE_PROTOCOLS.get(spec.study_id)
    if protocol is None:
        raise ValueError(f"unsupported headline study_id {spec.study_id!r}")
    manifest = _load_object(manifest_path, "headline manifest")
    candidate = _load_object(candidate_manifest_path, "candidate manifest")
    analysis = _load_object(analysis_plan_path, "analysis plan")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("status") != "FINAL-NO-SPEND"
        or manifest.get("study_id") != protocol.study_id
    ):
        raise ValueError("headline manifest identity/status is not final")
    if spec.task_manifest_hash != file_hash(manifest_path):
        raise ValueError("StudySpec task_manifest_hash does not match final manifest")
    if manifest.get("candidate_manifest_hash") != file_hash(candidate_manifest_path):
        raise ValueError("candidate manifest hash does not match final manifest")
    declared_candidate = _repo_file(
        repo_root, manifest.get("candidate_manifest"), "candidate_manifest"
    )
    if declared_candidate != candidate_manifest_path.resolve():
        raise ValueError("final manifest names a different candidate manifest")
    if manifest.get("analysis_plan_hash") != file_hash(analysis_plan_path):
        raise ValueError("analysis plan hash does not match final manifest")
    declared_analysis = _repo_file(
        repo_root, manifest.get("analysis_plan"), "analysis_plan"
    )
    if declared_analysis != analysis_plan_path.resolve():
        raise ValueError("final manifest names a different analysis plan")
    if analysis != required_analysis_plan(protocol):
        raise ValueError("headline analysis plan is not the exact locked plan")

    candidate_ids = _validate_selection(manifest, candidate, protocol=protocol)
    entries = manifest.get("tasks")
    if not isinstance(entries, list) or len(entries) != protocol.task_count:
        raise ValueError(
            f"headline manifest must declare exactly {protocol.task_count} tasks"
        )
    if tuple(entry.get("candidate_id") for entry in entries) != candidate_ids:
        raise ValueError("headline tasks are not candidate-minus-exposure order")

    probe = mirror_probe or _default_mirror_probe
    loaded = tuple(
        _validate_task(
            entry,
            candidate_id=candidate_id,
            repo_root=repo_root,
            mirror_probe=probe,
        )
        for entry, candidate_id in zip(entries, candidate_ids)
    )
    task_ids = tuple(item[0] for item in loaded)
    if len(set(task_ids)) != protocol.task_count:
        raise ValueError("headline tasks must have a unique task_id mapping")
    task_types = tuple(item[1] for item in loaded)
    task_tomls = tuple(item[2] for item in loaded)
    task_dirs = tuple(item[3] for item in loaded)
    mirrors = tuple(repository for item in loaded for repository in item[4])

    actual_arms = tuple((arm.name, arm.capability_fingerprint) for arm in spec.arms)
    if (
        spec.task_ids != task_ids
        or actual_arms != protocol.arms
        or spec.baseline_arm != "baseline"
        or spec.repetitions != 1
        or spec.attempt_policy != "first_valid_attempt"
        or spec.max_attempts != 1
        or spec.model != "claude-sonnet-5"
        or spec.token_source != "sdk_model_usage"
        or spec.score_contract != "weighted-mean-v2"
        or spec.promotion_policy != "paired-valid-complete-arms"
    ):
        raise ValueError("StudySpec does not match the locked headline contract")
    if manifest.get("arms") != protocol.arm_descriptions:
        raise ValueError("headline arm descriptions are not locked")
    if manifest.get("cache_isolation") != REQUIRED_CACHE_ISOLATION:
        raise ValueError("headline cache-isolation contract is not locked")
    if manifest.get("judge_configuration") != REQUIRED_JUDGE:
        raise ValueError("headline judge configuration is not locked")
    if manifest.get("evidence_policy") != REQUIRED_EVIDENCE_POLICY:
        raise ValueError("headline evidence policy is not locked")
    _validate_spend_guard(manifest, protocol=protocol)
    output_root = _validate_execution(
        manifest,
        entries,
        repo_root=repo_root,
        require_clean_output_root=require_clean_output_root,
        protocol=protocol,
    )

    provider = provenance_provider or _default_provenance_provider(repo_root)
    provenances = tuple(provider(task_toml) for task_toml in task_tomls)
    if any(
        provenance.task_hash != entries[index]["task_hash"]
        for index, provenance in enumerate(provenances)
    ):
        raise ValueError("captured task hash does not match final manifest")
    harness_hashes = {provenance.harness_hash for provenance in provenances}
    if (
        harness_hashes != {manifest.get("harness_hash")}
        or spec.harness not in harness_hashes
    ):
        raise ValueError("headline harness hash does not match current harness")
    verifier_hashes = {
        task_id: provenance.verifier_hash
        for task_id, provenance in zip(task_ids, provenances)
    }
    if manifest.get("verifier_hashes") != verifier_hashes:
        raise ValueError("headline verifier hashes do not match current verifiers")

    validator = revision_validator or (
        lambda revision, paths: _git_revision_matches(
            revision, paths, repo_root=repo_root
        )
    )
    if not validator(
        spec.revision,
        (
            *harness_input_paths(repo_root),
            candidate_manifest_path,
            *task_dirs,
        ),
    ):
        raise ValueError(
            f"revision {spec.revision!r} does not match current critical inputs"
        )
    expected_slots = tuple(
        (task_id, arm, 1) for task_id in task_ids for arm, _fingerprint in protocol.arms
    )
    if spec.slots() != expected_slots or len(expected_slots) != protocol.slot_count:
        raise ValueError(
            "StudySpec does not compile to exactly "
            f"{protocol.slot_count} no-retry slots"
        )
    _validate_auth(auth_probe or _default_auth_probe)

    type_counts = tuple(
        (task_type, task_types.count(task_type))
        for task_type in sorted(set(task_types))
    )
    return HeadlineEvidence(
        study_id=spec.study_id,
        spec_hash=spec.spec_hash,
        task_manifest_hash=spec.task_manifest_hash,
        analysis_plan_hash=file_hash(analysis_plan_path),
        candidate_ids=candidate_ids,
        task_ids=task_ids,
        slots=expected_slots,
        revision=spec.revision,
        mirror_repositories=mirrors,
        output_root=output_root,
        type_counts=type_counts,
        paid_dispatch_authorized=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    study_dir = REPO_ROOT / "configs" / "studies" / STUDY_ID
    parser.add_argument("--spec", type=Path, default=study_dir / "study_spec.json")
    parser.add_argument(
        "--manifest", type=Path, default=study_dir / "final_manifest.json"
    )
    parser.add_argument(
        "--candidate-manifest",
        type=Path,
        default=REPO_ROOT / "results" / "rryas_dataset" / "candidate_manifest.json",
    )
    parser.add_argument(
        "--analysis-plan", type=Path, default=study_dir / "analysis_plan.json"
    )
    args = parser.parse_args(argv)
    evidence = validate_headline_study(
        spec_path=args.spec.resolve(),
        manifest_path=args.manifest.resolve(),
        candidate_manifest_path=args.candidate_manifest.resolve(),
        analysis_plan_path=args.analysis_plan.resolve(),
        repo_root=REPO_ROOT,
    )
    print(json.dumps(asdict(evidence), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
