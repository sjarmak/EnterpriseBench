from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STUDY_ROOT = PROJECT_ROOT / "results" / "studies" / "rryas-headline-v4"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_batch1_is_sealed_as_pre_inference_terminal_failure() -> None:
    terminal = json.loads((STUDY_ROOT / "batch-001-terminal.json").read_text())
    authorization = terminal["authorization"]
    capacity = terminal["capacity_recheck"]
    outputs = terminal["observed_outputs"]
    disposition = terminal["disposition"]

    plan = (
        PROJECT_ROOT
        / "configs"
        / "studies"
        / "rryas-headline-v4"
        / "dispatch_plan.authorized-batch-001.json"
    )
    rechecks = STUDY_ROOT / "capacity_rechecks"
    batch_id = authorization["batch_hash"].removeprefix("sha256:")
    committed_plan = subprocess.run(
        [
            "git",
            "show",
            f"{authorization['plan_commit']}:"
            "configs/studies/rryas-headline-v4/"
            "dispatch_plan.authorized-batch-001.json",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
    ).stdout

    assert terminal["status"] == "TERMINAL-PRE-INFERENCE-INFRA-INVALID"
    assert authorization["consumed"] is True
    assert authorization["retry_authorized"] is False
    assert _sha256(plan) == authorization["plan_sha256"]
    assert hashlib.sha256(committed_plan).hexdigest() == authorization["plan_sha256"]
    assert _sha256(rechecks / f"{batch_id}.started.json") == (
        capacity["started_sha256"]
    )
    assert _sha256(rechecks / f"{batch_id}.result.json") == (
        capacity["result_sha256"]
    )
    assert outputs == {
        "failed_slot_output_dir": (
            "results/studies/rryas-headline-v4/runs/"
            "dep-graph-tri-tokio-hyper-tonic-001/baseline"
        ),
        "receipt_created": False,
        "agent_stdout_created": False,
        "agent_trace_created": False,
        "results_created": False,
        "agent_inference_started": False,
        "agent_input_tokens": 0,
        "agent_output_tokens": 0,
        "agent_cost_usd": 0.0,
        "capacity_probe_usage_is_uncovered": True,
    }
    assert disposition["headline_result"] is False
    assert disposition["task_exposed_to_agent"] is False
    assert disposition["continue_batch"] is False
    assert disposition["retry_batch"] is False
    failed_output_dir = PROJECT_ROOT / outputs["failed_slot_output_dir"]
    assert failed_output_dir.exists() is False
    assert (STUDY_ROOT / "receipts.jsonl").exists() is False
    actual_files = {
        str(path.relative_to(STUDY_ROOT))
        for path in STUDY_ROOT.rglob("*")
        if path.is_file()
    }
    assert actual_files == set(terminal["sealed_study_files"])
