"""Contract tests for the receipt emitter — the producer half of the capsule.

The end-to-end test at the bottom is the one that matters most: a run
directory becomes a receipt, receipts become a capsule, and the capsule
becomes the headline, with the score surviving that trip unchanged. That chain
is what no test previously spanned, which is how a weighted 1.0 could arrive at
the report as 0.25.
"""

from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from analysis.study_report import build_report  # noqa: E402
from eb_study import (  # noqa: E402
    CompletenessError,
    ReceiptError,
    SpecError,
    StudyCapsule,
    append_receipt,
    read_receipts,
)
from orchestration.study_receipt import RunEvidence, build_receipt  # noqa: E402

from tests.test_study_capsule import make_spec  # noqa: E402

EVIDENCE = RunEvidence(
    image_digest="sha256:abc123",
    arm_gate_proof="mode_gate:agent-denied,scorer-allowed",
    task_hash="sha256:task",
    harness_hash="sha256:harness",
    verifier_hash="sha256:verifier",
    started_at="2026-07-20T00:00:00Z",
    ended_at="2026-07-20T00:10:00Z",
)

VENDOR_BLOCK = {
    "total_cost_usd": 1.5,
    "modelUsage": {
        "claude-opus-4-8": {
            "inputTokens": 100,
            "outputTokens": 200,
            "cacheCreationInputTokens": 0,
            "cacheReadInputTokens": 0,
            "costUSD": 1.5,
        }
    },
}


def write_run(
    tmp_path: Path,
    *,
    task_id: str = "dep-traversal-001",
    mode: str = "cli",
    checkpoints: list[dict] | None = None,
    task_score: float = 1.0,
    status: str = "",
    failure_class: str | None = None,
    success: bool = True,
    phase: str = "complete",
    vendor: dict | None = VENDOR_BLOCK,
    name: str | None = None,
    score_contract_version: int = 2,
) -> Path:
    run_dir = tmp_path / (name or f"{task_id}-{mode}")
    run_dir.mkdir(parents=True, exist_ok=True)
    if checkpoints is None:
        checkpoints = [
            {"name": f"cp{i}", "weight": 0.25, "score": 1.0, "passed": True}
            for i in range(4)
        ]
    scores = (
        {
            "task_score": task_score,
            "score_contract_version": score_contract_version,
            "checkpoints_total": len(checkpoints),
            "checkpoints_passed": sum(1 for c in checkpoints if c["passed"]),
            "checkpoints": checkpoints,
        }
        if checkpoints
        else None
    )
    (run_dir / "results.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "success": success,
                "phase": phase,
                "status": status,
                "failure_class": failure_class,
                "scores": scores,
                "tool_usage": {"sgx_tool_calls": 7},
                "config": {"mode": mode},
            }
        )
    )
    if vendor is not None:
        (run_dir / "agent_stdout.log").write_text(json.dumps(vendor))
    return run_dir


def emit(run_dir: Path, spec=None, *, repetition: int = 1, attempt: int = 1):
    return build_receipt(
        spec or make_spec(),
        run_dir,
        repetition=repetition,
        attempt=attempt,
        evidence=EVIDENCE,
    )


