#!/usr/bin/env python3
"""Fail-closed, no-inference validation for the locked rryas pilot capsule."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "lib"))

from eb_study import StudySpec, file_hash  # noqa: E402
from study_run import (  # noqa: E402
    InputProvenance,
    capture_input_provenance,
    harness_input_paths,
    verifier_input_paths,
)

REQUIRED_GATES = (
    "EnterpriseBench-rryas.11",
    "EnterpriseBench-rryas.12",
    "EnterpriseBench-rryas.13",
    "EnterpriseBench-rryas.14",
    "EnterpriseBench-rryas.30",
    "EnterpriseBench-xrji0",
)
REQUIRED_ARMS = (
    ("baseline", "local-repos:no-mcp:no-sgx:cache-isolated:v2"),
    ("mcp_only", "sourcegraph-mcp:local-repos-denied:cache-isolated:v2"),
    ("cli", "sgx-cli:local-repos-readable:usage-required:cache-isolated:v2"),
)
REQUIRED_CACHE_ISOLATION = {
    "schema_version": 1,
    "required": True,
    "comparison_rule": "valid proof and cross_run_cache_read_tokens == 0",
    "legacy_evidence": "comparison_ineligible",
}
REQUIRED_MODEL = "claude-sonnet-5"
REQUIRED_SCORE_CONTRACT = "weighted-mean-v2"
REQUIRED_PROMOTION_POLICY = "paired-valid-complete-arms"
REQUIRED_ATTEMPT_POLICY = "first_valid_attempt"
REQUIRED_TOKEN_SOURCE = "sdk_model_usage"

RevisionValidator = Callable[[str, Sequence[Path]], bool]
ProvenanceProvider = Callable[[Path], InputProvenance]


@dataclass(frozen=True)
class PilotEvidence:
    """The exact paid trial slots admitted by preflight."""

    study_id: str
    spec_hash: str
    task_manifest_hash: str
    task_ids: tuple[str, ...]
    slots: tuple[tuple[str, str, int], ...]
    revision: str
    closed_gates: tuple[str, ...]


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


def _task_inputs(
    manifest: dict[str, Any],
    curated: dict[str, Any],
    repo_root: Path,
) -> tuple[tuple[str, ...], tuple[Path, ...], tuple[Path, ...]]:
    task_entries = manifest.get("tasks")
    if not isinstance(task_entries, list) or len(task_entries) != 1:
        raise ValueError("pilot manifest must declare exactly one task")
    curated_entries = curated.get("task_ids")
    if not isinstance(curated_entries, list) or not all(
        isinstance(task_id, str) and task_id for task_id in curated_entries
    ):
        raise ValueError("curated manifest must contain a valid task_ids list")
    curated_ids = set(curated_entries)

    entry = task_entries[0]
    if not isinstance(entry, dict):
        raise ValueError("pilot task entry must be an object")
    task_id = entry.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("pilot task_id must be a non-empty string")
    if task_id not in curated_ids:
        raise ValueError(f"pilot task {task_id!r} is not in curated manifest")

    task_toml = _repo_file(repo_root, entry.get("task_toml"), "task_toml")
    if entry.get("task_hash") != file_hash(task_toml):
        raise ValueError(f"task hash does not match {task_toml}")
    try:
        task_data = tomllib.loads(task_toml.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot parse task TOML {task_toml}: {exc}") from exc
    if task_data.get("task", {}).get("id") != task_id:
        raise ValueError(f"task TOML identity does not match pilot task {task_id!r}")

    mirror_value = task_data.get("tool_access", {}).get("sourcegraph_mirror_config")
    mirror_path = _repo_file(repo_root, mirror_value, "sourcegraph_mirror_config")
    _load_object(mirror_path, "Sourcegraph mirror config")
    return (task_id,), (task_toml,), (task_toml.parent, mirror_path)


def _git_revision_matches(
    revision: str,
    critical_paths: Sequence[Path],
    *,
    repo_root: Path,
) -> bool:
    relative_paths = [
        str(path.resolve().relative_to(repo_root.resolve())) for path in critical_paths
    ]
    checks = (
        ["git", "merge-base", "--is-ancestor", revision, "HEAD"],
        ["git", "diff", "--quiet", revision, "--", *relative_paths],
    )
    for command in checks:
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


def _default_revision_validator(repo_root: Path) -> RevisionValidator:
    return lambda revision, paths: _git_revision_matches(
        revision, paths, repo_root=repo_root
    )


def _default_provenance_provider(repo_root: Path) -> ProvenanceProvider:
    def provide(task_toml: Path) -> InputProvenance:
        return capture_input_provenance(
            task_toml=task_toml,
            harness_inputs=harness_input_paths(repo_root),
            verifier_inputs=verifier_input_paths(repo_root, task_toml.parent),
            repo_root=repo_root,
        )

    return provide


def validate_pilot(
    *,
    spec_path: Path,
    manifest_path: Path,
    curated_manifest_path: Path,
    repo_root: Path,
    closed_gates: frozenset[str],
    revision_validator: RevisionValidator | None = None,
    provenance_provider: ProvenanceProvider | None = None,
) -> PilotEvidence:
    """Validate the locked three-trial pilot without launching any model."""

    repo_root = repo_root.resolve()
    spec = StudySpec.load(spec_path)
    manifest = _load_object(manifest_path, "pilot manifest")
    curated = _load_object(curated_manifest_path, "curated manifest")

    if manifest.get("schema_version") != 1:
        raise ValueError("pilot manifest schema_version must be 1")
    if manifest.get("status") != "locked-pilot":
        raise ValueError("pilot manifest status must be 'locked-pilot'")
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

    declared_gates = manifest.get("integrity_gates")
    if declared_gates != list(REQUIRED_GATES):
        raise ValueError("pilot manifest does not declare the exact integrity gates")
    if manifest.get("cache_isolation") != REQUIRED_CACHE_ISOLATION:
        raise ValueError("pilot manifest does not declare the cache-isolation contract")
    missing_gates = sorted(set(REQUIRED_GATES) - closed_gates)
    if missing_gates:
        raise ValueError(f"integrity gates are not closed: {missing_gates}")

    task_ids, task_tomls, task_paths = _task_inputs(manifest, curated, repo_root)
    if spec.task_ids != task_ids:
        raise ValueError("StudySpec task_ids do not match the locked pilot manifest")
    actual_arms = tuple((arm.name, arm.capability_fingerprint) for arm in spec.arms)
    if actual_arms != REQUIRED_ARMS:
        raise ValueError("StudySpec must declare the exact arms and fingerprints")
    if (
        spec.baseline_arm != "baseline"
        or spec.repetitions != 1
        or spec.attempt_policy != REQUIRED_ATTEMPT_POLICY
        or spec.max_attempts != 2
        or spec.model != REQUIRED_MODEL
        or spec.token_source != REQUIRED_TOKEN_SOURCE
        or spec.score_contract != REQUIRED_SCORE_CONTRACT
        or spec.promotion_policy != REQUIRED_PROMOTION_POLICY
    ):
        raise ValueError("StudySpec does not match the locked cheap-pilot contract")

    provider = provenance_provider or _default_provenance_provider(repo_root)
    provenance = provider(task_tomls[0])
    if manifest.get("harness_hash") != provenance.harness_hash:
        raise ValueError("pilot manifest harness_hash does not match current harness")
    if spec.harness != provenance.harness_hash:
        raise ValueError("StudySpec harness does not match current harness")
    if manifest.get("verifier_hashes") != {task_ids[0]: provenance.verifier_hash}:
        raise ValueError("pilot manifest verifier hash does not match current verifier")

    critical_paths = (
        repo_root / "scripts" / "orchestration",
        repo_root / "scripts" / "sandbox",
        repo_root / "scripts" / "lib",
        repo_root / "scripts" / "infra" / "create_sg_mirrors.py",
        repo_root / "scripts" / "cost_tracker.py",
        repo_root / "scripts" / "analyze_scores.py",
        repo_root / "lib" / "eb_verify",
        repo_root / "lib" / "eb_study",
        repo_root / "lib" / "pyproject.toml",
        repo_root / "agents" / "harnesses" / "claude",
        *task_paths,
    )
    validator = revision_validator or _default_revision_validator(repo_root)
    if not validator(spec.revision, critical_paths):
        raise ValueError(
            f"revision {spec.revision!r} does not match current critical inputs"
        )

    expected_slots = tuple((task_ids[0], arm, 1) for arm, _fingerprint in REQUIRED_ARMS)
    if spec.slots() != expected_slots:
        raise ValueError("StudySpec does not compile to exactly three pilot slots")
    return PilotEvidence(
        study_id=spec.study_id,
        spec_hash=spec.spec_hash,
        task_manifest_hash=spec.task_manifest_hash,
        task_ids=task_ids,
        slots=expected_slots,
        revision=spec.revision,
        closed_gates=tuple(REQUIRED_GATES),
    )


def _closed_gate_ids() -> frozenset[str]:
    result = subprocess.run(
        ["bd", "show", *REQUIRED_GATES, "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"cannot query integrity gates: {result.stderr.strip()}")
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"integrity gate query returned invalid JSON: {exc}") from exc
    if not isinstance(issues, list):
        raise ValueError("integrity gate query did not return a list")
    return frozenset(
        issue.get("id")
        for issue in issues
        if isinstance(issue, dict) and issue.get("status") == "closed"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    study_dir = REPO_ROOT / "configs" / "studies" / "rryas_pilot_v1"
    parser.add_argument("--spec", type=Path, default=study_dir / "study_spec.json")
    parser.add_argument(
        "--manifest", type=Path, default=study_dir / "pilot_manifest.json"
    )
    parser.add_argument(
        "--curated-manifest",
        type=Path,
        default=REPO_ROOT / "results" / "rryas_dataset" / "candidate_manifest.json",
    )
    args = parser.parse_args(argv)
    evidence = validate_pilot(
        spec_path=args.spec.resolve(),
        manifest_path=args.manifest.resolve(),
        curated_manifest_path=args.curated_manifest.resolve(),
        repo_root=REPO_ROOT,
        closed_gates=_closed_gate_ids(),
    )
    print(json.dumps(asdict(evidence), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
