#!/usr/bin/env python3
"""Tests for scripts/triage/triage_run.py — centralized failure classifier."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Import helpers — add scripts/ to sys.path so triage module is importable
# ---------------------------------------------------------------------------
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from triage.triage_run import (
    classify_task,
    scan_results_dir,
    build_report,
    TriageCategory,
)

# ---------------------------------------------------------------------------
# Fixtures: build minimal result dirs in tmp_path
# ---------------------------------------------------------------------------


def _write_results_json(task_dir: Path, data: dict[str, Any]) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    p = task_dir / "results.json"
    p.write_text(json.dumps(data))
    return p


def _write_log(task_dir: Path, filename: str, content: str) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    p = task_dir / filename
    p.write_text(content)
    return p


def _make_results(
    *,
    task_id: str = "test-task-001",
    success: bool = True,
    phase: str = "complete",
    error: str = "",
    task_score: float = 2.0,
    all_passed: bool = True,
    checkpoints: list[dict[str, Any]] | None = None,
    failure_class: str | None = None,
) -> dict[str, Any]:
    if checkpoints is None:
        checkpoints = [
            {
                "name": "cp1",
                "weight": 1.0,
                "score": 1.0,
                "passed": True,
                "duration_ms": 10,
                "exit_code": 0,
            },
            {
                "name": "cp2",
                "weight": 1.0,
                "score": 1.0,
                "passed": True,
                "duration_ms": 10,
                "exit_code": 0,
            },
        ]
    return {
        "task_id": task_id,
        "success": success,
        "phase": phase,
        "error": error,
        "failure_class": failure_class,
        "scores": {
            "task_score": task_score,
            "all_passed": all_passed,
            "checkpoints_passed": sum(1 for c in checkpoints if c.get("passed")),
            "checkpoints_total": len(checkpoints),
            "repos": ["testrepo"],
            "checkpoints": checkpoints,
        },
        "timing": {"agent": 120.0},
        "config": {"timeout": 300},
        "task_metadata": {
            "suite": "test_suite",
            "task_type": "error_provenance",
            "difficulty": "medium",
            "languages": ["python"],
        },
    }


# ---------------------------------------------------------------------------
# Test: Classify a pass result (score > 0)
# ---------------------------------------------------------------------------


class TestClassifyPass:
    def test_pass_all_checkpoints(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "pass-task-001"
        data = _make_results(task_id="pass-task-001", task_score=2.0, all_passed=True)
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.PASS
        assert result["task_id"] == "pass-task-001"
        assert result["score"] == 2.0

    def test_pass_partial_checkpoints(self, tmp_path: Path) -> None:
        """Score > 0 but not all checkpoints passed is still 'pass'."""
        cps = [
            {
                "name": "cp1",
                "weight": 1.0,
                "score": 1.0,
                "passed": True,
                "duration_ms": 10,
                "exit_code": 0,
            },
            {
                "name": "cp2",
                "weight": 1.0,
                "score": 0.0,
                "passed": False,
                "duration_ms": 10,
                "exit_code": 0,
            },
        ]
        task_dir = tmp_path / "partial-pass-001"
        data = _make_results(
            task_id="partial-pass-001",
            task_score=1.0,
            all_passed=False,
            checkpoints=cps,
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.PASS


# ---------------------------------------------------------------------------
# Test: Classify an infra error (docker failure in log)
# ---------------------------------------------------------------------------


class TestClassifyInfra:
    def test_docker_daemon_error_in_log(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "infra-task-001"
        data = _make_results(
            task_id="infra-task-001",
            success=False,
            phase="build",
            error="Cannot connect to the Docker daemon",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)
        _write_log(
            task_dir,
            "agent_stdout.log",
            "Cannot connect to the Docker daemon. Is the docker daemon running?\n",
        )

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.A_INFRA
        assert result["fingerprint_id"] == "docker_daemon"

    def test_oom_killed(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "oom-task-001"
        data = _make_results(
            task_id="oom-task-001",
            success=False,
            phase="agent",
            error="OOMKill detected in container",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.A_INFRA
        assert result["fingerprint_id"] == "oom_killed"

    def test_context_window_exceeded(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "ctx-task-001"
        data = _make_results(
            task_id="ctx-task-001",
            success=False,
            phase="agent",
            error="conversation is too long for this model",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.A_INFRA


# ---------------------------------------------------------------------------
# Test: Classify a timeout
# ---------------------------------------------------------------------------


class TestClassifyTimeout:
    def test_timeout_in_error(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "timeout-task-001"
        data = _make_results(
            task_id="timeout-task-001",
            success=False,
            phase="agent",
            error="Task timed out after 300s",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.E_TIMEOUT

    def test_timeout_in_log(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "timeout-task-002"
        data = _make_results(
            task_id="timeout-task-002",
            success=False,
            phase="agent",
            error="",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)
        _write_log(
            task_dir, "agent_stdout.log", "Agent SIGTERM received, deadline exceeded\n"
        )

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.E_TIMEOUT


# ---------------------------------------------------------------------------
# Test: Classify agent quality (completed, score=0, no fingerprint)
# ---------------------------------------------------------------------------


class TestClassifyAgentQuality:
    def test_completed_zero_score_no_fingerprint(self, tmp_path: Path) -> None:
        cps = [
            {
                "name": "cp1",
                "weight": 1.0,
                "score": 0.0,
                "passed": False,
                "duration_ms": 10,
                "exit_code": 0,
            },
            {
                "name": "cp2",
                "weight": 1.0,
                "score": 0.0,
                "passed": False,
                "duration_ms": 10,
                "exit_code": 0,
            },
        ]
        task_dir = tmp_path / "agent-task-001"
        data = _make_results(
            task_id="agent-task-001",
            success=True,
            phase="complete",
            error="",
            task_score=0.0,
            all_passed=False,
            checkpoints=cps,
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.D_AGENT

    def test_agent_no_output_fingerprint(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "agent-task-002"
        data = _make_results(
            task_id="agent-task-002",
            success=False,
            phase="complete",
            error="Agent produced no output",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.D_AGENT
        assert result["fingerprint_id"] == "agent_no_output"


# ---------------------------------------------------------------------------
# Test: Classify verifier error
# ---------------------------------------------------------------------------


class TestClassifyVerifier:
    def test_verifier_error_in_error_field(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "verifier-task-001"
        data = _make_results(
            task_id="verifier-task-001",
            success=False,
            phase="scoring",
            error="eb_verify plugin error: ValueError raised in checkpoint",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.C_VERIFIER
        assert result["fingerprint_id"] == "eb_verify_error"

    def test_checkpoint_script_error(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "verifier-task-002"
        data = _make_results(
            task_id="verifier-task-002",
            success=False,
            phase="scoring",
            error="checkpoint script exit code 2: error in .verifiers/",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.C_VERIFIER


# ---------------------------------------------------------------------------
# Test: Setup error
# ---------------------------------------------------------------------------


class TestClassifySetup:
    def test_docker_build_fail(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "setup-task-001"
        data = _make_results(
            task_id="setup-task-001",
            success=False,
            phase="build",
            error="Docker build failed for image eb-setup-task-001",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.B_SETUP

    def test_pip_install_fail(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "setup-task-002"
        data = _make_results(
            task_id="setup-task-002",
            success=False,
            phase="setup",
            error="pip install failed: No matching distribution found for foobar",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.B_SETUP


# ---------------------------------------------------------------------------
# Test: Summary counts
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_counts(self, tmp_path: Path) -> None:
        # Create 3 tasks: 1 pass, 1 infra, 1 agent
        _write_results_json(
            tmp_path / "pass-001",
            _make_results(task_id="pass-001", task_score=2.0),
        )
        _write_results_json(
            tmp_path / "infra-001",
            _make_results(
                task_id="infra-001", success=False, error="OOMKill", task_score=0.0
            ),
        )
        cps = [
            {
                "name": "cp1",
                "weight": 1.0,
                "score": 0.0,
                "passed": False,
                "duration_ms": 10,
                "exit_code": 0,
            }
        ]
        _write_results_json(
            tmp_path / "agent-001",
            _make_results(
                task_id="agent-001", task_score=0.0, all_passed=False, checkpoints=cps
            ),
        )

        tasks = scan_results_dir(tmp_path)
        report = build_report(tasks, str(tmp_path))

        assert report["summary"]["pass"] == 1
        assert report["summary"]["A_infra"] == 1
        assert report["summary"]["D_agent"] == 1
        assert report["summary"]["total"] == 3


# ---------------------------------------------------------------------------
# Test: Checkpoint detail preserved
# ---------------------------------------------------------------------------


class TestCheckpointDetail:
    def test_checkpoints_in_output(self, tmp_path: Path) -> None:
        cps = [
            {
                "name": "error_chain",
                "weight": 1.0,
                "score": 0.95,
                "passed": True,
                "duration_ms": 127,
                "exit_code": 0,
            },
            {
                "name": "error_source",
                "weight": 1.0,
                "score": 0.0,
                "passed": False,
                "duration_ms": 15,
                "exit_code": 0,
            },
        ]
        task_dir = tmp_path / "cp-task-001"
        data = _make_results(
            task_id="cp-task-001", task_score=0.95, all_passed=False, checkpoints=cps
        )
        _write_results_json(task_dir, data)

        result = classify_task(task_dir)
        assert "checkpoints" in result
        assert len(result["checkpoints"]) == 2
        assert result["checkpoints"][0]["name"] == "error_chain"
        assert result["checkpoints"][0]["passed"] is True
        assert result["checkpoints"][1]["name"] == "error_source"
        assert result["checkpoints"][1]["passed"] is False


# ---------------------------------------------------------------------------
# Test: CLI argument parsing
# ---------------------------------------------------------------------------


class TestCLI:
    def test_parse_defaults(self) -> None:
        from triage.triage_run import parse_args

        args = parse_args([])
        assert args.results_dir == "results/runs"
        assert args.output is None
        assert args.format == "json"

    def test_parse_custom(self) -> None:
        from triage.triage_run import parse_args

        args = parse_args(
            ["--results-dir", "/tmp/runs", "--output", "out.json", "--format", "table"]
        )
        assert args.results_dir == "/tmp/runs"
        assert args.output == "out.json"
        assert args.format == "table"


# ---------------------------------------------------------------------------
# Test: Missing results.json handled gracefully
# ---------------------------------------------------------------------------


class TestMissingResults:
    def test_missing_results_json(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "missing-001"
        task_dir.mkdir()
        # No results.json — just an empty dir

        result = classify_task(task_dir)
        assert result is None  # skip dirs without results.json

    def test_corrupt_results_json(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "corrupt-001"
        task_dir.mkdir()
        (task_dir / "results.json").write_text("not valid json {{{")

        result = classify_task(task_dir)
        assert result is None

    def test_scan_skips_batch_summaries(self, tmp_path: Path) -> None:
        """_batch_summaries dir should be skipped."""
        batch_dir = tmp_path / "_batch_summaries" / "20260331"
        batch_dir.mkdir(parents=True)
        (batch_dir / "summary.json").write_text("{}")

        _write_results_json(
            tmp_path / "real-task-001",
            _make_results(task_id="real-task-001", task_score=1.0),
        )

        tasks = scan_results_dir(tmp_path)
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == "real-task-001"


# ---------------------------------------------------------------------------
# Test: Log-only classification (error field empty, log has signal)
# ---------------------------------------------------------------------------


class TestLogOnlyClassification:
    def test_infra_from_log_when_error_empty(self, tmp_path: Path) -> None:
        task_dir = tmp_path / "log-infra-001"
        data = _make_results(
            task_id="log-infra-001",
            success=False,
            phase="agent",
            error="",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)
        _write_log(
            task_dir,
            "agent_stdout.log",
            "Error: Cannot connect to the Docker daemon\nFailed.\n",
        )

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.A_INFRA


# ---------------------------------------------------------------------------
# Test: Agent output overrides fingerprint (misclassification fix)
# ---------------------------------------------------------------------------


class TestAgentOutputOverridesFingerprint:
    """When an agent produced meaningful output (result + cost > 0) but scored 0,
    classify as D_agent even if the log text contains infra fingerprint strings.
    """

    def _agent_log_json(
        self, result_text: str = "The answer is X", cost: float = 0.38
    ) -> str:
        """Build a realistic agent_stdout.log JSON blob."""
        return json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": result_text,
                "total_cost_usd": cost,
                "num_turns": 5,
            }
        )

    def test_agent_output_with_infra_fingerprint_classified_as_d_agent(
        self,
        tmp_path: Path,
    ) -> None:
        """Agent ran, produced an answer, cost > 0, score 0.
        Log happens to contain '500' (HTTP status code discussion).
        Should be D_agent, not A_infra."""
        task_dir = tmp_path / "ccx-compliance-052"
        data = _make_results(
            task_id="ccx-compliance-052",
            success=True,
            phase="complete",
            error="",
            task_score=0.0,
            all_passed=False,
            checkpoints=[
                {
                    "name": "cp1",
                    "weight": 1.0,
                    "score": 0.0,
                    "passed": False,
                    "duration_ms": 10,
                    "exit_code": 0,
                },
            ],
        )
        _write_results_json(task_dir, data)
        _write_log(
            task_dir,
            "agent_stdout.log",
            self._agent_log_json(
                result_text="The server returned HTTP 500 when calling /api/v2/health",
                cost=0.38,
            ),
        )

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.D_AGENT

    def test_agent_output_with_cost_zero_falls_through_to_fingerprint(
        self,
        tmp_path: Path,
    ) -> None:
        """Agent log has result text but cost is 0 — not meaningful output,
        so fingerprint should still apply."""
        task_dir = tmp_path / "cost-zero-001"
        data = _make_results(
            task_id="cost-zero-001",
            success=False,
            phase="agent",
            error="Cannot connect to the Docker daemon",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)
        _write_log(
            task_dir,
            "agent_stdout.log",
            json.dumps(
                {
                    "type": "result",
                    "result": "partial",
                    "total_cost_usd": 0,
                }
            ),
        )

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.A_INFRA

    def test_empty_result_field_falls_through_to_fingerprint(
        self,
        tmp_path: Path,
    ) -> None:
        """Agent log is JSON but result field is empty — falls through."""
        task_dir = tmp_path / "empty-result-001"
        data = _make_results(
            task_id="empty-result-001",
            success=False,
            phase="agent",
            error="OOMKill detected in container",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)
        _write_log(
            task_dir,
            "agent_stdout.log",
            json.dumps(
                {
                    "type": "result",
                    "result": "",
                    "total_cost_usd": 0.50,
                }
            ),
        )

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.A_INFRA

    def test_non_json_log_falls_through_to_fingerprint(
        self,
        tmp_path: Path,
    ) -> None:
        """Non-JSON log (plain text error) should still match fingerprint."""
        task_dir = tmp_path / "plain-log-001"
        data = _make_results(
            task_id="plain-log-001",
            success=False,
            phase="agent",
            error="",
            task_score=0.0,
        )
        _write_results_json(task_dir, data)
        _write_log(
            task_dir, "agent_stdout.log", "Cannot connect to the Docker daemon\n"
        )

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.A_INFRA

    def test_agent_output_overrides_timeout_fingerprint(
        self,
        tmp_path: Path,
    ) -> None:
        """Agent completed with result but log mentions 'timed out' in discussion.
        Should be D_agent since agent produced meaningful output."""
        task_dir = tmp_path / "timeout-override-001"
        data = _make_results(
            task_id="timeout-override-001",
            success=True,
            phase="complete",
            error="",
            task_score=0.0,
            all_passed=False,
            checkpoints=[
                {
                    "name": "cp1",
                    "weight": 1.0,
                    "score": 0.0,
                    "passed": False,
                    "duration_ms": 10,
                    "exit_code": 0,
                },
            ],
        )
        _write_results_json(task_dir, data)
        _write_log(
            task_dir,
            "agent_stdout.log",
            self._agent_log_json(
                result_text="The request timed out because the upstream service was slow",
                cost=0.25,
            ),
        )

        result = classify_task(task_dir)
        assert result["category"] == TriageCategory.D_AGENT
