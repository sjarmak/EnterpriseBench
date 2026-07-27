#!/usr/bin/env python3
"""Fail-closed, no-inference validation for the Finder interface supplement."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (REPO_ROOT / "lib", REPO_ROOT / "scripts" / "infra"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from code_finder_interface_pilot_preflight import (  # noqa: E402
    REQUIRED_ARMS,
    REQUIRED_ATTEMPT_POLICY,
    REQUIRED_CACHE_ISOLATION,
    REQUIRED_JUDGE,
    REQUIRED_MODEL,
    REQUIRED_SCORE_CONTRACT,
    REQUIRED_TOKEN_SOURCE,
    REQUIRED_TREATMENT_CONTRACT,
    MirrorProbe,
    ProvenanceProvider,
    RevisionValidator,
    _default_mirror_probe,
    _default_provenance_provider,
    _git_revision_matches,
    _load_object,
    _load_task_entry,
    _repo_file,
    _validate_task_mirrors,
)
from eb_study import StudySpec, file_hash  # noqa: E402
from mode_gate import IneligibleTask, check_eligibility  # noqa: E402
from run_task import WORKSPACE_DIR, _derive_graded_artifact_path  # noqa: E402

STUDY_ID = "rryas-code-finder-interface-supplement-v1"
PARENT_STUDY_ID = "rryas-code-finder-interface-pilot-v1"
TASK_ID = "incident-investigation-dual-nerdctl-001"
REPORT_PATH = "/workspace/agent_output/INCIDENT_REPORT.md"
REQUIRED_PROMOTION_POLICY = "descriptive-interface-supplement-no-promotion"
REQUIRED_SELECTION_RULE = (
    "among previously unrun curated dual-repository incident tasks, sort by "
    "declared duration then task_id; reject prompt leakage or structural "
    "ineligibility; select the first passing task"
)
REQUIRED_CANDIDATE_ORDER = (
    "incident-investigation-dual-flux-001",
    "incident-investigation-dual-prometheus-001",
    "incident-investigation-dual-kafka-001",
    TASK_ID,
)
REQUIRED_EXECUTION_BASE = {
    "agent_account": 3,
    "timeout_seconds": 600,
    "build_timeout_seconds": 1800,
    "verifier_timeout_seconds": 600,
    "memory_mb": 8192,
    "no_build": True,
    "max_attempts": 1,
}
REQUIRED_SPEND_BASE = {
    "slots": 2,
    "max_attempts_per_slot": 1,
    "paid_dispatch_requires_new_explicit_authorization": True,
    "forecast_reported_outer_spend_usd": 3.61,
    "inner_finder_cost": "unavailable",
}
REQUIRED_EVIDENCE_POLICY = {
    "exclude_parent_invalid_pair_from_quality": True,
    "parent_invalid_task_id": "incident-investigation-dual-istio-001",
    "promotion": "none",
}


@dataclass(frozen=True)
class InterfaceSupplementEvidence:
    """The exact two paid slots admitted by the no-spend supplement preflight."""

    study_id: str
    spec_hash: str
    task_manifest_hash: str
    task_ids: tuple[str, ...]
    slots: tuple[tuple[str, str, int], ...]
    revision: str
    mirror_repositories: tuple[str, ...]
    graded_artifact_path: str
    forecast_reported_outer_spend_usd: float
    paid_dispatch_authorized: bool


def _validate_selection(selection: Any) -> None:
    if not isinstance(selection, dict):
        raise ValueError("supplement selection audit must be an object")
    if (
        selection.get("rule") != REQUIRED_SELECTION_RULE
        or selection.get("candidate_outcomes_inspected") is not False
        or not isinstance(selection.get("parent_invalidity_trigger"), str)
        or not selection["parent_invalidity_trigger"]
        or tuple(selection.get("candidate_order", ())) != REQUIRED_CANDIDATE_ORDER
    ):
        raise ValueError("supplement selection is not the locked outcome-blind audit")

    rejections = selection.get("rejections")
    if not isinstance(rejections, list) or len(rejections) != 3:
        raise ValueError("supplement selection must contain three rejection receipts")
    for candidate_id, rejection in zip(REQUIRED_CANDIDATE_ORDER[:3], rejections):
        if (
            not isinstance(rejection, dict)
            or rejection.get("candidate_id") != candidate_id
            or rejection.get("reason") != "prompt_leakage"
            or not isinstance(rejection.get("detail"), str)
            or not rejection["detail"]
            or rejection.get("candidate_outcomes_inspected") is not False
        ):
            raise ValueError("supplement selection contains an invalid rejection")

    selected = selection.get("selected")
    if (
        not isinstance(selected, dict)
        or selected.get("task_id") != TASK_ID
        or selected.get("declared_duration_minutes") != 45
        or selected.get("prior_run_count") != 0
        or selected.get("prompt_leakage") != "pass"
        or not str(selected.get("structural_eligibility", "")).startswith("pass")
        or selected.get("candidate_outcomes_inspected") is not False
    ):
        raise ValueError("supplement selected-task audit is not locked")


def _validate_contracts(manifest: dict[str, Any]) -> None:
    exact_contracts = (
        ("treatment contract", "treatment_contract", REQUIRED_TREATMENT_CONTRACT),
        ("cache-isolation contract", "cache_isolation", REQUIRED_CACHE_ISOLATION),
        ("judge configuration", "judge_configuration", REQUIRED_JUDGE),
        ("evidence policy", "evidence_policy", REQUIRED_EVIDENCE_POLICY),
    )
    for label, field, required in exact_contracts:
        if manifest.get(field) != required:
            raise ValueError(f"interface-supplement {label} does not match locked contract")

    execution = manifest.get("execution_configuration")
    expected_order = [
        [TASK_ID, "mcp_code_finder", 1],
        [TASK_ID, "cli_code_finder", 1],
    ]
    if (
        not isinstance(execution, dict)
        or any(execution.get(key) != value for key, value in REQUIRED_EXECUTION_BASE.items())
        or execution.get("execution_order") != expected_order
        or set(execution) != {*REQUIRED_EXECUTION_BASE, "execution_order"}
    ):
        raise ValueError(
            "interface-supplement execution configuration does not match locked contract"
        )

    spend = manifest.get("spend_guard")
    if (
        not isinstance(spend, dict)
        or any(spend.get(key) != value for key, value in REQUIRED_SPEND_BASE.items())
        or not isinstance(spend.get("forecast_basis"), str)
        or not spend["forecast_basis"]
        or set(spend) != {*REQUIRED_SPEND_BASE, "forecast_basis"}
    ):
        raise ValueError("interface-supplement spend guard does not match locked contract")

    estimands = manifest.get("estimands")
    if (
        not isinstance(estimands, dict)
        or estimands.get("primary")
        != "paired_task_score_difference_cli_minus_mcp"
        or estimands.get("secondary")
        != [
            "reported_outer_cost_usd",
            "elapsed_seconds",
            "combined_tokens",
            "finder_activity",
        ]
        or estimands.get("inference")
        != "descriptive_only_n3_after_valid_supplement"
        or not isinstance(estimands.get("combined_analysis"), str)
        or not estimands["combined_analysis"]
        or set(estimands)
        != {"primary", "secondary", "combined_analysis", "inference"}
    ):
        raise ValueError("interface-supplement estimands do not match locked contract")


def _load_supplement_task(
    manifest: dict[str, Any],
    curated: dict[str, Any],
    repo_root: Path,
    mirror_probe: MirrorProbe,
) -> tuple[Path, Path, tuple[str, ...]]:
    entries = manifest.get("tasks")
    if not isinstance(entries, list) or len(entries) != 1:
        raise ValueError("interface-supplement manifest must declare exactly one task")
    declared_ids = curated.get("task_ids")
    if not isinstance(declared_ids, list):
        raise ValueError("curated manifest must contain task_ids")

    entry = entries[0]
    task_id, task_type, task_toml, task_data = _load_task_entry(
        entry, set(declared_ids), repo_root
    )
    if task_id != TASK_ID or task_type != "incident_investigation":
        raise ValueError("interface-supplement task is not the locked incident task")
    mirrors = _validate_task_mirrors(
        entry, task_id, task_data, mirror_probe
    )

    task_dir = task_toml.parent
    artifact_path = _derive_graded_artifact_path(task_dir)
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
            "supplement graded artifact must be writable outside gated repositories"
        ) from exc
    if artifact_path != REPORT_PATH or entry.get("graded_artifact_path") != REPORT_PATH:
        raise ValueError(
            f"supplement must use the exact graded artifact path {REPORT_PATH}"
        )

    instruction = _repo_file(
        repo_root,
        str((task_dir / "instruction.md").relative_to(repo_root)),
        "delivered instruction",
    ).read_text()
    if REPORT_PATH not in instruction or "/workspace/agent_output/answer.json" in instruction:
        raise ValueError(
            "delivered instruction conflicts with the locked graded artifact path"
        )
    if REPORT_PATH not in task_toml.read_text():
        raise ValueError("task metadata conflicts with the locked graded artifact path")
    return task_toml, task_dir, mirrors


def _critical_paths(repo_root: Path, task_dir: Path) -> tuple[Path, ...]:
    return (
        repo_root / "scripts" / "orchestration",
        repo_root / "scripts" / "sandbox",
        repo_root / "scripts" / "lib",
        repo_root / "scripts" / "cost_tracker.py",
        repo_root / "scripts" / "analyze_scores.py",
        repo_root / "lib" / "eb_verify",
        repo_root / "lib" / "eb_study",
        repo_root / "lib" / "pyproject.toml",
        repo_root / "agents" / "harnesses" / "claude",
        task_dir,
    )


def validate_interface_supplement(
    *,
    spec_path: Path,
    manifest_path: Path,
    curated_manifest_path: Path,
    repo_root: Path,
    revision_validator: RevisionValidator | None = None,
    provenance_provider: ProvenanceProvider | None = None,
    mirror_probe: MirrorProbe | None = None,
) -> InterfaceSupplementEvidence:
    """Validate the two-slot supplement without launching an agent or judge."""

    repo_root = repo_root.resolve()
    spec = StudySpec.load(spec_path)
    manifest = _load_object(manifest_path, "supplement manifest")
    curated = _load_object(curated_manifest_path, "curated manifest")

    if (
        manifest.get("schema_version") != 1
        or manifest.get("status") != "locked-supplement"
        or manifest.get("study_id") != STUDY_ID
        or manifest.get("parent_study_id") != PARENT_STUDY_ID
        or spec.study_id != STUDY_ID
    ):
        raise ValueError("supplement manifest identity/status is not locked")
    if spec.task_manifest_hash != file_hash(manifest_path):
        raise ValueError("StudySpec task_manifest_hash does not match supplement manifest")
    if manifest.get("curated_manifest_hash") != file_hash(curated_manifest_path):
        raise ValueError("curated manifest hash does not match supplement manifest")
    declared_curated = _repo_file(
        repo_root, manifest.get("curated_manifest"), "curated_manifest"
    )
    if declared_curated != curated_manifest_path.resolve():
        raise ValueError("supplement manifest names a different curated manifest")

    _validate_selection(manifest.get("selection"))
    _validate_contracts(manifest)
    task_toml, task_dir, mirrors = _load_supplement_task(
        manifest, curated, repo_root, mirror_probe or _default_mirror_probe
    )

    actual_arms = tuple((arm.name, arm.capability_fingerprint) for arm in spec.arms)
    if actual_arms != REQUIRED_ARMS:
        raise ValueError("StudySpec must declare the exact arms and fingerprints")
    if (
        spec.task_ids != (TASK_ID,)
        or spec.baseline_arm != "mcp_code_finder"
        or spec.repetitions != 1
        or spec.attempt_policy != REQUIRED_ATTEMPT_POLICY
        or spec.max_attempts != 1
        or spec.model != REQUIRED_MODEL
        or spec.token_source != REQUIRED_TOKEN_SOURCE
        or spec.score_contract != REQUIRED_SCORE_CONTRACT
        or spec.promotion_policy != REQUIRED_PROMOTION_POLICY
    ):
        raise ValueError("StudySpec does not match the locked supplement contract")

    provider = provenance_provider or _default_provenance_provider(repo_root)
    provenance = provider(task_toml)
    task_entry = manifest["tasks"][0]
    if provenance.task_hash != task_entry["task_hash"]:
        raise ValueError("captured task hash does not match supplement manifest")
    if (
        provenance.harness_hash != manifest.get("harness_hash")
        or spec.harness != provenance.harness_hash
    ):
        raise ValueError("supplement harness hash does not match current harness")
    if manifest.get("verifier_hashes") != {TASK_ID: provenance.verifier_hash}:
        raise ValueError("supplement verifier hash does not match current verifier")

    validator = revision_validator or (
        lambda revision, paths: _git_revision_matches(
            revision, paths, repo_root=repo_root
        )
    )
    if not validator(spec.revision, _critical_paths(repo_root, task_dir)):
        raise ValueError(
            f"revision {spec.revision!r} does not match current critical inputs"
        )

    expected_slots = (
        (TASK_ID, "mcp_code_finder", 1),
        (TASK_ID, "cli_code_finder", 1),
    )
    if spec.slots() != expected_slots:
        raise ValueError("StudySpec does not compile to exactly two matched slots")
    return InterfaceSupplementEvidence(
        study_id=spec.study_id,
        spec_hash=spec.spec_hash,
        task_manifest_hash=spec.task_manifest_hash,
        task_ids=spec.task_ids,
        slots=expected_slots,
        revision=spec.revision,
        mirror_repositories=mirrors,
        graded_artifact_path=REPORT_PATH,
        forecast_reported_outer_spend_usd=3.61,
        paid_dispatch_authorized=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--curated-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    evidence = validate_interface_supplement(
        spec_path=args.spec,
        manifest_path=args.manifest,
        curated_manifest_path=args.curated_manifest,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(asdict(evidence), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
