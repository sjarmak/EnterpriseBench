#!/usr/bin/env python3
"""Fail-closed, no-inference validation for the Finder interface pilot."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (REPO_ROOT / "lib", REPO_ROOT / "scripts" / "infra"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from eb_study import StudySpec, file_hash  # noqa: E402
from mirror_naming import derive_mirror_name  # noqa: E402
from study_run import (  # noqa: E402
    InputProvenance,
    capture_input_provenance,
    harness_input_paths,
    verifier_input_paths,
)

REQUIRED_ARMS = (
    (
        "mcp_code_finder",
        "sourcegraph-mcp-code-finder:exactly-once-per-repository:"
        "local-repos-denied:direct-tools-denied:beta-telemetry-required:"
        "proxy-v1:cache-isolated:v2",
    ),
    (
        "cli_code_finder",
        "sourcegraph-cli-code-finder:exactly-once-per-repository:"
        "local-repos-denied:direct-tools-denied:beta-telemetry-required:"
        "proxy-v1:no-mcp-registration:cache-isolated:v2",
    ),
)
REQUIRED_TASK_TYPES = (
    "dependency_graph",
    "error_provenance",
    "incident_investigation",
)
REQUIRED_TREATMENT_CONTRACT = {
    "finder_calls": "exactly_once_per_repository",
    "other_sgx_retrieval_allowed": False,
    "direct_sourcegraph_retrieval_allowed": False,
    "local_repository_source_readable": False,
    "same_proxy_telemetry_required": True,
    "required_telemetry": [
        "invocation_count",
        "repository_scope",
        "sourcegraphToolTelemetry",
        "tool_inventory_sha256",
        "code_finder_schema_sha256",
        "interface_call_count",
        "proxy_call_count",
        "cache_isolation",
    ],
    "invalid_if": [
        "zero_or_wrong_code_finder_call_count",
        "interface_and_proxy_call_count_mismatch",
        "ambiguous_or_wrong_repository_scope",
        "any_other_sgx_retrieval_call",
        "any_direct_sourcegraph_retrieval_call",
        "failed_code_finder_response",
        "missing_sourcegraphToolTelemetry",
        "missing_or_malformed_proxy_trace",
        "missing_or_invalid_cache_isolation_proof",
        "cross_run_cache_read_tokens_nonzero",
    ],
}
REQUIRED_CACHE_ISOLATION = {
    "schema_version": 1,
    "required": True,
    "comparison_rule": "valid proof and cross_run_cache_read_tokens == 0",
    "legacy_evidence": "comparison_ineligible",
}
REQUIRED_JUDGE = {
    "model": "cc:haiku",
    "account": 1,
    "executable": "claude-1",
    "selection": "explicit --judge-account 1",
    "provenance_required_in_scores": True,
}
REQUIRED_EXECUTION = {
    "agent_account": 3,
    "timeout_seconds": 600,
    "build_timeout_seconds": 1800,
    "verifier_timeout_seconds": 600,
    "memory_mb": 8192,
    "no_build": True,
    "max_attempts": 1,
}
REQUIRED_ESTIMANDS = {
    "primary": "paired_task_score_difference_cli_minus_mcp",
    "secondary": [
        "reported_outer_cost_usd",
        "elapsed_seconds",
        "combined_tokens",
        "finder_activity",
    ],
    "inference": "descriptive_only_n3",
}
REQUIRED_SPEND_GUARD = {
    "slots": 6,
    "paid_dispatch_requires_separate_explicit_authorization": True,
    "calibrated_reported_outer_spend_usd": 1.38,
    "inner_finder_cost": "unavailable",
}
REQUIRED_EVIDENCE_POLICY = {
    "exclude_canary_outcomes": True,
    "excluded_task_ids": ["dep-traversal-003"],
    "promotion": "none",
}
REQUIRED_SELECTION_RULE = (
    "declared duration then task_id; reject only prompt leakage, unavailable "
    "mirrors, or structural verifier failure"
)
ALLOWED_REJECTION_REASONS = {
    "prompt_leakage",
    "unavailable_mirrors",
    "structural_verifier_failure",
}
REQUIRED_MODEL = "claude-sonnet-5"
REQUIRED_SCORE_CONTRACT = "weighted-mean-v2"
REQUIRED_PROMOTION_POLICY = "descriptive-interface-pilot-no-promotion"
REQUIRED_ATTEMPT_POLICY = "first_valid_attempt"
REQUIRED_TOKEN_SOURCE = "sdk_model_usage"

RevisionValidator = Callable[[str, Sequence[Path]], bool]
ProvenanceProvider = Callable[[Path], InputProvenance]
MirrorProbe = Callable[[str], bool]


@dataclass(frozen=True)
class InterfacePilotEvidence:
    """The exact paid trial slots admitted by no-spend preflight."""

    study_id: str
    spec_hash: str
    task_manifest_hash: str
    task_ids: tuple[str, ...]
    slots: tuple[tuple[str, str, int], ...]
    revision: str
    mirror_repositories: tuple[str, ...]
    calibrated_reported_outer_spend_usd: float


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} {path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} {path} must contain a JSON object")
    return payload


def _repo_file(repo_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty repository-relative path")
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"{label} must be repository-relative: {value}")
    root = repo_root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository: {value}") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} does not exist: {resolved}")
    return resolved


def _validate_selection(selection: Any) -> None:
    if not isinstance(selection, dict):
        raise ValueError("selection audit must be an object")
    if (
        selection.get("rule") != REQUIRED_SELECTION_RULE
        or selection.get("outcomes_inspected") is not False
    ):
        raise ValueError(
            "selection audit does not preserve the locked outcome-blind rule"
        )
    rejections = selection.get("rejections")
    if not isinstance(rejections, list):
        raise ValueError("selection audit rejections must be a list")
    for rejection in rejections:
        if (
            not isinstance(rejection, dict)
            or not isinstance(rejection.get("candidate_id"), str)
            or rejection.get("reason") not in ALLOWED_REJECTION_REASONS
            or not isinstance(rejection.get("detail"), str)
            or rejection.get("outcomes_inspected") is not False
        ):
            raise ValueError("selection audit contains an invalid rejection receipt")


def _expected_mirrors(task_data: dict[str, Any]) -> tuple[str, ...]:
    repos = task_data.get("repos")
    if not isinstance(repos, list) or len(repos) != 2:
        raise ValueError("each interface-pilot task must declare exactly two repos")
    mirrors = []
    for repo in repos:
        if not isinstance(repo, dict):
            raise ValueError("task repo entry must be an object")
        url = repo.get("url")
        rev = repo.get("rev")
        if not isinstance(url, str) or not isinstance(rev, str):
            raise ValueError("task repo URL and revision must be strings")
        mirrors.append(f"github.com/{derive_mirror_name(url, rev)}")
    return tuple(mirrors)


def _load_task_entry(
    entry: Any,
    curated_ids: set[str],
    repo_root: Path,
) -> tuple[str, str, Path, dict[str, Any]]:
    if not isinstance(entry, dict):
        raise ValueError("interface-pilot task entry must be an object")
    task_id = entry.get("task_id")
    if not isinstance(task_id, str) or task_id not in curated_ids:
        raise ValueError(f"pilot task {task_id!r} is not in curated manifest")
    task_toml = _repo_file(repo_root, entry.get("task_toml"), "task_toml")
    if entry.get("task_hash") != file_hash(task_toml):
        raise ValueError(f"task hash does not match {task_toml}")
    try:
        task_data = tomllib.loads(task_toml.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot parse task TOML {task_toml}: {exc}") from exc

    task = task_data.get("task", {})
    task_type = task.get("task_type")
    if task.get("id") != task_id or entry.get("task_type") != task_type:
        raise ValueError(f"task identity/type does not match manifest for {task_id!r}")
    if task_data.get("difficulty_stratum") != "dual_repo":
        raise ValueError(f"task {task_id!r} is not dual_repo")
    return task_id, task_type, task_toml, task_data


def _validate_task_audit(entry: dict[str, Any], task_id: str) -> None:
    if entry.get("selection_audit") != {
        "prompt_leakage": "pass",
        "structural_verifier": "pass",
        "prior_run_count": 0,
    }:
        raise ValueError(f"task {task_id!r} failed its selection audit")


def _validate_task_mirrors(
    entry: dict[str, Any],
    task_id: str,
    task_data: dict[str, Any],
    mirror_probe: MirrorProbe,
) -> tuple[str, ...]:
    mirrors = _expected_mirrors(task_data)
    if entry.get("expected_repositories") != list(mirrors):
        raise ValueError(f"task {task_id!r} repository scope does not match task TOML")
    for repository in mirrors:
        if not mirror_probe(repository):
            raise ValueError(f"Sourcegraph mirror is unavailable: {repository}")
    return mirrors


def _task_inputs(
    manifest: dict[str, Any],
    curated: dict[str, Any],
    repo_root: Path,
    mirror_probe: MirrorProbe,
) -> tuple[tuple[str, ...], tuple[Path, ...], tuple[Path, ...], tuple[str, ...]]:
    entries = manifest.get("tasks")
    if not isinstance(entries, list) or len(entries) != 3:
        raise ValueError("interface-pilot manifest must declare exactly three tasks")
    declared_ids = curated.get("task_ids")
    if not isinstance(declared_ids, list) or not all(
        isinstance(task_id, str) and task_id for task_id in declared_ids
    ):
        raise ValueError("curated manifest must contain a valid task_ids list")
    curated_ids = set(declared_ids)

    task_ids: list[str] = []
    task_tomls: list[Path] = []
    critical_paths: list[Path] = []
    all_mirrors: list[str] = []
    task_types: list[str] = []
    for entry in entries:
        task_id, task_type, task_toml, task_data = _load_task_entry(
            entry, curated_ids, repo_root
        )
        _validate_task_audit(entry, task_id)
        mirrors = _validate_task_mirrors(entry, task_id, task_data, mirror_probe)

        task_ids.append(task_id)
        task_types.append(task_type)
        task_tomls.append(task_toml)
        critical_paths.append(task_toml.parent)
        all_mirrors.extend(mirrors)

    if tuple(task_types) != REQUIRED_TASK_TYPES:
        raise ValueError("interface pilot does not contain the exact task-type mix")
    if len(set(all_mirrors)) != len(all_mirrors):
        raise ValueError("interface-pilot repository scopes must be distinct")
    return (
        tuple(task_ids),
        tuple(task_tomls),
        tuple(critical_paths),
        tuple(all_mirrors),
    )


def _git_revision_matches(
    revision: str,
    critical_paths: Sequence[Path],
    *,
    repo_root: Path,
) -> bool:
    relative_paths = [
        str(path.resolve().relative_to(repo_root.resolve())) for path in critical_paths
    ]
    for command in (
        ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
        ["git", "diff", "--quiet", revision, "--", *relative_paths],
    ):
        result = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return False
    return True


def _default_provenance_provider(repo_root: Path) -> ProvenanceProvider:
    def provide(task_toml: Path) -> InputProvenance:
        return capture_input_provenance(
            task_toml=task_toml,
            harness_inputs=harness_input_paths(repo_root),
            verifier_inputs=verifier_input_paths(repo_root, task_toml.parent),
            repo_root=repo_root,
        )

    return provide


def _default_mirror_probe(repository: str) -> bool:
    cli = REPO_ROOT / "agents" / "harnesses" / "claude" / "mcp" / "sg_cli.py"
    result = subprocess.run(
        [sys.executable, str(cli), "ls", repository],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _validate_exact_contracts(manifest: dict[str, Any]) -> None:
    contracts = (
        ("treatment contract", "treatment_contract", REQUIRED_TREATMENT_CONTRACT),
        ("cache-isolation contract", "cache_isolation", REQUIRED_CACHE_ISOLATION),
        ("judge configuration", "judge_configuration", REQUIRED_JUDGE),
        ("execution configuration", "execution_configuration", REQUIRED_EXECUTION),
        ("estimands", "estimands", REQUIRED_ESTIMANDS),
        ("spend guard", "spend_guard", REQUIRED_SPEND_GUARD),
        ("evidence policy", "evidence_policy", REQUIRED_EVIDENCE_POLICY),
    )
    for label, field, required in contracts:
        if manifest.get(field) != required:
            raise ValueError(f"interface-pilot {label} does not match locked contract")


def validate_interface_pilot(
    *,
    spec_path: Path,
    manifest_path: Path,
    curated_manifest_path: Path,
    repo_root: Path,
    revision_validator: RevisionValidator | None = None,
    provenance_provider: ProvenanceProvider | None = None,
    mirror_probe: MirrorProbe | None = None,
) -> InterfacePilotEvidence:
    """Validate the six-slot capsule without launching an agent or judge."""

    repo_root = repo_root.resolve()
    spec = StudySpec.load(spec_path)
    manifest = _load_object(manifest_path, "pilot manifest")
    curated = _load_object(curated_manifest_path, "curated manifest")

    if manifest.get("schema_version") != 1 or manifest.get("status") != "locked-pilot":
        raise ValueError("pilot manifest must be locked at schema_version 1")
    if manifest.get("study_id") != spec.study_id:
        raise ValueError("pilot manifest and StudySpec study_id do not match")
    if spec.task_manifest_hash != file_hash(manifest_path):
        raise ValueError("StudySpec task_manifest_hash does not match pilot manifest")
    if manifest.get("curated_manifest_hash") != file_hash(curated_manifest_path):
        raise ValueError("curated manifest hash does not match pilot manifest")
    declared_curated = _repo_file(
        repo_root, manifest.get("curated_manifest"), "curated_manifest"
    )
    if declared_curated != curated_manifest_path.resolve():
        raise ValueError("pilot manifest names a different curated manifest")

    _validate_selection(manifest.get("selection"))
    _validate_exact_contracts(manifest)
    task_ids, task_tomls, task_paths, mirrors = _task_inputs(
        manifest,
        curated,
        repo_root,
        mirror_probe or _default_mirror_probe,
    )
    if spec.task_ids != task_ids:
        raise ValueError("StudySpec task_ids do not match the locked pilot manifest")
    actual_arms = tuple((arm.name, arm.capability_fingerprint) for arm in spec.arms)
    if actual_arms != REQUIRED_ARMS:
        raise ValueError("StudySpec must declare the exact arms and fingerprints")
    if (
        spec.baseline_arm != "mcp_code_finder"
        or spec.repetitions != 1
        or spec.attempt_policy != REQUIRED_ATTEMPT_POLICY
        or spec.max_attempts != 1
        or spec.model != REQUIRED_MODEL
        or spec.token_source != REQUIRED_TOKEN_SOURCE
        or spec.score_contract != REQUIRED_SCORE_CONTRACT
        or spec.promotion_policy != REQUIRED_PROMOTION_POLICY
    ):
        raise ValueError("StudySpec does not match the locked interface-pilot contract")

    provider = provenance_provider or _default_provenance_provider(repo_root)
    provenances = tuple(provider(task_toml) for task_toml in task_tomls)
    if any(
        provenance.task_hash != manifest["tasks"][index]["task_hash"]
        for index, provenance in enumerate(provenances)
    ):
        raise ValueError("captured task hash does not match pilot manifest")
    harness_hashes = {provenance.harness_hash for provenance in provenances}
    if (
        harness_hashes != {manifest.get("harness_hash")}
        or spec.harness not in harness_hashes
    ):
        raise ValueError("pilot harness hash does not match current harness")
    verifier_hashes = {
        task_id: provenance.verifier_hash
        for task_id, provenance in zip(task_ids, provenances)
    }
    if manifest.get("verifier_hashes") != verifier_hashes:
        raise ValueError("pilot verifier hashes do not match current verifiers")

    critical_paths = (
        repo_root / "scripts" / "orchestration",
        repo_root / "scripts" / "sandbox",
        repo_root / "scripts" / "lib",
        repo_root / "scripts" / "cost_tracker.py",
        repo_root / "scripts" / "analyze_scores.py",
        repo_root / "lib" / "eb_verify",
        repo_root / "lib" / "eb_study",
        repo_root / "lib" / "pyproject.toml",
        repo_root / "agents" / "harnesses" / "claude",
        *task_paths,
    )
    validator = revision_validator or (
        lambda revision, paths: _git_revision_matches(
            revision, paths, repo_root=repo_root
        )
    )
    if not validator(spec.revision, critical_paths):
        raise ValueError(
            f"revision {spec.revision!r} does not match current critical inputs"
        )

    expected_slots = tuple(
        (task_id, arm, 1) for task_id in task_ids for arm, _fingerprint in REQUIRED_ARMS
    )
    if spec.slots() != expected_slots:
        raise ValueError("StudySpec does not compile to exactly six matched slots")
    return InterfacePilotEvidence(
        study_id=spec.study_id,
        spec_hash=spec.spec_hash,
        task_manifest_hash=spec.task_manifest_hash,
        task_ids=task_ids,
        slots=expected_slots,
        revision=spec.revision,
        mirror_repositories=mirrors,
        calibrated_reported_outer_spend_usd=1.38,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--curated-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    evidence = validate_interface_pilot(
        spec_path=args.spec,
        manifest_path=args.manifest,
        curated_manifest_path=args.curated_manifest,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(asdict(evidence), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
