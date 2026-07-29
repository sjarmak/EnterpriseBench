#!/usr/bin/env python3
"""Build the contamination-clean, no-spend rryas headline v3 capsule."""

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

from code_finder_interface_pilot_preflight import (  # noqa: E402
    _default_provenance_provider,
)
from eb_study import StudySpec, file_hash  # noqa: E402
from headline_protocol import (  # noqa: E402
    CANDIDATE_LOCK_REVISION,
    REQUIRED_CACHE_ISOLATION,
    REQUIRED_EVIDENCE_POLICY,
    REQUIRED_EXECUTION_BASE,
    REQUIRED_JUDGE,
    REQUIRED_ORDER_POLICY,
    REQUIRED_SELECTION_RULE,
    V3_AGENT_MAX_BUDGET_USD_PER_SLOT,
    V3_JUDGE_MAX_BUDGET_USD_PER_CALL,
    V3_MAX_JUDGE_ATTEMPTS_PER_CALL,
    V3_MAX_JUDGE_CALLS_PER_SLOT,
    V3_MAX_SLOTS_PER_DISPATCH,
    V3_OUTER_SPEND_HARD_CAP_PER_SLOT_USD,
    V3_PROTOCOL,
    HEADLINE_STUDY_SPEND_CEILINGS_USD,
    required_analysis_plan,
)
from headline_study_preflight import (  # noqa: E402
    HeadlineEvidence,
    compile_execution_order,
)

SOURCE_CONFIG_DIR = Path("configs/studies/rryas-headline-v1")
V3_CONFIG_DIR = Path("configs/studies") / V3_PROTOCOL.study_id
CANDIDATE_MANIFEST = Path("results/rryas_dataset/candidate_manifest.json")
COST_RECEIPTS = (
    Path("results/studies/rryas-headline-v1/receipts.jsonl"),
    Path("results/studies/rryas-headline-v2/receipts.jsonl"),
)
AUTHORIZATION_CEILING_USD = HEADLINE_STUDY_SPEND_CEILINGS_USD[
    V3_PROTOCOL.study_id
]
HEADLINE_STATUS = (
    Path("results/studies") / V3_PROTOCOL.study_id / "study_status.json"
)


@dataclass(frozen=True)
class CorePayloads:
    analysis_plan: Mapping[str, Any]
    manifest: Mapping[str, Any]
    spec: Mapping[str, Any]
    preflight_evidence: Mapping[str, Any]
    dispatch_plan: Mapping[str, Any]


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
        if task.get("candidate_id") not in V3_PROTOCOL.post_lock_exposures
    ]
    expected_ids = [
        candidate_id
        for candidate_id in candidate_ids
        if candidate_id not in V3_PROTOCOL.post_lock_exposures
    ]
    actual_ids = [task.get("candidate_id") for task in selected]
    if actual_ids != expected_ids or len(selected) != V3_PROTOCOL.task_count:
        raise ValueError("v3 selection is not candidate order minus every exposure")
    return selected


def _task_provenances(
    repo_root: Path, tasks: Sequence[Mapping[str, Any]]
) -> tuple[tuple[Any, ...], str]:
    provider = _default_provenance_provider(repo_root)
    provenances = tuple(provider(repo_root / str(task["task_toml"])) for task in tasks)
    harness_hashes = {provenance.harness_hash for provenance in provenances}
    if len(harness_hashes) != 1:
        raise ValueError("v3 tasks do not share one current harness hash")
    for task, provenance in zip(tasks, provenances):
        if task.get("task_hash") != provenance.task_hash:
            raise ValueError(f"task hash drifted for {task.get('task_id')}")
    return provenances, next(iter(harness_hashes))


