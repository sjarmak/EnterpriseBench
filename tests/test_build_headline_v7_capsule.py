from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
for import_path in (
    PROJECT_ROOT / "lib",
    PROJECT_ROOT / "scripts" / "infra",
    PROJECT_ROOT / "scripts" / "orchestration",
    PROJECT_ROOT / "scripts" / "studies",
):
    sys.path.insert(0, str(import_path))

from build_headline_v7_capsule import (  # noqa: E402
    build_core_payloads,
    configured_revision,
    main,
    write_capsule,
)
from eb_study import file_hash  # noqa: E402
import headline_protocol_evidence as protocol_evidence  # noqa: E402
from headline_protocol import V6_PROTOCOL, V7_PROTOCOL  # noqa: E402
from headline_study_dispatch import load_dispatch_plan  # noqa: E402
from headline_study_preflight import validate_headline_study  # noqa: E402


V6_TERMINAL = Path("results/studies/rryas-headline-v6/batch-001-terminal.json")
V6_RECEIPTS = Path("results/studies/rryas-headline-v6/receipts.jsonl")
V6_EXPOSED_TASKS = (
    "dep-traversal-001",
    "dep-traversal-002",
    "dep-traversal-004",
)


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_v7_excludes_only_v6_agent_exposed_tasks() -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())
    v6_manifest = json.loads(
        (
            PROJECT_ROOT
            / "configs"
            / "studies"
            / V6_PROTOCOL.study_id
            / "final_manifest.json"
        ).read_text()
    )
    v6_ids = [task["task_id"] for task in v6_manifest["tasks"]]

    assert build.spec["study_id"] == V7_PROTOCOL.study_id
    assert build.spec["revision"] == _head()
    assert build.spec["task_ids"] == [
        task_id for task_id in v6_ids if task_id not in V6_EXPOSED_TASKS
    ]
    assert len(build.spec["task_ids"]) == 27
    assert len(build.manifest["execution_configuration"]["execution_order"]) == 81
    for field in (
        "arms",
        "cache_isolation",
        "judge_configuration",
        "evidence_policy",
    ):
        assert build.manifest[field] == v6_manifest[field]
    amendment = build.analysis_plan["protocol_amendment"]
    assert amendment == {
        "predecessor": "rryas-headline-v6",
        "reason": (
            "the execution harness changed after v6 batch 1 was sealed; "
            "continuing v6 would mix harness identities"
        ),
        "selection_rule": (
            "exclude every task with v1-v3, v5, or v6 agent output; retain all "
            "other locked candidates without inspecting reward"
        ),
        "excluded_candidate_ids": list(V6_EXPOSED_TASKS),
        "predecessor_terminal_evidence": str(V6_TERMINAL),
        "predecessor_terminal_evidence_sha256": file_hash(
            PROJECT_ROOT / V6_TERMINAL
        ),
        "predecessor_receipts": str(V6_RECEIPTS),
        "predecessor_receipts_sha256": file_hash(PROJECT_ROOT / V6_RECEIPTS),
        "predecessor_analysis_use": (
            "operational evidence and task-level descriptive diagnostics only"
        ),
    }
    assert build.dispatch_plan["provider_capacity"]["confirmed"] is False
    assert build.dispatch_plan["authorization"]["paid_dispatch_authorized"] is False
    forecast = build.dispatch_plan["cost_forecast"]
    assert forecast["sample_attempts"] == 44
    assert forecast["sample_outer_spend_usd"] == pytest.approx(181.675256)
    assert forecast["sample_receipts"][-1] == {
        "path": str(V6_RECEIPTS),
        "sha256": file_hash(PROJECT_ROOT / V6_RECEIPTS),
    }


def test_repository_v7_artifacts_are_current() -> None:
    build = build_core_payloads(
        PROJECT_ROOT,
        revision=configured_revision(PROJECT_ROOT),
    )

    write_capsule(PROJECT_ROOT, build, check=True)


def test_v7_builder_check_cli_reports_no_spend(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--check"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["study_id"] == V7_PROTOCOL.study_id
    assert report["tasks"] == 27
    assert report["slots"] == 81
    assert report["paid_dispatch_authorized"] is False


def test_repository_v7_dispatch_plan_is_locked_no_spend() -> None:
    plan = load_dispatch_plan(
        PROJECT_ROOT
        / "configs"
        / "studies"
        / V7_PROTOCOL.study_id
        / "dispatch_plan.json",
        repo_root=PROJECT_ROOT,
    )

    assert len(plan.slots) == 81
    assert plan.paid_dispatch_authorized is False
    assert plan.authorization_reference is None
    assert plan.authorization_ceiling_usd == pytest.approx(990.0)


def test_repository_v7_passes_zero_inference_preflight() -> None:
    study_root = (
        PROJECT_ROOT / "configs" / "studies" / V7_PROTOCOL.study_id
    )
    evidence = validate_headline_study(
        spec_path=study_root / "study_spec.json",
        manifest_path=study_root / "final_manifest.json",
        candidate_manifest_path=(
            PROJECT_ROOT
            / "results"
            / "rryas_dataset"
            / "candidate_manifest.json"
        ),
        analysis_plan_path=study_root / "analysis_plan.json",
        repo_root=PROJECT_ROOT,
        mirror_probe=lambda _repository: True,
        auth_probe=lambda _credential: True,
    )

    assert evidence.study_id == V7_PROTOCOL.study_id
    assert len(evidence.task_ids) == 27
    assert len(evidence.slots) == 81
    assert evidence.paid_dispatch_authorized is False


@pytest.mark.parametrize("evidence_path", (V6_TERMINAL, V6_RECEIPTS))
def test_v7_builder_rejects_changed_predecessor_evidence(
    monkeypatch: pytest.MonkeyPatch,
    evidence_path: Path,
) -> None:
    real_file_hash = protocol_evidence.file_hash
    resolved_evidence = (PROJECT_ROOT / evidence_path).resolve()

    def tampered_file_hash(path: Path) -> str:
        if path.resolve() == resolved_evidence:
            return f"sha256:{'0' * 64}"
        return real_file_hash(path)

    monkeypatch.setattr(protocol_evidence, "file_hash", tampered_file_hash)

    with pytest.raises(ValueError, match="v7 predecessor evidence"):
        build_core_payloads(PROJECT_ROOT, revision=_head())
