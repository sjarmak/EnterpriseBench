from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LIB_ROOT = PROJECT_ROOT / "lib"
ORCHESTRATION_ROOT = PROJECT_ROOT / "scripts" / "orchestration"
for import_root in (LIB_ROOT, ORCHESTRATION_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from eb_study import StudyCapsule, file_hash, read_receipts  # noqa: E402
from headline_study_dispatch import load_dispatch_plan  # noqa: E402
from scripts.analysis.rootcause_console import DATA_SCRIPT_RE  # noqa: E402


STUDY_ID = "rryas-headline-v6"
STUDY_ROOT = PROJECT_ROOT / "results" / "studies" / STUDY_ID
PLAN_RELATIVE = (
    "configs/studies/rryas-headline-v6/"
    "dispatch_plan.authorized-batch-001-refresh-001.json"
)
PLAN_PATH = PROJECT_ROOT / PLAN_RELATIVE


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sealed_tree_hash(paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        path = STUDY_ROOT / relative
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def test_batch1_is_sealed_as_complete_valid_triplets() -> None:
    plan = load_dispatch_plan(PLAN_PATH, repo_root=PROJECT_ROOT)
    controls = plan.v3_controls
    assert controls is not None
    assert controls.authorized_completed_prefix is not None
    assert controls.authorized_end_prefix is not None
    expected_slots = plan.slots[
        controls.authorized_completed_prefix : controls.authorized_end_prefix
    ]
    terminal = json.loads((STUDY_ROOT / "batch-001-terminal.json").read_text())
    authorization = terminal["authorization"]
    capacity = terminal["capacity_recheck"]
    execution = terminal["execution"]
    disposition = terminal["disposition"]
    batch_id = authorization["batch_hash"].removeprefix("sha256:")
    rechecks = STUDY_ROOT / "capacity_rechecks"
    receipts_path = STUDY_ROOT / "receipts.jsonl"
    receipts = read_receipts(receipts_path)
    capsule = StudyCapsule.build(plan.spec, receipts)
    committed_plan = subprocess.run(
        ["git", "show", f"{authorization['plan_commit']}:{PLAN_RELATIVE}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
    ).stdout

    assert terminal["status"] == "TERMINAL-BATCH-COMPLETE"
    assert authorization["consumed"] is True
    assert authorization["retry_authorized"] is False
    assert len(authorization["plan_commit"]) == 40
    assert authorization["reference"] == plan.authorization_reference
    assert authorization["batch_hash"] == controls.authorized_batch_hash
    assert (
        authorization["authorized_completed_prefix"]
        == controls.authorized_completed_prefix
    )
    assert authorization["authorized_end_prefix"] == controls.authorized_end_prefix
    assert (
        authorization["authorized_outer_spend_ceiling_usd"]
        == plan.authorization_ceiling_usd
    )
    assert _sha256(PLAN_PATH) == authorization["plan_sha256"]
    assert hashlib.sha256(committed_plan).hexdigest() == authorization["plan_sha256"]
    assert (
        _sha256(rechecks / f"{batch_id}.started.json") == (capacity["started_sha256"])
    )
    assert _sha256(rechecks / f"{batch_id}.result.json") == (capacity["result_sha256"])
    assert capacity["status"] == "accepted"

    assert file_hash(receipts_path) == execution["receipts_hash"]
    assert len(receipts) == execution["attempted_slots"] == 9
    assert execution["valid_slots"] == 9
    assert execution["invalid_slots"] == 0
    assert execution["completed_task_triplets"] == 3
    assert (
        execution["reported_outer_spend_usd"]
        <= (authorization["authorized_outer_spend_ceiling_usd"])
    )
    assert [receipt.trial for receipt in receipts] == [
        plan.spec.trial_id(
            slot.task_id,
            slot.arm,
            slot.repetition,
            slot.attempt,
        )
        for slot in expected_slots
    ]
    assert all(receipt.status == "valid" for receipt in receipts)
    assert sum(receipt.usage.cost_usd for receipt in receipts) == pytest.approx(
        execution["reported_outer_spend_usd"]
    )
    assert sum(
        receipt.usage.model_usage["claude-sonnet-5"]["cost_usd"] for receipt in receipts
    ) == pytest.approx(execution["reported_agent_spend_usd"])
    assert sum(
        receipt.usage.cost_usd
        - receipt.usage.model_usage["claude-sonnet-5"]["cost_usd"]
        for receipt in receipts
    ) == pytest.approx(execution["reported_judge_spend_usd"])
    assert (
        sum(
            model["input_tokens"]
            for receipt in receipts
            for model in receipt.usage.model_usage.values()
        )
        == execution["reported_input_tokens"]
    )
    assert (
        sum(
            model["output_tokens"]
            for receipt in receipts
            for model in receipt.usage.model_usage.values()
        )
        == execution["reported_output_tokens"]
    )
    assert execution["outcomes"] == [
        {
            "task_id": receipt.trial.task_id,
            "arm": receipt.trial.arm,
            "score": receipt.score,
            "cost_usd": receipt.usage.cost_usd,
            "mcp_tool_calls": receipt.tool_use["mcp_tool_calls"],
            "sgx_tool_calls": receipt.tool_use["sgx_tool_calls"],
        }
        for receipt in receipts
    ]
    assert all(receipt.score_contract == "weighted-mean-v2" for receipt in receipts)
    assert all(receipt.usage.source == "sdk_model_usage" for receipt in receipts)
    assert all(receipt.image_digest.startswith("sha256:") for receipt in receipts)
    assert all(
        receipt.arm_gate_proof.startswith(f"mode_gate:v1:{receipt.trial.arm}:")
        for receipt in receipts
    )
    assert all(receipt.tool_use["trace_captured"] is True for receipt in receipts)
    assert all(
        receipt.tool_use["cache_isolation"]["valid"] is True for receipt in receipts
    )
    assert {
        receipt.tool_use["cache_isolation"]["launcher_scope"] for receipt in receipts
    } == set(execution["cache_isolation"]["launcher_scopes"])
    assert len(execution["cache_isolation"]["launcher_scopes"]) == 9
    assert (
        sum(
            receipt.tool_use["cache_isolation"]["cross_run_cache_read_tokens"]
            for receipt in receipts
        )
        == 0
    )
    assert (
        sum(
            receipt.tool_use["cache_isolation"]["cache_write_tokens"]
            for receipt in receipts
        )
        == 0
    )
    assert all(
        _sha256(
            STUDY_ROOT
            / "runs"
            / receipt.trial.task_id
            / receipt.trial.arm
            / "rep1"
            / "attempt1"
            / "agent_trace.jsonl"
        )
        == receipt.artifacts["agent_trace.jsonl"].removeprefix("sha256:")
        for receipt in receipts
    )
    expected_traces = [
        (
            f"runs/{receipt.trial.task_id}/{receipt.trial.arm}/"
            "rep1/attempt1/agent_trace.jsonl"
        )
        for receipt in receipts
    ]
    assert execution["trace_files"] == expected_traces
    for receipt in receipts:
        result_path = (
            STUDY_ROOT
            / "runs"
            / receipt.trial.task_id
            / receipt.trial.arm
            / "rep1"
            / "attempt1"
            / "results.json"
        )
        assert _sha256(result_path) == receipt.artifacts["results.json"].removeprefix(
            "sha256:"
        )
        provenance = json.loads(result_path.read_text())["scores"]["judge_provenance"]
        assert provenance["backend"] == "claude_code_cli"
        assert provenance["provider"] == "anthropic"
        assert provenance["account"] == 1
        assert provenance["executable"] == "claude-1"
    assert all(
        receipt.tool_use["mcp_tool_calls"] > 0
        for receipt in receipts
        if receipt.trial.arm == "mcp_only"
    )
    assert all(
        receipt.tool_use["sgx_tool_calls"] > 0
        for receipt in receipts
        if receipt.trial.arm == "cli"
    )
    paired = capsule.paired_valid()
    assert paired.task_ids == tuple(
        dict.fromkeys(slot.task_id for slot in expected_slots)
    )
    assert paired.arms == plan.spec.arm_names

    assert disposition["headline_result"] is False
    assert disposition["promotion_eligible"] is False
    assert disposition["continue_batch"] is False
    assert disposition["retry_batch"] is False
    assert disposition["new_authorization_required"] is True
    actual_files = sorted(
        str(path.relative_to(STUDY_ROOT))
        for path in STUDY_ROOT.rglob("*")
        if path.is_file() and path.name != "batch-001-terminal.json"
    )
    assert actual_files == terminal["sealed_study_files"]
    assert _sealed_tree_hash(actual_files) == terminal["sealed_tree_hash"]


def test_console_contains_all_nine_v6_traces() -> None:
    console = (PROJECT_ROOT / "rootcause_console.html").read_text()
    match = DATA_SCRIPT_RE.search(console)
    assert match is not None
    cells = json.loads(match.group(2))
    v6_cells = [cell for cell in cells if cell.get("study_id") == STUDY_ID]
    plan = load_dispatch_plan(PLAN_PATH, repo_root=PROJECT_ROOT)
    controls = plan.v3_controls
    assert controls is not None
    expected_slots = plan.slots[
        controls.authorized_completed_prefix : controls.authorized_end_prefix
    ]

    assert len(v6_cells) == len(expected_slots) == 9
    assert {(cell["task"], cell["mode"]) for cell in v6_cells} == {
        (slot.task_id, slot.arm) for slot in expected_slots
    }
    for cell in v6_cells:
        run_id = (
            f"{cell['task']}/{cell['mode']}/claude-claude-sonnet-5/"
            f"{STUDY_ID}/rep1/attempt1"
        )
        trace_source = (
            STUDY_ROOT
            / "runs"
            / cell["task"]
            / cell["mode"]
            / "rep1"
            / "attempt1"
            / "agent_stdout.log"
        )
        persisted_source = Path(cell["trace_source"])
        if not persisted_source.is_absolute():
            persisted_source = PROJECT_ROOT / persisted_source
        assert cell["run_id"] == run_id
        assert persisted_source.resolve() == trace_source.resolve()
        assert cell["trace"]