def _cost_forecast(repo_root: Path) -> dict[str, Any]:
    samples = tuple(
        (path, _sample_costs(repo_root / path)) for path in COST_RECEIPTS
    )
    costs = tuple(cost for _path, values in samples for cost in values)
    total = sum(costs)
    mean = total / len(costs)
    maximum = max(costs)
    envelope = maximum * V3_PROTOCOL.slot_count
    if AUTHORIZATION_CEILING_USD < envelope:
        raise ValueError("v3 authorization ceiling is below the empirical envelope")
    return {
        "basis": (
            "All immutable v1 and v2 attempts, including terminal invalid "
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
        "forecast_outer_spend_usd": round(mean * V3_PROTOCOL.slot_count, 6),
        "max_observed_per_slot_usd": round(maximum, 6),
        "empirical_slot_count_envelope_usd": round(envelope, 6),
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
        "selected_count": V3_PROTOCOL.task_count,
        "post_lock_exposures": [
            {
                "candidate_id": candidate_id,
                "reason": "post_lock_agent_output",
                "evidence": list(
                    V3_PROTOCOL.post_lock_exposure_evidence[candidate_id]
                ),
            }
            for candidate_id in V3_PROTOCOL.post_lock_exposures
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
            for row in compile_execution_order(tasks, study_id=V3_PROTOCOL.study_id)
        ],
    }


def build_core_payloads(repo_root: Path, *, revision: str) -> CorePayloads:
    """Derive every v3 artifact without writing to disk or launching a model."""

    repo_root = repo_root.resolve()
    source_manifest = _load_object(
        repo_root / SOURCE_CONFIG_DIR / "final_manifest.json"
    )
    candidate_path = repo_root / CANDIDATE_MANIFEST
    candidate_manifest = _load_object(candidate_path)
    tasks = _selected_tasks(source_manifest, candidate_manifest)
    analysis = required_analysis_plan(V3_PROTOCOL)
    provenances, harness_hash = _task_provenances(repo_root, tasks)
    output_root = f"results/studies/{V3_PROTOCOL.study_id}"
    manifest = deepcopy(source_manifest)
    manifest.update(
        {
            "study_id": V3_PROTOCOL.study_id,
            "purpose": (
                "Confirmatory Claude Sonnet 5 protocol comparison on every "
                "candidate untouched by the aborted v1 and v2 operational runs."
            ),
            "candidate_manifest": str(CANDIDATE_MANIFEST),
            "candidate_manifest_hash": file_hash(candidate_path),
            "candidate_lock_revision": CANDIDATE_LOCK_REVISION,
            "analysis_plan": str(V3_CONFIG_DIR / "analysis_plan.json"),
            "analysis_plan_hash": _payload_hash(analysis),
            "selection": _selection_payload(),
            "tasks": tasks,
            "arms": dict(V3_PROTOCOL.arm_descriptions),
            "cache_isolation": REQUIRED_CACHE_ISOLATION,
            "judge_configuration": REQUIRED_JUDGE,
            "execution_configuration": _execution_configuration(tasks, output_root),
            "spend_guard": {
                "slots": V3_PROTOCOL.slot_count,
                "max_attempts_per_slot": 1,
                "paid_dispatch_requires_new_explicit_authorization": True,
                "paid_dispatch_authorized": False,
                "forecast_reported_outer_spend_usd": None,
                "forecast_basis": V3_PROTOCOL.forecast_basis,
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
        "study_id": V3_PROTOCOL.study_id,
        "schema_version": 1,
        "task_manifest_hash": _payload_hash(manifest),
        "task_ids": [task["task_id"] for task in tasks],
        "arms": [
            {"name": name, "capability_fingerprint": fingerprint}
            for name, fingerprint in V3_PROTOCOL.arms
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
            study_id=V3_PROTOCOL.study_id,
            spec_hash=study_spec.spec_hash,
            task_manifest_hash=study_spec.task_manifest_hash,
            analysis_plan_hash=_payload_hash(analysis),
            candidate_ids=tuple(str(task["candidate_id"]) for task in tasks),
            task_ids=task_ids,
            slots=tuple(
                (task_id, arm, 1)
                for task_id in task_ids
                for arm, _fingerprint in V3_PROTOCOL.arms
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
    dispatch_plan = {
        "schema_version": 1,
        "study_id": V3_PROTOCOL.study_id,
        "status": "LOCKED-NO-SPEND",
        "study_spec": str(V3_CONFIG_DIR / "study_spec.json"),
        "study_spec_file_hash": _payload_hash(spec),
        "study_spec_hash": study_spec.spec_hash,
        "final_manifest": str(V3_CONFIG_DIR / "final_manifest.json"),
        "final_manifest_hash": _payload_hash(manifest),
        "preflight_evidence": str(V3_CONFIG_DIR / "preflight_evidence.json"),
        "preflight_evidence_hash": _payload_hash(evidence),
        "cost_forecast": _cost_forecast(repo_root),
        "batch_policy": {
            "max_slots_per_dispatch": V3_MAX_SLOTS_PER_DISPATCH,
            "complete_task_triplets": True,
            "score_independent_boundaries": True,
            "agent_max_budget_usd_per_slot": (
                V3_AGENT_MAX_BUDGET_USD_PER_SLOT
            ),
            "judge_max_budget_usd_per_call": (
                V3_JUDGE_MAX_BUDGET_USD_PER_CALL
            ),
            "max_judge_calls_per_slot": V3_MAX_JUDGE_CALLS_PER_SLOT,
            "max_judge_attempts_per_call": V3_MAX_JUDGE_ATTEMPTS_PER_CALL,
            "outer_spend_hard_cap_per_slot_usd": (
                V3_OUTER_SPEND_HARD_CAP_PER_SLOT_USD
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
    output_dir = repo_root.resolve() / V3_CONFIG_DIR
    status_path = repo_root.resolve() / HEADLINE_STATUS
    if status_path.is_file():
        status = _load_object(status_path)
        if (
            status.get("study_id") == V3_PROTOCOL.study_id
            and status.get("status") == "ABORTED-JUDGE-CAP-INVALID"
        ):
            required = {
                "analysis_plan.json",
                "final_manifest.json",
                "study_spec.json",
                "preflight_evidence.json",
                "dispatch_plan.json",
            }
            missing = sorted(
                name for name in required if not (output_dir / name).is_file()
            )
            if missing:
                raise ValueError(
                    f"terminal v3 capsule is missing artifacts: {missing}"
                )
            return
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
                raise ValueError(f"generated v3 artifact is stale: {path}")
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
    spec = _load_object(repo_root / V3_CONFIG_DIR / "study_spec.json")
    revision = spec.get("revision")
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("frozen v3 study spec has no full git revision")
    return revision


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed v3 artifacts differ; do not write files.",
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
                "study_id": V3_PROTOCOL.study_id,
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
