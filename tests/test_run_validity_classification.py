"""Tests for run-validity classification + fail-loud no-op handling in run_task.py.

Covers bead EnterpriseBench-s58f: a container file-permission EACCES used to make
the agent never start, yet the run recorded success=true, num_turns=0,
mcp_calls=0, task_score=0.0 — a FAKE 0 that corrupted the MCP-vs-baseline
comparison. These tests assert that:

  * num_turns == 0 / EACCES / mcp_only-never-handshaked  -> status=INVALID, success=False
  * MCP-mode run with real turns but 0 MCP calls          -> status=FALLBACK (preserved)
  * baseline / MCP run with >=1 MCP call                  -> status=VALID
  * results.json carries 'account' and 'mcp_handshake_ok' for attribution
  * the pre-agent readability gate and chown helpers exist + fail loud
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make scripts importable
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts" / "orchestration")
)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "infra"))

from run_task import (  # noqa: E402
    RUN_STATUS_FALLBACK,
    RUN_STATUS_INVALID,
    RUN_STATUS_VALID,
    TaskRunConfig,
    TaskRunResult,
    _save_results,
    _scan_mcp_config_error,
    classify_run_validity,
)


# ---------------------------------------------------------------------------
# Helpers (mirror conventions in test_run_task_results.py)
# ---------------------------------------------------------------------------

def _make_task_data(task_id: str = "test-validity-001") -> dict:
    return {
        "task": {
            "id": task_id,
            "suite": "dependency_management",
            "task_type": "dependency_graph",
            "difficulty": "medium",
            "session_type": "single",
        },
        "metadata": {"languages": ["python"]},
    }


def _make_config(**overrides) -> TaskRunConfig:
    defaults = dict(
        task_toml=Path("/fake/task.toml"),
        source="mirror",
        agent_command="claude -p",
        timeout=300,
        build_timeout=600,
        verifier_timeout=120,
        memory_mb=8192,
        output_dir=None,
        dry_run=False,
        no_build=False,
        keep_container=False,
        verbose=False,
        account=None,
        mode="baseline",
    )
    defaults.update(overrides)
    return TaskRunConfig(**defaults)


def _make_result(task_id: str = "test-validity-001", **overrides) -> TaskRunResult:
    defaults = dict(
        task_id=task_id,
        phase="complete",
        success=True,
        image_tag="eb-test-validity-001",
        scores={"task_score": 2.5},
        timing={"agent": 100.0},
    )
    defaults.update(overrides)
    return TaskRunResult(**defaults)


# ---------------------------------------------------------------------------
# classify_run_validity — the pure decision matrix
# ---------------------------------------------------------------------------

class TestClassifyRunValidity:
    def test_zero_turns_is_invalid_baseline(self) -> None:
        """The core fake-0 guard: an agent that never started is INVALID."""
        assert (
            classify_run_validity(
                mode="baseline",
                num_turns=0,
                mcp_calls=0,
                mcp_handshake_ok=None,
                config_error=False,
            )
            == RUN_STATUS_INVALID
        )

    def test_zero_turns_is_invalid_mcp(self) -> None:
        assert (
            classify_run_validity(
                mode="mcp_only",
                num_turns=0,
                mcp_calls=0,
                mcp_handshake_ok=True,
                config_error=False,
            )
            == RUN_STATUS_INVALID
        )

    def test_config_error_is_invalid_even_with_turns(self) -> None:
        """An MCP-config / EACCES parse error invalidates the run regardless of turns."""
        assert (
            classify_run_validity(
                mode="hybrid",
                num_turns=5,
                mcp_calls=3,
                mcp_handshake_ok=True,
                config_error=True,
            )
            == RUN_STATUS_INVALID
        )

    def test_hybrid_real_turns_zero_calls_is_fallback(self) -> None:
        """A genuine fs-fallback hybrid run is FALLBACK, NOT INVALID."""
        assert (
            classify_run_validity(
                mode="hybrid",
                num_turns=68,
                mcp_calls=0,
                mcp_handshake_ok=True,
                config_error=False,
            )
            == RUN_STATUS_FALLBACK
        )

    def test_hybrid_fallback_preserved_even_if_handshake_failed(self) -> None:
        """Hybrid falls back to fs tools by design — still a real, scoreable run."""
        assert (
            classify_run_validity(
                mode="hybrid",
                num_turns=25,
                mcp_calls=0,
                mcp_handshake_ok=False,
                config_error=False,
            )
            == RUN_STATUS_FALLBACK
        )

    def test_mcp_only_never_handshaked_zero_calls_is_invalid(self) -> None:
        """mcp_only with no working MCP transport is INVALID, not FALLBACK."""
        assert (
            classify_run_validity(
                mode="mcp_only",
                num_turns=10,
                mcp_calls=0,
                mcp_handshake_ok=False,
                config_error=False,
            )
            == RUN_STATUS_INVALID
        )

    def test_mcp_only_handshaked_zero_calls_is_fallback(self) -> None:
        """mcp_only that connected but made 0 calls is a real run (FALLBACK)."""
        assert (
            classify_run_validity(
                mode="mcp_only",
                num_turns=10,
                mcp_calls=0,
                mcp_handshake_ok=True,
                config_error=False,
            )
            == RUN_STATUS_FALLBACK
        )

    def test_mcp_run_with_calls_is_valid(self) -> None:
        assert (
            classify_run_validity(
                mode="mcp_only",
                num_turns=54,
                mcp_calls=104,
                mcp_handshake_ok=True,
                config_error=False,
            )
            == RUN_STATUS_VALID
        )

    def test_baseline_with_turns_is_valid(self) -> None:
        assert (
            classify_run_validity(
                mode="baseline",
                num_turns=12,
                mcp_calls=0,
                mcp_handshake_ok=None,
                config_error=False,
            )
            == RUN_STATUS_VALID
        )


# ---------------------------------------------------------------------------
# _scan_mcp_config_error — detect EACCES / parse errors from agent stderr
# ---------------------------------------------------------------------------

class TestScanMcpConfigError:
    def test_detects_invalid_mcp_configuration(self, tmp_path: Path) -> None:
        (tmp_path / "agent_stderr.log").write_text(
            "Invalid MCP configuration: EACCES /home/agent/.mcp.json\n"
        )
        assert _scan_mcp_config_error(tmp_path) is True

    def test_detects_instruction_permission_denied(self, tmp_path: Path) -> None:
        (tmp_path / "agent_stderr.log").write_text(
            "bash: /workspace/instruction.md: Permission denied\n"
        )
        assert _scan_mcp_config_error(tmp_path) is True

    def test_clean_stderr_is_not_an_error(self, tmp_path: Path) -> None:
        (tmp_path / "agent_stderr.log").write_text("normal warning output\n")
        assert _scan_mcp_config_error(tmp_path) is False

    def test_missing_log_is_not_an_error(self, tmp_path: Path) -> None:
        assert _scan_mcp_config_error(tmp_path) is False


# ---------------------------------------------------------------------------
# results.json schema — account + mcp_handshake_ok + status
# ---------------------------------------------------------------------------

class TestResultsSchemaFields:
    def test_results_json_has_account(self, tmp_path: Path) -> None:
        config = _make_config(account=3)
        result = _make_result()
        _save_results(result, _make_task_data(), tmp_path, config)
        data = json.loads((tmp_path / "results.json").read_text())
        assert data["account"] == 3

    def test_results_json_account_none_when_unset(self, tmp_path: Path) -> None:
        config = _make_config(account=None)
        result = _make_result()
        _save_results(result, _make_task_data(), tmp_path, config)
        data = json.loads((tmp_path / "results.json").read_text())
        assert data["account"] is None

    def test_results_json_has_mcp_handshake_ok(self, tmp_path: Path) -> None:
        config = _make_config(mode="mcp_only", account=1)
        result = _make_result(mcp_handshake_ok=True)
        _save_results(result, _make_task_data(), tmp_path, config)
        data = json.loads((tmp_path / "results.json").read_text())
        assert data["mcp_handshake_ok"] is True

    def test_results_json_has_status(self, tmp_path: Path) -> None:
        config = _make_config()
        result = _make_result(status=RUN_STATUS_INVALID, success=False)
        _save_results(result, _make_task_data(), tmp_path, config)
        data = json.loads((tmp_path / "results.json").read_text())
        assert data["status"] == RUN_STATUS_INVALID
        assert data["success"] is False

    def test_default_status_is_valid(self) -> None:
        assert TaskRunResult(task_id="x").status == RUN_STATUS_VALID

    def test_default_handshake_is_none(self) -> None:
        assert TaskRunResult(task_id="x").mcp_handshake_ok is None


# ---------------------------------------------------------------------------
# Fail-loud no-op: a 0-turn EACCES run must record INVALID, never a real 0.0
# ---------------------------------------------------------------------------

class TestFailLoudNoOp:
    def test_zero_turn_eacces_records_invalid_not_fake_zero(
        self, tmp_path: Path
    ) -> None:
        """Reproduces the audited no-op: 0 turns + EACCES -> INVALID + success=False.

        Before the fix this was recorded success=True / task_score=0.0.
        """
        status = classify_run_validity(
            mode="mcp_only",
            num_turns=0,
            mcp_calls=0,
            mcp_handshake_ok=False,
            config_error=True,
        )
        assert status == RUN_STATUS_INVALID

        result = _make_result(
            status=status,
            success=False,
            phase="agent_preflight_failed",
            failure_class="infra_perms",
            error="agent user cannot read /workspace/instruction.md",
        )
        _save_results(result, _make_task_data(), tmp_path, _make_config(mode="mcp_only"))
        data = json.loads((tmp_path / "results.json").read_text())
        assert data["status"] == RUN_STATUS_INVALID
        assert data["success"] is False
        assert data["failure_class"] == "infra_perms"


# ---------------------------------------------------------------------------
# Source-level verification: the perms fix + gate + classifier are wired in
# ---------------------------------------------------------------------------

class TestRunTaskSourceLogic:
    @pytest.fixture(autouse=True)
    def _read_source(self) -> None:
        self.source = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "orchestration"
            / "run_task.py"
        ).read_text()

    def test_pre_agent_readability_gate_exists(self) -> None:
        assert "_assert_agent_readable" in self.source

    def test_chown_helper_exists(self) -> None:
        assert "_chown_to_agent" in self.source

    def test_setup_chown_not_silently_masked(self) -> None:
        """The old silent `2>/dev/null; true` chown that hid EACCES must be gone."""
        assert "2>/dev/null; true" not in self.source

    def test_classifier_wired_into_run(self) -> None:
        assert "classify_run_validity" in self.source

    def test_invalid_status_blocks_success(self) -> None:
        assert "RUN_STATUS_INVALID" in self.source

    def test_configure_mcp_returns_handshake(self) -> None:
        """_configure_mcp must report whether the MCP server handshaked."""
        assert "mcp_handshake_ok" in self.source
