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

from build_headline_v6_capsule import (  # noqa: E402
    build_core_payloads,
)
from eb_study import file_hash  # noqa: E402
import headline_protocol_evidence as protocol_evidence  # noqa: E402
from headline_protocol import V5_PROTOCOL, V6_PROTOCOL  # noqa: E402
from headline_study_dispatch import load_dispatch_plan  # noqa: E402


V5_TERMINAL = Path("results/studies/rryas-headline-v5/batch-001-terminal.json")
V5_RECEIPTS = Path("results/studies/rryas-headline-v5/receipts.jsonl")
V5_EXPOSED_TASK = "dep-graph-tri-tokio-hyper-tonic-001"
V5_UNEXPOSED_FAILED_TASK = "dep-traversal-001"


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_v6_excludes_only_the_v5_agent_exposed_task() -> None:
    build = build_core_payloads(PROJECT_ROOT, revision=_head())
    v5_manifest = json.loads(
        (
            PROJECT_ROOT
            / "configs"
            / "studies"
            / V5_PROTOCOL.study_id
            / "final_manifest.json"
        ).read_text()
    )
    v5_ids = [task["task_id"] for task in v5_manifest["tasks"]]

    assert build.spec["study_id"] == V6_PROTOCOL.study_id
    assert build.spec["revision"] == _head()
    assert build.spec["task_ids"] == [
        task_id for task_id in v5_ids if task_id != V5_EXPOSED_TASK
    ]
    assert V5_UNEXPOSED_FAILED_TASK in build.spec["task_ids"]
    assert len(build.spec["task_ids"]) == 30
    assert len(build.manifest["execution_configuration"]["execution_order"]) == 90
    for field in (
        "arms",
        "cache_isolation",
        "judge_configuration",
        "evidence_policy",
    ):
        assert build.manifest[field] == v5_manifest[field]
    amendment = build.analysis_plan["protocol_amendment"]
    assert amendment == {
        "predecessor": "rryas-headline-v5",
        "reason": (
            "v5 stopped fail-closed on a Sourcegraph MCP authentication "
            "failure before agent startup on the fourth attempt"
        ),
        "selection_rule": (
            "exclude every task with v1-v3 or v5 agent output; retain all "
            "other locked candidates without inspecting reward"
        ),
        "excluded_candidate_ids": [V5_EXPOSED_TASK],
        "predecessor_terminal_evidence": str(V5_TERMINAL),
        "predecessor_terminal_evidence_sha256": file_hash(
            PROJECT_ROOT / V5_TERMINAL
        ),
        "predecessor_receipts": str(V5_RECEIPTS),
        "predecessor_receipts_sha256": file_hash(PROJECT_ROOT / V5_RECEIPTS),
        "unexposed_failed_task_ids": [V5_UNEXPOSED_FAILED_TASK],
        "predecessor_analysis_use": (
            "operational evidence and task-level descriptive diagnostics only"
        ),
    }
    assert build.dispatch_plan["provider_capacity"]["confirmed"] is False
    assert build.dispatch_plan["authorization"]["paid_dispatch_authorized"] is False
    forecast = build.dispatch_plan["cost_forecast"]
    assert forecast["sample_attempts"] == 35
    assert forecast["sample_outer_spend_usd"] == pytest.approx(145.601469)
    assert forecast["sample_receipts"][-1] == {
        "path": str(V5_RECEIPTS),
        "sha256": file_hash(PROJECT_ROOT / V5_RECEIPTS),
    }


def test_repository_v6_artifacts_match_published_terminal_commit() -> None:
    terminal = json.loads(
        (
            PROJECT_ROOT
            / "results"
            / "studies"
            / V6_PROTOCOL.study_id
            / "batch-001-terminal.json"
        ).read_text()
    )
    revision = terminal["authorization"]["plan_commit"]
    capsule_root = Path("configs/studies") / V6_PROTOCOL.study_id
    for name in (
        "analysis_plan.json",
        "dispatch_plan.json",
        "final_manifest.json",
        "preflight_evidence.json",
        "study_spec.json",
    ):
        relative = capsule_root / name
        committed = subprocess.run(
            ["git", "show", f"{revision}:{relative}"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        assert (PROJECT_ROOT / relative).read_bytes() == committed


def test_repository_v6_dispatch_plan_is_locked_no_spend() -> None:
    plan = load_dispatch_plan(
        PROJECT_ROOT
        / "configs"
        / "studies"
        / V6_PROTOCOL.study_id
        / "dispatch_plan.json",
        repo_root=PROJECT_ROOT,
    )

    assert len(plan.slots) == 90
    assert plan.paid_dispatch_authorized is False
    assert plan.authorization_reference is None
    assert plan.authorization_ceiling_usd == pytest.approx(990.0)


@pytest.mark.parametrize("evidence_path", (V5_TERMINAL, V5_RECEIPTS))
def test_v6_builder_rejects_changed_predecessor_evidence(
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

    with pytest.raises(ValueError, match="v6 predecessor evidence"):
        build_core_payloads(PROJECT_ROOT, revision=_head())
