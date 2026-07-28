#!/usr/bin/env python3
"""Build the contamination-clean, no-spend rryas headline v2 capsule."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (
    REPO_ROOT / "lib",
    REPO_ROOT / "scripts" / "infra",
    REPO_ROOT / "scripts" / "orchestration",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from eb_study import StudySpec, file_hash  # noqa: E402
from headline_study_preflight import (  # noqa: E402
    CANDIDATE_LOCK_REVISION,
    REQUIRED_CACHE_ISOLATION,
    REQUIRED_EVIDENCE_POLICY,
    REQUIRED_EXECUTION_BASE,
    REQUIRED_JUDGE,
    REQUIRED_ORDER_POLICY,
    REQUIRED_SELECTION_RULE,
    HeadlineEvidence,
    V2_ADDITIONAL_EXPOSURES,
    V2_PROTOCOL,
    compile_execution_order,
    required_analysis_plan,
)
from code_finder_interface_pilot_preflight import (  # noqa: E402
    _default_provenance_provider,
)

V1_STUDY_ID = "rryas-headline-v1"
V1_CONFIG_DIR = Path("configs/studies") / V1_STUDY_ID
V1_RECEIPTS = Path("results/studies") / V1_STUDY_ID / "receipts.jsonl"
V2_CONFIG_DIR = Path("configs/studies") / V2_PROTOCOL.study_id
CANDIDATE_MANIFEST = Path("results/rryas_dataset/candidate_manifest.json")


@dataclass(frozen=True)
class CorePayloads:
    analysis_plan: Mapping[str, Any]
    manifest: Mapping[str, Any]
    spec: Mapping[str, Any]
    preflight_evidence: Mapping[str, Any]
    dispatch_plan: Mapping[str, Any]
    canary: Mapping[str, Any]


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2) + "\n").encode()


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return f"sha256:{hashlib.sha256(_json_bytes(payload)).hexdigest()}"


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _sample_costs(receipts_path: Path) -> tuple[float, ...]:
    costs: list[float] = []
    for line_number, line in enumerate(receipts_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        receipt = json.loads(line)
        usage = receipt.get("usage")
        isolation = receipt.get("tool_use", {}).get("cache_isolation")
        cost = usage.get("cost_usd") if isinstance(usage, dict) else None
        if (
            not isinstance(cost, (int, float))
            or isinstance(cost, bool)
            or not isinstance(isolation, dict)
            or isolation.get("valid") is not True
            or isolation.get("cross_run_cache_read_tokens") != 0
            or isolation.get("cache_write_tokens") != 0
        ):
            raise ValueError(
                f"{receipts_path}:{line_number} lacks cache-isolated outer cost"
            )
        costs.append(float(cost))
    if not costs:
        raise ValueError(f"{receipts_path} contains no cost evidence")
    return tuple(costs)


def _selected_tasks(
    v1_manifest: Mapping[str, Any],
    candidate_manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    v1_tasks = v1_manifest.get("tasks")
    candidate_ids = candidate_manifest.get("task_ids")
    if not isinstance(v1_tasks, list) or not isinstance(candidate_ids, list):
        raise ValueError("v1 tasks and candidate IDs must be lists")
    selected = [
        deepcopy(task)
        for task in v1_tasks
        if task.get("candidate_id") not in V2_ADDITIONAL_EXPOSURES
    ]
    expected_ids = [
        candidate_id
        for candidate_id in candidate_ids
        if candidate_id not in V2_PROTOCOL.post_lock_exposures
    ]
    actual_ids = [task.get("candidate_id") for task in selected]
    if actual_ids != expected_ids or len(selected) != V2_PROTOCOL.task_count:
        raise ValueError("v2 selection is not candidate order minus all exposures")
    return selected


def _cost_forecast(repo_root: Path) -> dict[str, Any]:
    receipts_path = repo_root / V1_RECEIPTS
    costs = _sample_costs(receipts_path)
    total = sum(costs)
    mean = total / len(costs)
    maximum = max(costs)
    return {
        "basis": (
            "All seven immutable rryas-headline-v1 attempts, including the "
            "terminal invalid attempt, with provider-native outer-agent cost "
            "and zero cache reads/writes."
        ),
        "sample_receipts": [
            {
                "path": str(V1_RECEIPTS),
                "sha256": file_hash(receipts_path),
            }
        ],
        "sample_attempts": len(costs),
        "sample_outer_spend_usd": round(total, 6),
        "mean_per_slot_usd": round(mean, 9),
        "forecast_outer_spend_usd": round(mean * V2_PROTOCOL.slot_count, 6),
        "max_observed_per_slot_usd": round(maximum, 6),
        "empirical_slot_count_envelope_usd": round(maximum * V2_PROTOCOL.slot_count, 6),
        "authorization_outer_spend_ceiling_usd": 1100.0,
        "uncovered_costs": [
            "Sourcegraph MCP and CLI backend cost is not reported by the endpoint",
            "Claude judge-account usage is not included in the agent modelUsage receipt",
            "local Docker compute is not priced",
        ],
    }


def _task_provenances(
    repo_root: Path, tasks: Sequence[Mapping[str, Any]]
) -> tuple[tuple[Any, ...], str]:
    provider = _default_provenance_provider(repo_root)
    provenances = tuple(provider(repo_root / str(task["task_toml"])) for task in tasks)
    harness_hashes = {provenance.harness_hash for provenance in provenances}
    if len(harness_hashes) != 1:
        raise ValueError("v2 tasks do not share one current harness hash")
    for task, provenance in zip(tasks, provenances):
        if task.get("task_hash") != provenance.task_hash:
            raise ValueError(f"task hash drifted for {task.get('task_id')}")
    return provenances, next(iter(harness_hashes))


def _selection_payload() -> dict[str, Any]:
    return {
        "rule": REQUIRED_SELECTION_RULE,
        "candidate_outcomes_inspected": False,
        "candidate_count": 48,
        "selected_count": V2_PROTOCOL.task_count,
        "post_lock_exposures": [
            {
                "candidate_id": candidate_id,
                "reason": "post_lock_agent_output",
                "evidence": list(V2_PROTOCOL.post_lock_exposure_evidence[candidate_id]),
            }
            for candidate_id in V2_PROTOCOL.post_lock_exposures
        ],
    }


def _execution_configuration(
    tasks: Sequence[Mapping[str, Any]], output_root: str
) -> dict[str, Any]:
    return {
        **REQUIRED_EXECUTION_BASE,
        "output_root": output_root,
        "receipts": f"{output_root}/receipts.jsonl",
        "order_policy": REQUIRED_ORDER_POLICY,
        "execution_order": [
            dict(row)
            for row in compile_execution_order(tasks, study_id=V2_PROTOCOL.study_id)
        ],
    }


def _manifest_payload(
    *,
    v1_manifest: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
    analysis: Mapping[str, Any],
    candidate_path: Path,
    provenances: Sequence[Any],
    harness_hash: str,
) -> dict[str, Any]:
    output_root = f"results/studies/{V2_PROTOCOL.study_id}"
    manifest = deepcopy(v1_manifest)
    manifest.update(
        {
            "study_id": V2_PROTOCOL.study_id,
            "purpose": (
                "Confirmatory Claude Sonnet 5 protocol comparison on every "
                "candidate untouched by the aborted v1 operational run."
            ),
            "candidate_manifest": str(CANDIDATE_MANIFEST),
            "candidate_manifest_hash": file_hash(candidate_path),
            "candidate_lock_revision": CANDIDATE_LOCK_REVISION,
            "analysis_plan": str(V2_CONFIG_DIR / "analysis_plan.json"),
            "analysis_plan_hash": _payload_hash(analysis),
            "selection": _selection_payload(),
            "tasks": list(tasks),
            "arms": dict(V2_PROTOCOL.arm_descriptions),
            "cache_isolation": REQUIRED_CACHE_ISOLATION,
            "judge_configuration": REQUIRED_JUDGE,
            "execution_configuration": _execution_configuration(tasks, output_root),
            "spend_guard": {
                "slots": V2_PROTOCOL.slot_count,
                "max_attempts_per_slot": 1,
                "paid_dispatch_requires_new_explicit_authorization": True,
                "paid_dispatch_authorized": False,
                "forecast_reported_outer_spend_usd": None,
                "forecast_basis": V2_PROTOCOL.forecast_basis,
            },
            "evidence_policy": REQUIRED_EVIDENCE_POLICY,
            "harness_hash": harness_hash,
            "verifier_hashes": {
                str(task["task_id"]): provenance.verifier_hash
                for task, provenance in zip(tasks, provenances)
            },
        }
    )
    return manifest


def _study_spec_payload(
    tasks: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    *,
    harness_hash: str,
    revision: str,
) -> dict[str, Any]:
    return {
        "study_id": V2_PROTOCOL.study_id,
        "schema_version": 1,
        "task_manifest_hash": _payload_hash(manifest),
        "task_ids": [task["task_id"] for task in tasks],
        "arms": [
            {"name": name, "capability_fingerprint": fingerprint}
            for name, fingerprint in V2_PROTOCOL.arms
        ],
        "baseline_arm": "baseline",
        "repetitions": 1,
        "attempt_policy": "first_valid_attempt",
        "max_attempts": 1,
        "model": "claude-sonnet-5",
        "harness": harness_hash,
        "revision": revision,
        "token_source": "sdk_model_usage",
        "score_contract": "weighted-mean-v2",
        "promotion_policy": "paired-valid-complete-arms",
    }


def _preflight_payload(
    tasks: Sequence[Mapping[str, Any]],
    *,
    study_spec: StudySpec,
    analysis: Mapping[str, Any],
    revision: str,
) -> dict[str, Any]:
    task_ids = tuple(str(task["task_id"]) for task in tasks)
    task_types = tuple(str(task["task_type"]) for task in tasks)
    return asdict(
        HeadlineEvidence(
            study_id=V2_PROTOCOL.study_id,
            spec_hash=study_spec.spec_hash,
            task_manifest_hash=study_spec.task_manifest_hash,
            analysis_plan_hash=_payload_hash(analysis),
            candidate_ids=tuple(str(task["candidate_id"]) for task in tasks),
            task_ids=task_ids,
            slots=tuple(
                (task_id, arm, 1)
                for task_id in task_ids
                for arm, _fingerprint in V2_PROTOCOL.arms
            ),
            revision=revision,
            mirror_repositories=tuple(
                str(repository)
                for task in tasks
                for repository in task["expected_repositories"]
            ),
            output_root=f"results/studies/{V2_PROTOCOL.study_id}",
            type_counts=tuple(
                (task_type, task_types.count(task_type))
                for task_type in sorted(set(task_types))
            ),
            paid_dispatch_authorized=False,
        )
    )


def _dispatch_plan_payload(
    repo_root: Path,
    *,
    spec: Mapping[str, Any],
    study_spec: StudySpec,
    manifest: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "study_id": V2_PROTOCOL.study_id,
        "status": "LOCKED-NO-SPEND",
        "study_spec": str(V2_CONFIG_DIR / "study_spec.json"),
        "study_spec_file_hash": _payload_hash(spec),
        "study_spec_hash": study_spec.spec_hash,
        "final_manifest": str(V2_CONFIG_DIR / "final_manifest.json"),
        "final_manifest_hash": _payload_hash(manifest),
        "preflight_evidence": str(V2_CONFIG_DIR / "preflight_evidence.json"),
        "preflight_evidence_hash": _payload_hash(evidence),
        "cost_forecast": _cost_forecast(repo_root),
        "authorization": {
            "paid_dispatch_authorized": False,
            "authorization_reference": None,
        },
    }


def _canary_payload(*, harness_hash: str, revision: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "canary_id": "rryas-headline-v2-cli-compliance-canary",
        "status": "LOCKED-NO-SPEND",
        "purpose": "Validate strengthened CLI treatment compliance, not reward.",
        "task_id": "api-contract-dual-envoy-istio-001",
        "candidate_id": "api-contract-dual-envoy-istio-001",
        "task_toml": (
            "benchmarks/dependency_management/"
            "api-contract-dual-envoy-istio-001/task.toml"
        ),
        "mode": "cli",
        "harness": "claude",
        "model": "claude-sonnet-5",
        "agent_account": 3,
        "judge_account": 1,
        "max_attempts": 1,
        "harness_hash": harness_hash,
        "revision": revision,
        "output_root": "results/studies/rryas-headline-v2-cli-compliance-canary",
        "success_criterion": "sgx_tool_calls > 0",
        "analysis_use": "operational compliance evidence only",
        "paid_dispatch_authorized": False,
        "authorization_reference": None,
    }


def build_core_payloads(repo_root: Path, *, revision: str) -> CorePayloads:
    """Derive every v2 artifact without writing to disk or launching a model."""

    repo_root = repo_root.resolve()
    v1_manifest = _load_object(repo_root / V1_CONFIG_DIR / "final_manifest.json")
    candidate_path = repo_root / CANDIDATE_MANIFEST
    candidate_manifest = _load_object(candidate_path)
    tasks = _selected_tasks(v1_manifest, candidate_manifest)
    analysis = required_analysis_plan(V2_PROTOCOL)
    provenances, harness_hash = _task_provenances(repo_root, tasks)
    manifest = _manifest_payload(
        v1_manifest=v1_manifest,
        tasks=tasks,
        analysis=analysis,
        candidate_path=candidate_path,
        provenances=provenances,
        harness_hash=harness_hash,
    )
    spec = _study_spec_payload(
        tasks, manifest, harness_hash=harness_hash, revision=revision
    )
    study_spec = StudySpec.from_json(spec)
    evidence = _preflight_payload(
        tasks, study_spec=study_spec, analysis=analysis, revision=revision
    )
    dispatch_plan = _dispatch_plan_payload(
        repo_root,
        spec=spec,
        study_spec=study_spec,
        manifest=manifest,
        evidence=evidence,
    )
    canary = _canary_payload(harness_hash=harness_hash, revision=revision)
    return CorePayloads(
        analysis_plan=analysis,
        manifest=manifest,
        spec=spec,
        preflight_evidence=evidence,
        dispatch_plan=dispatch_plan,
        canary=canary,
    )


def _artifact_payloads(build: CorePayloads) -> dict[str, Mapping[str, Any]]:
    return {
        "analysis_plan.json": build.analysis_plan,
        "final_manifest.json": build.manifest,
        "study_spec.json": build.spec,
        "preflight_evidence.json": build.preflight_evidence,
        "dispatch_plan.json": build.dispatch_plan,
        "cli_compliance_canary.json": build.canary,
    }


def write_capsule(
    repo_root: Path,
    build: CorePayloads,
    *,
    check: bool,
) -> None:
    output_dir = repo_root / V2_CONFIG_DIR
    artifacts = _artifact_payloads(build)
    if check:
        for name, payload in artifacts.items():
            path = output_dir / name
            if not path.is_file() or path.read_bytes() != _json_bytes(payload):
                raise ValueError(f"generated v2 artifact is stale: {path}")
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in artifacts.items():
        (output_dir / name).write_bytes(_json_bytes(payload))


def _git_revision(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def configured_revision(repo_root: Path) -> str:
    """Return the immutable revision recorded by the frozen v2 capsule."""

    spec = _load_object(repo_root / V2_CONFIG_DIR / "study_spec.json")
    revision = spec.get("revision")
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("frozen v2 study spec has no full git revision")
    return revision


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed v2 artifacts differ; do not write files.",
    )
    args = parser.parse_args(argv)
    revision = (
        configured_revision(REPO_ROOT) if args.check else _git_revision(REPO_ROOT)
    )
    build = build_core_payloads(REPO_ROOT, revision=revision)
    write_capsule(REPO_ROOT, build, check=args.check)
    print(
        json.dumps(
            {
                "study_id": V2_PROTOCOL.study_id,
                "tasks": len(build.manifest["tasks"]),
                "slots": len(
                    build.manifest["execution_configuration"]["execution_order"]
                ),
                "harness_hash": build.manifest["harness_hash"],
                "spec_hash": StudySpec.from_json(build.spec).spec_hash,
                "paid_dispatch_authorized": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