class TestValidTrial:
    def test_identity_comes_from_the_spec_not_the_path(self, tmp_path):
        run_dir = write_run(tmp_path, name="whatever-directory-name")
        receipt = emit(run_dir, repetition=2)
        assert receipt.trial.study_id == "rryas-headline-2026-07"
        assert receipt.trial.task_id == "dep-traversal-001"
        assert receipt.trial.arm == "cli"
        assert receipt.trial.repetition == 2

    def test_the_weighted_score_is_not_divided_again(self, tmp_path):
        """Four checkpoints, all perfect, weights summing to 1.0 — this is 1.0."""

        receipt = emit(write_run(tmp_path, task_score=1.0))
        assert receipt.score == 1.0

    def test_unknown_score_contract_cannot_emit_a_receipt(self, tmp_path):
        run_dir = write_run(tmp_path, score_contract_version=99)
        with pytest.raises(ReceiptError, match="score contract"):
            emit(run_dir)

    def test_usage_is_billed_from_the_vendor_block(self, tmp_path):
        receipt = emit(write_run(tmp_path))
        assert receipt.usage is not None
        assert receipt.usage.source == "sdk_model_usage"
        assert receipt.usage.cost_usd == pytest.approx(1.5)
        assert receipt.usage.model_usage["claude-opus-4-8"]["input_tokens"] == 100

    def test_artifacts_are_content_addressed(self, tmp_path):
        receipt = emit(write_run(tmp_path))
        assert set(receipt.artifacts) == {"results.json", "agent_stdout.log"}
        assert all(d.startswith("sha256:") for d in receipt.artifacts.values())

    def test_injected_instruction_is_content_addressed_when_present(self, tmp_path):
        run_dir = write_run(tmp_path)
        (run_dir / "injected_instruction.md").write_text("exact prompt")

        receipt = emit(run_dir)

        assert receipt.artifacts["injected_instruction.md"].startswith("sha256:")

    def test_tool_use_is_carried_through(self, tmp_path):
        assert emit(write_run(tmp_path)).tool_use == {"sgx_tool_calls": 7}

    @pytest.mark.parametrize(
        ("harness", "model", "cost"),
        [
            ("codex", "gpt-5.6-sol", None),
            ("opencode", "openrouter/moonshotai/kimi-k3", 0.4211058),
        ],
    )
    def test_provider_native_usage_emits_valid_generated_harness_receipt(
        self, tmp_path, harness, model, cost
    ):
        run_dir = write_run(tmp_path, vendor=None)
        results_path = run_dir / "results.json"
        results = json.loads(results_path.read_text())
        results["config"].update({"harness": harness, "model": model})
        results["tool_usage"] = {
            "total_input_tokens": 1200,
            "total_output_tokens": 350,
            "cost_usd": 0.0 if cost is None else cost,
            "cost_usd_observed": harness == "opencode",
            "provider_activity": {
                "provider": harness,
                "primary_unit": "turn" if harness == "codex" else "step",
                "primary_count": 2,
            },
            "cache_isolation": {
                "valid": True,
                "cross_run_cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "total_cache_read_tokens": 0,
            },
        }
        results_path.write_text(json.dumps(results))
        spec = make_spec(model=model, token_source="provider_native_usage")

        receipt = emit(run_dir, spec)

        assert receipt.status == "valid"
        assert receipt.usage is not None
        assert receipt.usage.source == "provider_native_usage"
        assert receipt.usage.cost_usd == (
            None if cost is None else pytest.approx(cost, abs=0.000001)
        )
        assert receipt.usage.model_usage[model] == {
            "input_tokens": 1200,
            "output_tokens": 350,
            "cache_write_tokens": 0,
            "cache_read_tokens": 0,
            "cost_usd": None if cost is None else pytest.approx(cost, abs=0.000001),
        }

    def test_opencode_native_usage_requires_observed_cost(self, tmp_path):
        run_dir = write_run(tmp_path, vendor=None)
        results_path = run_dir / "results.json"
        results = json.loads(results_path.read_text())
        results["config"].update(
            {
                "harness": "opencode",
                "model": "openrouter/moonshotai/kimi-k3",
            }
        )
        results["tool_usage"] = {
            "total_input_tokens": 1200,
            "total_output_tokens": 350,
            "cost_usd": 0.0,
            "cost_usd_observed": False,
            "provider_activity": {"provider": "opencode"},
            "cache_isolation": {
                "valid": True,
                "cross_run_cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "total_cache_read_tokens": 0,
            },
        }
        results_path.write_text(json.dumps(results))
        spec = make_spec(
            model="openrouter/moonshotai/kimi-k3",
            token_source="provider_native_usage",
        )

        receipt = emit(run_dir, spec)

        assert receipt.status == "infra_invalid"
        assert receipt.failure_class == "authoritative_usage_missing"
        assert receipt.usage is None

    def test_provider_native_usage_requires_valid_cache_isolation(self, tmp_path):
        run_dir = write_run(tmp_path, vendor=None)
        results_path = run_dir / "results.json"
        results = json.loads(results_path.read_text())
        results["config"].update({"harness": "codex", "model": "gpt-5.6-sol"})
        results["tool_usage"] = {
            "total_input_tokens": 1200,
            "total_output_tokens": 350,
            "provider_activity": {"provider": "codex"},
            "cache_isolation": {
                "valid": False,
                "cross_run_cache_read_tokens": 12,
                "cache_write_tokens": 0,
                "total_cache_read_tokens": 12,
            },
        }
        results_path.write_text(json.dumps(results))
        spec = make_spec(model="gpt-5.6-sol", token_source="provider_native_usage")

        receipt = emit(run_dir, spec)

        assert receipt.status == "infra_invalid"
        assert receipt.failure_class == "authoritative_usage_missing"
        assert receipt.usage is None

    def test_provider_native_usage_rejects_model_drift(self, tmp_path):
        run_dir = write_run(tmp_path, vendor=None)
        results_path = run_dir / "results.json"
        results = json.loads(results_path.read_text())
        results["config"].update({"harness": "codex", "model": "unexpected-model"})
        results["tool_usage"].update(
            {
                "total_input_tokens": 10,
                "total_output_tokens": 20,
                "provider_activity": {"provider": "codex"},
            }
        )
        results_path.write_text(json.dumps(results))
        spec = make_spec(model="gpt-5.6-sol", token_source="provider_native_usage")

        with pytest.raises(ReceiptError, match="model"):
            emit(run_dir, spec)


