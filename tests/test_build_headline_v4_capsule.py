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

from build_headline_v4_capsule import build_core_payloads  # noqa: E402
from eb_study import file_hash  # noqa: E402
from headline_protocol import V4_PROTOCOL  # noqa: E402


def test_v4_builder_excludes_every_v1_through_v3_exposed_task() -> None:
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
        if task_id not in V4_PROTOCOL.post_lock_exposures
    ]
    actual_ids = [task["candidate_id"] for task in build.manifest["tasks"]]
    assert actual_ids == expected_ids
    assert len(actual_ids) == 31
    assert len(build.manifest["execution_configuration"]["execution_order"]) == 93
    assert build.spec["study_id"] == "rryas-headline-v4"
    assert build.manifest["judge_configuration"]["isolation"] == (
        "safe-mode:no-tools:replacement-system-prompt"
    )
    assert build.dispatch_plan["batch_policy"] == {
        "max_slots_per_dispatch": 9,
        "complete_task_triplets": True,
        "score_independent_boundaries": True,
        "agent_max_budget_usd_per_slot": 9.1,
        "judge_max_budget_usd_per_call": 0.1,
        "max_judge_calls_per_slot": 5,
        "max_judge_attempts_per_call": 3,
        "outer_spend_hard_cap_per_slot_usd": 10.6,
    }
    assert build.dispatch_plan["authorization"]["paid_dispatch_authorized"] is False
    assert build.dispatch_plan["provider_capacity"]["confirmed"] is False
    assert build.dispatch_plan["provider_capacity"]["eligibility_policy"] == (
        "fresh-account-specific-utilization-below-100-percent"
    )
    assert build.dispatch_plan["provider_capacity"]["confound_policy"] == (
        "accept-and-report-observed-nonzero-provider-utilization"
    )


def test_repository_v4_artifacts_remain_terminally_frozen() -> None:
    expected_hashes = {
        "analysis_plan.json": (
            "sha256:e823ab3796d0785f7aea246dc2e18d595ec182f6a28ad96d4eac39e0ca461b54"
        ),
        "dispatch_plan.json": (
            "sha256:a9e36ae5f30ba7c7718edd0d0910295a95a99faf949586655f538d28356ca0a7"
        ),
        "final_manifest.json": (
            "sha256:766715c9dfb427e1989a89c3c0f623bd30034752923045716fe8bb353d38f166"
        ),
        "preflight_evidence.json": (
            "sha256:989fd5f37c29fce9e73e5ed7465d6dc77d3b8e8c054fd71f7a54b9543e19b416"
        ),
        "study_spec.json": (
            "sha256:808544fe1d256b39f037761d4605d761641508769f426d9749d5be2681871b2d"
        ),
    }
    config_dir = PROJECT_ROOT / "configs" / "studies" / "rryas-headline-v4"

    assert {
        name: file_hash(config_dir / name) for name in expected_hashes
    } == expected_hashes
