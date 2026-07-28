from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for import_path in (
    PROJECT_ROOT / "lib",
    PROJECT_ROOT / "scripts" / "infra",
    PROJECT_ROOT / "scripts" / "orchestration",
    PROJECT_ROOT / "scripts" / "studies",
):
    sys.path.insert(0, str(import_path))

from build_headline_v3_capsule import (  # noqa: E402
    build_core_payloads,
    configured_revision,
    write_capsule,
)
from headline_protocol import V3_PROTOCOL  # noqa: E402


def test_v3_builder_uses_only_the_32_remaining_unexposed_tasks() -> None:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    candidates = json.loads(
        (PROJECT_ROOT / "results/rryas_dataset/candidate_manifest.json").read_text()
    )

    build = build_core_payloads(PROJECT_ROOT, revision=revision)

    expected_ids = [
        task_id
        for task_id in candidates["task_ids"]
        if task_id not in V3_PROTOCOL.post_lock_exposures
    ]
    actual_ids = [task["candidate_id"] for task in build.manifest["tasks"]]
    assert actual_ids == expected_ids
    assert len(actual_ids) == 32
    assert len(build.manifest["execution_configuration"]["execution_order"]) == 96
    assert build.manifest["selection"]["selected_count"] == 32
    assert build.spec["study_id"] == "rryas-headline-v3"
    assert build.spec["harness"] == build.manifest["harness_hash"]
    assert build.dispatch_plan["authorization"] == {
        "paid_dispatch_authorized": False,
        "authorization_reference": None,
        "authorized_completed_prefix": None,
        "authorized_end_prefix": None,
        "authorized_batch_hash": None,
        "authorized_outer_spend_ceiling_usd": None,
    }
    assert build.dispatch_plan["provider_capacity"] == {
        "confirmed": False,
        "capacity_reference": None,
        "confirmed_completed_prefix": None,
        "confirmed_max_slots": None,
    }
    assert build.dispatch_plan["batch_policy"] == {
        "max_slots_per_dispatch": 12,
        "complete_task_triplets": True,
        "score_independent_boundaries": True,
        "agent_max_budget_usd_per_slot": 9.1,
        "judge_max_budget_usd_per_call": 0.01,
        "max_judge_calls_per_slot": 5,
        "max_judge_attempts_per_call": 3,
        "outer_spend_hard_cap_per_slot_usd": 9.25,
    }
    assert build.dispatch_plan["cost_forecast"]["sample_attempts"] == 30
    assert build.dispatch_plan["cost_forecast"]["sample_outer_spend_usd"] == (
        132.24647
    )
    assert (
        build.dispatch_plan["cost_forecast"][
            "authorization_outer_spend_ceiling_usd"
        ]
        == 890.0
    )


def test_repository_v3_artifacts_are_current() -> None:
    revision = configured_revision(PROJECT_ROOT)
    build = build_core_payloads(PROJECT_ROOT, revision=revision)

    write_capsule(PROJECT_ROOT, build, check=True)