class TestInvalidTrial:
    def test_an_invalid_status_produces_no_score(self, tmp_path):
        run_dir = write_run(
            tmp_path,
            status="invalid",
            failure_class="mcp_preflight_failed",
            success=False,
            phase="mcp_preflight",
        )
        receipt = emit(run_dir)
        assert receipt.status == "infra_invalid"
        assert receipt.failure_class == "mcp_preflight_failed"
        assert receipt.score is None

    def test_a_run_that_never_completed_is_invalid_even_without_a_status(
        self, tmp_path
    ):
        run_dir = write_run(tmp_path, success=False, phase="build_failed")
        receipt = emit(run_dir)
        assert receipt.status == "infra_invalid"
        assert receipt.failure_class == "run_invalid"

    def test_an_ineligible_task_is_typed_separately(self, tmp_path):
        run_dir = write_run(
            tmp_path,
            status="invalid",
            failure_class="task_ineligible",
            success=False,
            phase="ineligible_for_mode",
        )
        assert emit(run_dir).status == "ineligible"

    def test_a_scoreless_run_does_not_become_a_zero(self, tmp_path):
        run_dir = write_run(tmp_path, checkpoints=[])
        receipt = emit(run_dir)
        assert receipt.status == "infra_invalid"
        assert receipt.failure_class == "scorer_produced_no_checkpoints"
        assert receipt.score is None

    def test_a_run_without_a_vendor_block_cannot_be_priced(self, tmp_path):
        """No trace fallback: an unpriceable run is not a comparable one."""

        run_dir = write_run(tmp_path, vendor=None)
        receipt = emit(run_dir)
        assert receipt.status == "infra_invalid"
        assert receipt.failure_class == "authoritative_usage_missing"
        assert receipt.usage is None


class TestOutOfStudyRuns:
    def test_a_task_outside_the_study_cannot_emit_into_it(self, tmp_path):
        run_dir = write_run(tmp_path, task_id="quarantined-task-999")
        with pytest.raises(SpecError, match="not in study"):
            emit(run_dir)

    def test_an_undeclared_arm_cannot_emit_into_it(self, tmp_path):
        run_dir = write_run(tmp_path, mode="hybrid")
        with pytest.raises(SpecError, match="not declared"):
            emit(run_dir)

    def test_a_repetition_past_the_declared_count_is_refused(self, tmp_path):
        with pytest.raises(SpecError, match="repetition"):
            emit(write_run(tmp_path), repetition=3)


class TestEndToEnd:
    def test_parallel_duplicate_append_admits_exactly_one_receipt(
        self, tmp_path, monkeypatch
    ):
        import eb_study.receipt as receipt_module

        receipts_path = tmp_path / "receipts.jsonl"
        receipts_path.touch()
        receipt = emit(write_run(tmp_path))
        both_read_empty = threading.Barrier(2)

        def synchronized_empty_read(_path):
            both_read_empty.wait()
            return []

        monkeypatch.setattr(receipt_module, "read_receipts", synchronized_empty_read)

        def try_append():
            try:
                append_receipt(receipts_path, receipt)
                return "appended"
            except ReceiptError:
                return "duplicate"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: try_append(), range(2)))

        assert sorted(outcomes) == ["appended", "duplicate"]
        assert receipts_path.read_text().count("\n") == 1

    def test_run_directories_become_a_headline_with_the_score_intact(self, tmp_path):
        spec = make_spec()
        receipts_path = tmp_path / "receipts.jsonl"

        for task_id in spec.task_ids:
            for arm in spec.arm_names:
                for rep in (1, 2):
                    run_dir = write_run(
                        tmp_path,
                        task_id=task_id,
                        mode=arm,
                        task_score=1.0 if arm == "cli" else 0.5,
                        name=f"{task_id}-{arm}-rep{rep}",
                    )
                    append_receipt(receipts_path, emit(run_dir, spec, repetition=rep))

        capsule = StudyCapsule.build(spec, read_receipts(receipts_path))
        report = build_report(capsule)

        assert report["reward"]["by_arm"]["cli"]["mean"] == 1.0
        assert report["reward"]["contrasts"]["cli_vs_baseline"]["mean_delta"] == 0.5
        assert report["completeness"]["paired_tasks"] == 2
        assert report["economics"]["paired_valid"]["total_cost_usd"] == pytest.approx(
            18.0
        )

    def test_one_arm_failing_infrastructure_fails_the_headline(self, tmp_path):
        spec = make_spec()
        receipts_path = tmp_path / "receipts.jsonl"

        for task_id in spec.task_ids:
            for arm in spec.arm_names:
                for rep in (1, 2):
                    run_dir = write_run(
                        tmp_path,
                        task_id=task_id,
                        mode=arm,
                        vendor=None if arm == "cli" else VENDOR_BLOCK,
                        name=f"{task_id}-{arm}-rep{rep}",
                    )
                    append_receipt(receipts_path, emit(run_dir, spec, repetition=rep))

        capsule = StudyCapsule.build(spec, read_receipts(receipts_path))
        with pytest.raises(CompletenessError, match=r"\['cli'\]"):
            build_report(capsule)
