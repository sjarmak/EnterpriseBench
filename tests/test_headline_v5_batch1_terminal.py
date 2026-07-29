from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LIB_ROOT = PROJECT_ROOT / "lib"
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

from eb_study import file_hash, read_receipts  # noqa: E402


STUDY_ROOT = PROJECT_ROOT / "results" / "studies" / "rryas-headline-v5"
PLAN_PATH = (
    PROJECT_ROOT
    / "configs"
    / "studies"
    / "rryas-headline-v5"
    / "dispatch_plan.authorized-batch-001.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_batch1_is_sealed_as_mid_batch_infra_failure() -> None:
    terminal = json.loads((STUDY_ROOT / "batch-001-terminal.json").read_text())
    authorization = terminal["authorization"]
    capacity = terminal["capacity_recheck"]
    execution = terminal["execution"]
    disposition = terminal["disposition"]
    batch_id = authorization["batch_hash"].removeprefix("sha256:")
    rechecks = STUDY_ROOT / "capacity_rechecks"
    committed_plan = subprocess.run(
        [
            "git",
            "show",
            f"{authorization['plan_commit']}:"
            "configs/studies/rryas-headline-v5/"
            "dispatch_plan.authorized-batch-001.json",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    receipts_path = STUDY_ROOT / "receipts.jsonl"
    receipts = read_receipts(receipts_path)
    valid_receipts = [receipt for receipt in receipts if receipt.status == "valid"]
    stop_receipt = receipts[-1]

    assert terminal["status"] == "TERMINAL-MID-BATCH-INFRA-INVALID"
    assert authorization["consumed"] is True
    assert authorization["retry_authorized"] is False
    assert _sha256(PLAN_PATH) == authorization["plan_sha256"]
    assert hashlib.sha256(committed_plan).hexdigest() == authorization["plan_sha256"]
    assert _sha256(rechecks / f"{batch_id}.started.json") == (
        capacity["started_sha256"]
    )
    assert _sha256(rechecks / f"{batch_id}.result.json") == (
        capacity["result_sha256"]
    )
    assert file_hash(receipts_path) == execution["receipts_hash"]
    assert len(receipts) == execution["attempted_slots"] == 4
    assert len(valid_receipts) == execution["valid_slots"] == 3
    assert execution["invalid_slots"] == 1
    assert sum(receipt.usage.cost_usd for receipt in valid_receipts) == pytest.approx(
        execution["reported_outer_spend_usd"]
    )
    assert all(
        receipt.tool_use["cache_isolation"]["valid"] is True
        for receipt in valid_receipts
    )
    assert sum(
        receipt.tool_use["cache_isolation"]["cross_run_cache_read_tokens"]
        for receipt in valid_receipts
    ) == 0
    assert sum(
        receipt.tool_use["cache_isolation"]["cache_write_tokens"]
        for receipt in valid_receipts
    ) == 0
    assert stop_receipt.status == "infra_invalid"
    assert stop_receipt.failure_class == "infra_mcp_preflight"
    assert stop_receipt.usage is None
    assert "agent_trace.jsonl" not in stop_receipt.artifacts
    assert disposition["headline_result"] is False
    assert disposition["promotion_eligible"] is False
    assert disposition["continue_batch"] is False
    assert disposition["retry_batch"] is False
    assert disposition["new_authorization_required"] is True
    actual_files = {
        str(path.relative_to(STUDY_ROOT))
        for path in STUDY_ROOT.rglob("*")
        if path.is_file()
    }
    assert actual_files == set(terminal["sealed_study_files"])


def test_console_contains_all_three_valid_v5_traces() -> None:
    console = (PROJECT_ROOT / "rootcause_console.html").read_text()

    for arm in ("baseline", "mcp_only", "cli"):
        run_id = (
            "dep-graph-tri-tokio-hyper-tonic-001/"
            f"{arm}/claude-claude-sonnet-5/rryas-headline-v5/rep1/attempt1"
        )
        assert run_id in console
