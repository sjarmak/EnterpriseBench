#!/usr/bin/env python3
"""Fail-closed, no-inference validation for the rryas headline study."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

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
from headline_protocol import (  # noqa: E402,F401
    CANDIDATE_LOCK_REVISION,
    HEADLINE_PROTOCOLS,
    POST_LOCK_EXPOSURES,
    POST_LOCK_EXPOSURE_EVIDENCE,
    REQUIRED_ANALYSIS_PLAN,
    REQUIRED_ARMS,
    REQUIRED_CACHE_ISOLATION,
    REQUIRED_EVIDENCE_POLICY,
    REQUIRED_EXECUTION_BASE,
    REQUIRED_JUDGE,
    REQUIRED_ORDER_POLICY,
    REQUIRED_SELECTION_RULE,
    STUDY_ID,
    V1_PROTOCOL,
    V2_ADDITIONAL_EXPOSURES,
    V2_PROTOCOL,
    V2_REQUIRED_ARMS,
    V3_ADDITIONAL_EXPOSURES,
    V3_PROTOCOL,
    V4_PROTOCOL,
    V4_REQUIRED_JUDGE,
    V5_PROTOCOL,
    HeadlineProtocol,
    required_analysis_plan,
)
from headline_protocol_evidence import (  # noqa: E402
    validate_protocol_amendment_evidence,
)
from mirror_naming import derive_mirror_name  # noqa: E402
from mode_gate import IneligibleTask, check_eligibility  # noqa: E402
from run_task import (  # noqa: E402
    WORKSPACE_DIR,
    _derive_graded_artifact_path,
    _verifier_specs_by_name,
)
from study_run import harness_input_paths  # noqa: E402

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
    validate_protocol_amendment_evidence(
        repo_root,
        analysis,
        protocol=protocol,
    )

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
    expected_judge = (
        V4_REQUIRED_JUDGE
        if protocol in (V4_PROTOCOL, V5_PROTOCOL)
        else REQUIRED_JUDGE
    )
    if manifest.get("judge_configuration") != expected_judge:
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
