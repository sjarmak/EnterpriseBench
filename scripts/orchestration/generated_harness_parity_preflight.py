#!/usr/bin/env python3
"""Fail-closed, no-inference validation for generated-harness Finder parity."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (
    REPO_ROOT,
    REPO_ROOT / "lib",
    REPO_ROOT / "scripts" / "infra",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from agents.harnesses.registry import (  # noqa: E402
    CODEX_NPM_PACKAGE,
    OPENCODE_NPM_PACKAGE,
    build_harness_plan,
)
from code_finder_interface_pilot_preflight import (  # noqa: E402
    REQUIRED_ARMS,
    REQUIRED_CACHE_ISOLATION,
    REQUIRED_JUDGE,
    REQUIRED_TREATMENT_CONTRACT,
    MirrorProbe,
    ProvenanceProvider,
    RevisionValidator,
    _default_mirror_probe,
    _default_provenance_provider,
    _git_revision_matches,
    _load_object,
)
from code_finder_interface_supplement_preflight import (  # noqa: E402
    REPORT_PATH,
    TASK_ID,
    _load_supplement_task,
)
from eb_study import StudySpec, file_hash  # noqa: E402
from study_run import harness_input_paths  # noqa: E402

CAPSULE_ID = "rryas-generated-harness-finder-parity-v1"
CODEX_STUDY_ID = "rryas-codex-finder-parity-v1"
OPENCODE_STUDY_ID = "rryas-opencode-kimi-k3-finder-parity-v1"
REQUIRED_PROMOTION_POLICY = "descriptive-generated-harness-parity-no-promotion"
REQUIRED_COMPARISON_POLICY = {
    "comparison_unit": "harness-model bundle",
    "within_bundle": "paired MCP Code Finder minus CLI Code Finder",
    "cross_bundle": (
        "descriptive only because harness and model identity jointly vary"
    ),
    "claude_reference": (
        "reuse only valid corrected-v2 Claude/Sonnet receipts as historical context"
    ),
    "inference": "none",
}
REQUIRED_SLOTS = (
    ("codex", TASK_ID, "mcp_code_finder", 1, 1),
    ("codex", TASK_ID, "cli_code_finder", 1, 1),
    ("opencode", TASK_ID, "mcp_code_finder", 1, 1),
    ("opencode", TASK_ID, "cli_code_finder", 1, 1),
)
REQUIRED_EXECUTION = {
    "timeout_seconds": 600,
    "build_timeout_seconds": 1800,
    "verifier_timeout_seconds": 600,
    "memory_mb": 8192,
    "no_build": True,
    "repetitions": 1,
    "max_attempts": 1,
    "execution_order": [list(slot) for slot in REQUIRED_SLOTS],
}
REQUIRED_SPEND_GUARD = {
    "slots": 4,
    "max_attempts_per_slot": 1,
    "paid_dispatch_requires_new_explicit_authorization": True,
    "paid_dispatch_authorized": False,
    "reported_outer_spend_forecast_usd": None,
    "forecast_basis": (
        "no immutable generated-harness receipts; report provider-native cost "
        "without imputation"
    ),
    "inner_finder_cost": "unavailable",
}
REQUIRED_BUNDLES = (
    ("codex", CODEX_STUDY_ID, "gpt-5.6-sol", CODEX_NPM_PACKAGE),
    (
        "opencode",
        OPENCODE_STUDY_ID,
        "openrouter/moonshotai/kimi-k3",
        OPENCODE_NPM_PACKAGE,
    ),
)
REQUIRED_SPEC_FIELDS = {
    "task_ids": (TASK_ID,),
    "baseline_arm": "mcp_code_finder",
    "repetitions": 1,
    "attempt_policy": "first_valid_attempt",
    "max_attempts": 1,
    "token_source": "provider_native_usage",
    "score_contract": "weighted-mean-v2",
    "promotion_policy": REQUIRED_PROMOTION_POLICY,
}

AuthProbe = Callable[[str], bool]


@dataclass(frozen=True)
class GeneratedHarnessParityEvidence:
    """The exact four no-retry slots admitted by the no-spend preflight."""

    capsule_id: str
    spec_hashes: tuple[tuple[str, str], ...]
    task_manifest_hash: str
    task_ids: tuple[str, ...]
    slots: tuple[tuple[str, str, str, int, int], ...]
    revision: str
    models: tuple[tuple[str, str], ...]
    mirror_repositories: tuple[str, ...]
    output_roots: tuple[str, ...]
    graded_artifact_path: str
    comparison_label: str
    paid_dispatch_authorized: bool


def _repo_path(repo_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty repository-relative path")
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"{label} must be repository-relative")
    resolved = (repo_root / relative).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc
    return resolved


def _validate_manifest_contracts(manifest: dict[str, Any]) -> None:
    expected = (
        ("treatment contract", "treatment_contract", REQUIRED_TREATMENT_CONTRACT),
        ("cache isolation", "cache_isolation", REQUIRED_CACHE_ISOLATION),
        ("judge configuration", "judge_configuration", REQUIRED_JUDGE),
        ("execution configuration", "execution_configuration", REQUIRED_EXECUTION),
        ("comparison policy", "comparison_policy", REQUIRED_COMPARISON_POLICY),
        ("spend guard", "spend_guard", REQUIRED_SPEND_GUARD),
    )
    for label, field, required in expected:
        if manifest.get(field) != required:
            raise ValueError(f"generated-harness {label} is not locked")


def _validate_spec(
    spec: StudySpec,
    *,
    label: str,
    study_id: str,
    model: str,
    manifest_hash: str,
) -> None:
    actual_arms = tuple((arm.name, arm.capability_fingerprint) for arm in spec.arms)
    actual_fields = {field: getattr(spec, field) for field in REQUIRED_SPEC_FIELDS}
    if (
        spec.study_id != study_id
        or spec.model != model
        or spec.task_manifest_hash != manifest_hash
        or actual_arms != REQUIRED_ARMS
        or actual_fields != REQUIRED_SPEC_FIELDS
        or spec.slots()
        != (
            (TASK_ID, "mcp_code_finder", 1),
            (TASK_ID, "cli_code_finder", 1),
        )
    ):
        raise ValueError(f"{label} study contract does not match the locked capsule")


def _validate_bundles(
    manifest: dict[str, Any],
    *,
    spec_paths: tuple[Path, Path],
    repo_root: Path,
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    bundles = manifest.get("bundles")
    if not isinstance(bundles, list) or len(bundles) != len(REQUIRED_BUNDLES):
        raise ValueError("generated-harness capsule must declare exactly two bundles")

    output_roots: list[str] = []
    models: list[tuple[str, str]] = []
    for bundle, required, spec_path in zip(bundles, REQUIRED_BUNDLES, spec_paths):
        harness, study_id, model, npm_package = required
        if (
            not isinstance(bundle, dict)
            or bundle.get("harness") != harness
            or bundle.get("study_id") != study_id
            or bundle.get("model") != model
            or _repo_path(repo_root, bundle.get("study_spec"), "study_spec")
            != spec_path.resolve()
        ):
            raise ValueError(f"{harness} bundle identity is not locked")

        output_root = _repo_path(
            repo_root, bundle.get("output_root"), f"{harness} output_root"
        )
        receipts = _repo_path(repo_root, bundle.get("receipts"), f"{harness} receipts")
        if receipts.parent != output_root or receipts.name != "receipts.jsonl":
            raise ValueError(f"{harness} receipts must live in its output root")
        if output_root.exists() and any(output_root.iterdir()):
            raise ValueError(f"{harness} output root is not clean: {output_root}")

        for mode in ("mcp_code_finder", "cli_code_finder"):
            plan = build_harness_plan(harness, model=model, mode=mode)
            if plan.npm_package != npm_package:
                raise ValueError(f"{harness} package pin drifted")
        output_roots.append(str(output_root.relative_to(repo_root)))
        models.append((harness, model))

    if len(set(output_roots)) != len(output_roots):
        raise ValueError("generated-harness output roots must be unique")
    return tuple(output_roots), tuple(models)


def _default_auth_probe(credential: str) -> bool:
    if credential == "openrouter":
        return bool(os.environ.get("OPENROUTER_API_KEY"))
    executable = "codex" if credential == "codex" else "claude-1"
    if shutil.which(executable) is None:
        return False
    command = (
        [executable, "login", "status"]
        if credential == "codex"
        else [executable, "--version"]
    )
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0


def _validate_auth(auth_probe: AuthProbe) -> None:
    labels = {
        "codex": "Codex authentication",
        "openrouter": "OpenRouter authentication",
        "judge": "Claude judge authentication",
    }
    for credential, label in labels.items():
        if not auth_probe(credential):
            raise ValueError(f"{label} is unavailable")


def validate_generated_harness_parity(
    *,
    manifest_path: Path,
    codex_spec_path: Path,
    opencode_spec_path: Path,
    repo_root: Path,
    revision_validator: RevisionValidator | None = None,
    provenance_provider: ProvenanceProvider | None = None,
    mirror_probe: MirrorProbe | None = None,
    auth_probe: AuthProbe | None = None,
) -> GeneratedHarnessParityEvidence:
    """Validate the four-slot capsule without launching an agent or judge."""

    repo_root = repo_root.resolve()
    manifest = _load_object(manifest_path, "generated-harness parity manifest")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("status") != "locked-no-spend-capsule"
        or manifest.get("capsule_id") != CAPSULE_ID
    ):
        raise ValueError("generated-harness capsule identity/status is not locked")
    _validate_manifest_contracts(manifest)

    codex_spec = StudySpec.load(codex_spec_path)
    opencode_spec = StudySpec.load(opencode_spec_path)
    manifest_hash = file_hash(manifest_path)
    _validate_spec(
        codex_spec,
        label="Codex",
        study_id=CODEX_STUDY_ID,
        model="gpt-5.6-sol",
        manifest_hash=manifest_hash,
    )
    _validate_spec(
        opencode_spec,
        label="OpenCode",
        study_id=OPENCODE_STUDY_ID,
        model="openrouter/moonshotai/kimi-k3",
        manifest_hash=manifest_hash,
    )
    if codex_spec.revision != opencode_spec.revision:
        raise ValueError("generated-harness studies must freeze the same revision")

    task_toml, task_dir, mirrors = _load_supplement_task(
        manifest,
        {"task_ids": [TASK_ID]},
        repo_root,
        mirror_probe or _default_mirror_probe,
    )
    provider = provenance_provider or _default_provenance_provider(repo_root)
    provenance = provider(task_toml)
    task_entry = manifest["tasks"][0]
    if provenance.task_hash != task_entry.get("task_hash"):
        raise ValueError("captured task hash does not match parity manifest")
    if (
        provenance.harness_hash != manifest.get("harness_hash")
        or codex_spec.harness != provenance.harness_hash
        or opencode_spec.harness != provenance.harness_hash
    ):
        raise ValueError("generated-harness hash does not match current harness")
    if manifest.get("verifier_hashes") != {TASK_ID: provenance.verifier_hash}:
        raise ValueError("parity verifier hash does not match current verifier")

    validator = revision_validator or (
        lambda revision, paths: _git_revision_matches(
            revision, paths, repo_root=repo_root
        )
    )
    if not validator(codex_spec.revision, (*harness_input_paths(repo_root), task_dir)):
        raise ValueError(
            f"revision {codex_spec.revision!r} does not match current critical inputs"
        )
    output_roots, models = _validate_bundles(
        manifest,
        spec_paths=(codex_spec_path, opencode_spec_path),
        repo_root=repo_root,
    )
    _validate_auth(auth_probe or _default_auth_probe)

    return GeneratedHarnessParityEvidence(
        capsule_id=CAPSULE_ID,
        spec_hashes=(
            (CODEX_STUDY_ID, codex_spec.spec_hash),
            (OPENCODE_STUDY_ID, opencode_spec.spec_hash),
        ),
        task_manifest_hash=manifest_hash,
        task_ids=(TASK_ID,),
        slots=REQUIRED_SLOTS,
        revision=codex_spec.revision,
        models=models,
        mirror_repositories=mirrors,
        output_roots=output_roots,
        graded_artifact_path=REPORT_PATH,
        comparison_label="harness-model bundles; descriptive only",
        paid_dispatch_authorized=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--codex-spec", type=Path, required=True)
    parser.add_argument("--opencode-spec", type=Path, required=True)
    args = parser.parse_args(argv)
    evidence = validate_generated_harness_parity(
        manifest_path=args.manifest,
        codex_spec_path=args.codex_spec,
        opencode_spec_path=args.opencode_spec,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(asdict(evidence), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
