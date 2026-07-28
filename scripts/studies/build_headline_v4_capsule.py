#!/usr/bin/env python3
"""Build the judge-isolated, no-spend rryas headline v4 capsule."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
for import_path in (
    REPO_ROOT / "lib",
    REPO_ROOT / "scripts" / "infra",
    REPO_ROOT / "scripts" / "orchestration",
    REPO_ROOT / "scripts" / "studies",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from build_headline_v3_capsule import (  # noqa: E402
    CANDIDATE_MANIFEST,
    SOURCE_CONFIG_DIR,
    CorePayloads,
    _json_bytes,
    _load_object,
    _payload_hash,
    _sample_costs,
    _task_provenances,
)
from eb_study import StudySpec, file_hash  # noqa: E402
from headline_protocol import (  # noqa: E402
    CANDIDATE_LOCK_REVISION,
    HEADLINE_BATCH_POLICIES,
    REQUIRED_CACHE_ISOLATION,
    REQUIRED_EVIDENCE_POLICY,
    REQUIRED_EXECUTION_BASE,
    REQUIRED_ORDER_POLICY,
    REQUIRED_SELECTION_RULE,
    V4_PROTOCOL,
    V4_REQUIRED_JUDGE,
    required_analysis_plan,
)
from headline_study_preflight import (  # noqa: E402
    HeadlineEvidence,
    compile_execution_order,
)

V4_CONFIG_DIR = Path("configs/studies") / V4_PROTOCOL.study_id
COST_RECEIPTS = (
    Path("results/studies/rryas-headline-v1/receipts.jsonl"),
    Path("results/studies/rryas-headline-v2/receipts.jsonl"),
    Path("results/studies/rryas-headline-v3/receipts.jsonl"),
)
AUTHORIZATION_CEILING_USD = 990.0


def _selected_tasks(
    source_manifest: Mapping[str, Any],
    candidate_manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    source_tasks = source_manifest.get("tasks")
    candidate_ids = candidate_manifest.get("task_ids")
    if not isinstance(source_tasks, list) or not isinstance(candidate_ids, list):
        raise ValueError("source tasks and candidate IDs must be lists")
    selected = [
        deepcopy(task)
        for task in source_tasks
        if task.get("candidate_id") not in V4_PROTOCOL.post_lock_exposures
    ]
    expected_ids = [
        candidate_id
        for candidate_id in candidate_ids
        if candidate_id not in V4_PROTOCOL.post_lock_exposures
    ]
    actual_ids = [task.get("candidate_id") for task in selected]
    if actual_ids != expected_ids or len(selected) != V4_PROTOCOL.task_count:
        raise ValueError("v4 selection is not candidate order minus every exposure")
    return selected


def _cost_forecast(repo_root: Path) -> dict[str, Any]:
    samples = tuple(
        (path, _sample_costs(repo_root / path)) for path in COST_RECEIPTS
    )
    costs = tuple(cost for _path, values in samples for cost in values)
    total = sum(costs)
    mean = total / len(costs)
    maximum = max(costs)
    empirical_envelope = maximum * V4_PROTOCOL.slot_count
    policy = HEADLINE_BATCH_POLICIES[V4_PROTOCOL.study_id]
    hard_cap_envelope = (
        policy["outer_spend_hard_cap_per_slot_usd"] * V4_PROTOCOL.slot_count
    )
    if AUTHORIZATION_CEILING_USD < max(empirical_envelope, hard_cap_envelope):
        raise ValueError("v4 authorization ceiling is below a required envelope")
    return {
        "basis": (
            "All immutable v1, v2, and v3 attempts, including terminal invalid "
            "attempts, with provider-native outer-agent cost and zero cache "
            "reads/writes."
        ),
        "sample_receipts": [
            {"path": str(path), "sha256": file_hash(repo_root / path)}
            for path, _values in samples
        ],
        "sample_attempts": len(costs),
        "sample_outer_spend_usd": round(total, 6),
        "mean_per_slot_usd": round(mean, 9),
        "forecast_outer_spend_usd": round(mean * V4_PROTOCOL.slot_count, 6),
        "max_observed_per_slot_usd": round(maximum, 6),
        "empirical_slot_count_envelope_usd": round(empirical_envelope, 6),
        "authorization_outer_spend_ceiling_usd": AUTHORIZATION_CEILING_USD,
        "uncovered_costs": [
            "Sourcegraph MCP and CLI backend cost is not reported by the endpoint",
            "Claude judge-account usage is not included in the agent modelUsage receipt",
            "local Docker compute is not priced",
        ],
    }


def _selection_payload() -> dict[str, Any]:
    return {
        "rule": REQUIRED_SELECTION_RULE,
        "candidate_outcomes_inspected": False,
        "candidate_count": 48,
        "selected_count": V4_PROTOCOL.task_count,
        "post_lock_exposures": [
            {
                "candidate_id": candidate_id,
                "reason": "post_lock_agent_output",
                "evidence": list(
                    V4_PROTOCOL.post_lock_exposure_evidence[candidate_id]
                ),
            }
            for candidate_id in V4_PROTOCOL.post_lock_exposures
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
            for row in compile_execution_order(tasks, study_id=V4_PROTOCOL.study_id)
        ],
    }


def build_core_payloads(repo_root: Path, *, revision: str) -> CorePayloads:
    """Derive every v4 artifact without writing or launching a model."""

    repo_root = repo_root.resolve()
    source_manifest = _load_object(
        repo_root / SOURCE_CONFIG_DIR / "final_manifest.json"
    )
    candidate_path = repo_root / CANDIDATE_MANIFEST
    tasks = _selected_tasks(source_manifest, _load_object(candidate_path))
    analysis = required_analysis_plan(V4_PROTOCOL)
    provenances, harness_hash = _task_provenances(repo_root, tasks)
    output_root = f"results/studies/{V4_PROTOCOL.study_id}"
    manifest = deepcopy(source_manifest)
    manifest.update(
        {
            "study_id": V4_PROTOCOL.study_id,
            "purpose": (
                "Confirmatory Claude Sonnet 5 protocol comparison on every "
                "candidate untouched by the v1-v3 operational runs, with an "
                "isolated no-tool judge process."
            ),
            "candidate_manifest": str(CANDIDATE_MANIFEST),
            "candidate_manifest_hash": file_hash(candidate_path),
            "candidate_lock_revision": CANDIDATE_LOCK_REVISION,
            "analysis_plan": str(V4_CONFIG_DIR / "analysis_plan.json"),
            "analysis_plan_hash": _payload_hash(analysis),
            "selection": _selection_payload(),
            "tasks": tasks,
            "arms": dict(V4_PROTOCOL.arm_descriptions),
            "cache_isolation": REQUIRED_CACHE_ISOLATION,
            "judge_configuration": V4_REQUIRED_JUDGE,
            "execution_configuration": _execution_configuration(tasks, output_root),
            "spend_guard": {
                "slots": V4_PROTOCOL.slot_count,
                "max_attempts_per_slot": 1,
                "paid_dispatch_requires_new_explicit_authorization": True,
                "paid_dispatch_authorized": False,
                "forecast_reported_outer_spend_usd": None,
                "forecast_basis": V4_PROTOCOL.forecast_basis,
            },
            "evidence_policy": REQUIRED_EVIDENCE_POLICY,
            "harness_hash": harness_hash,
            "verifier_hashes": {
                str(task["task_id"]): provenance.verifier_hash
                for task, provenance in zip(tasks, provenances)
            },
        }
    )
    spec = {
        "study_id": V4_PROTOCOL.study_id,
        "schema_version": 1,
        "task_manifest_hash": _payload_hash(manifest),
        "task_ids": [task["task_id"] for task in tasks],
        "arms": [
            {"name": name, "capability_fingerprint": fingerprint}
            for name, fingerprint in V4_PROTOCOL.arms
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
    study_spec = StudySpec.from_json(spec)
    task_ids = tuple(str(task["task_id"]) for task in tasks)
    task_types = tuple(str(task["task_type"]) for task in tasks)
    evidence = asdict(
        HeadlineEvidence(
            study_id=V4_PROTOCOL.study_id,
            spec_hash=study_spec.spec_hash,
            task_manifest_hash=study_spec.task_manifest_hash,
            analysis_plan_hash=_payload_hash(analysis),
            candidate_ids=tuple(str(task["candidate_id"]) for task in tasks),
            task_ids=task_ids,
            slots=tuple(
                (task_id, arm, 1)
                for task_id in task_ids
                for arm, _fingerprint in V4_PROTOCOL.arms
            ),
            revision=revision,
            mirror_repositories=tuple(
                str(repository)
                for task in tasks
                for repository in task["expected_repositories"]
            ),
            output_root=output_root,
            type_counts=tuple(
                (task_type, task_types.count(task_type))
                for task_type in sorted(set(task_types))
            ),
            paid_dispatch_authorized=False,
        )
    )
    policy = HEADLINE_BATCH_POLICIES[V4_PROTOCOL.study_id]
    dispatch_plan = {
        "schema_version": 1,
        "study_id": V4_PROTOCOL.study_id,
        "status": "LOCKED-NO-SPEND",
        "study_spec": str(V4_CONFIG_DIR / "study_spec.json"),
        "study_spec_file_hash": _payload_hash(spec),
        "study_spec_hash": study_spec.spec_hash,
        "final_manifest": str(V4_CONFIG_DIR / "final_manifest.json"),
        "final_manifest_hash": _payload_hash(manifest),
        "preflight_evidence": str(V4_CONFIG_DIR / "preflight_evidence.json"),
        "preflight_evidence_hash": _payload_hash(evidence),
        "cost_forecast": _cost_forecast(repo_root),
        "batch_policy": {
            "max_slots_per_dispatch": policy["max_slots_per_dispatch"],
            "complete_task_triplets": True,
            "score_independent_boundaries": True,
            "agent_max_budget_usd_per_slot": (
                policy["agent_max_budget_usd_per_slot"]
            ),
            "judge_max_budget_usd_per_call": (
                policy["judge_max_budget_usd_per_call"]
            ),
            "max_judge_calls_per_slot": policy["max_judge_calls_per_slot"],
            "max_judge_attempts_per_call": (
                policy["max_judge_attempts_per_call"]
            ),
            "outer_spend_hard_cap_per_slot_usd": (
                policy["outer_spend_hard_cap_per_slot_usd"]
            ),
        },
        "provider_capacity": {
            "confirmed": False,
            "capacity_reference": None,
            "confirmed_completed_prefix": None,
            "confirmed_max_slots": None,
        },
        "authorization": {
            "paid_dispatch_authorized": False,
            "authorization_reference": None,
            "authorized_completed_prefix": None,
            "authorized_end_prefix": None,
            "authorized_batch_hash": None,
            "authorized_outer_spend_ceiling_usd": None,
        },
    }
    return CorePayloads(
        analysis_plan=analysis,
        manifest=manifest,
        spec=spec,
        preflight_evidence=evidence,
        dispatch_plan=dispatch_plan,
    )


def write_capsule(repo_root: Path, build: CorePayloads, *, check: bool) -> None:
    output_dir = repo_root.resolve() / V4_CONFIG_DIR
    artifacts = {
        "analysis_plan.json": build.analysis_plan,
        "final_manifest.json": build.manifest,
        "study_spec.json": build.spec,
        "preflight_evidence.json": build.preflight_evidence,
        "dispatch_plan.json": build.dispatch_plan,
    }
    if check:
        for name, payload in artifacts.items():
            path = output_dir / name
            if not path.is_file() or path.read_bytes() != _json_bytes(payload):
                raise ValueError(f"generated v4 artifact is stale: {path}")
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
    spec = _load_object(repo_root / V4_CONFIG_DIR / "study_spec.json")
    revision = spec.get("revision")
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("frozen v4 study spec has no full git revision")
    return revision


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed v4 artifacts differ; do not write files.",
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
                "study_id": V4_PROTOCOL.study_id,
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
