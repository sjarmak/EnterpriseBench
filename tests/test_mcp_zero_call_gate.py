"""Tests for the zero-MCP-call gate and trace/status integrity in run_task.py.

An ``mcp_only`` run that made 0 MCP tool calls had baseline tool access under
an MCP label, so it is routed to the infra-error re-run channel rather than
scored into the mcp_only mean.

``hybrid`` is deliberately NOT gated: that mode grants both toolsets, so 0 MCP
calls is a legitimate agent choice. Invalidating those runs would delete
exactly the cases where the agent preferred local tools and would bias the
hybrid mean upward.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts" / "orchestration")
)

import run_task
from run_task import (
    RUN_STATUS_INVALID,
    TaskRunConfig,
    TaskRunResult,
    _record_agent_trace,
    _route_zero_mcp_run,
    _save_results,
)


def _result(mcp_calls: int) -> TaskRunResult:
    return TaskRunResult(
        task_id="incident-investigation-002",
        phase="",
        tool_usage={"mcp_tool_calls": mcp_calls},
    )


class TestZeroMcpGateMcpOnly:
    """mcp_only with 0 MCP calls is an infra failure, not a score."""

    def test_marks_run_invalid(self) -> None:
        result = _result(0)

        _route_zero_mcp_run(result, "mcp_only")

        assert result.status == RUN_STATUS_INVALID
        assert result.failure_class == "infra_mcp_unused"
        assert result.success is False
        assert result.tool_usage["mcp_used"] is False

    def test_phase_excludes_run_from_the_headline(self) -> None:
        """phase must land outside 'complete' — that is what actually excludes.

        recompute_headline_uu17.py keeps only phase == 'complete' and
        success is True, and run_task's phase-complete guard skips any phase
        already in the infra-error set.
        """
        result = _result(0)

        _route_zero_mcp_run(result, "mcp_only")

        assert result.phase == "agent_infra_error"
        assert result.phase != "complete"

    def test_records_a_reason_on_the_result(self) -> None:
        result = _result(0)

        _route_zero_mcp_run(result, "mcp_only")

        assert "mcp_only" in result.error
        assert result.error != ""

    def test_does_not_relabel_an_already_invalid_run(self) -> None:
        """A broken MCP config is the root cause; 0 calls is just its symptom.

        The config gate runs first and classifies the run infra_mcp_config. The
        agent then makes 0 MCP calls *because* of it, and relabelling the run
        infra_mcp_unused would bury the actual cause in the re-run channel.
        """
        result = _result(0)
        result.status = RUN_STATUS_INVALID
        result.failure_class = "infra_mcp_config"
        result.phase = "agent_infra_error"

        _route_zero_mcp_run(result, "mcp_only")

        assert result.failure_class == "infra_mcp_config"
        assert result.status == RUN_STATUS_INVALID
        assert result.tool_usage["mcp_used"] is False

    @pytest.mark.parametrize(
        "root_cause",
        ["infra_oom", "infra_timeout", "agent_error"],
    )
    def test_preserves_a_root_cause_that_never_set_status(
        self, root_cause: str
    ) -> None:
        """OOM / timeout / crash set failure_class but NOT status.

        Each of those trivially produces 0 MCP calls, so a status-only guard
        would relabel them infra_mcp_unused and send triage chasing a phantom
        MCP problem. The run must still be excluded, but keep its real cause.
        """
        result = _result(0)
        result.failure_class = root_cause

        _route_zero_mcp_run(result, "mcp_only")

        assert result.failure_class == root_cause
        assert result.status == RUN_STATUS_INVALID  # still excluded
        assert result.phase == "agent_infra_error"
        assert result.success is False

    def test_run_with_mcp_calls_is_untouched(self) -> None:
        result = _result(7)

        _route_zero_mcp_run(result, "mcp_only")

        assert result.status == ""
        assert result.phase == ""
        assert result.failure_class is None
        assert result.tool_usage["mcp_used"] is True


class TestZeroMcpGateHybrid:
    """hybrid grants both toolsets — 0 MCP calls stays a scoreable run."""

    def test_zero_calls_flagged_but_still_scored(self) -> None:
        result = _result(0)

        _route_zero_mcp_run(result, "hybrid")

        assert result.tool_usage["mcp_used"] is False
        assert result.status == ""
        assert result.phase == ""
        assert result.failure_class is None
        assert result.success is False  # untouched default, set later by the run

    def test_calls_present_marks_mcp_used(self) -> None:
        result = _result(3)

        _route_zero_mcp_run(result, "hybrid")

        assert result.tool_usage["mcp_used"] is True
        assert result.status == ""


class TestZeroMcpGateBaseline:
    """baseline has no MCP at all — the gate must not touch it."""

    @pytest.mark.parametrize("mcp_calls", [0, 4])
    def test_baseline_is_never_gated_or_flagged(self, mcp_calls: int) -> None:
        result = _result(mcp_calls)

        _route_zero_mcp_run(result, "baseline")

        assert result.status == ""
        assert result.phase == ""
        assert result.failure_class is None
        assert "mcp_used" not in result.tool_usage


class TestRecordAgentTrace:
    """The trace-capture result must be recorded, not discarded."""

    def test_successful_capture_records_true(self, tmp_path: Path) -> None:
        result = _result(1)

        with patch.object(run_task, "_copy_agent_trace", return_value=True):
            _record_agent_trace(result, "container-123", tmp_path)

        assert result.tool_usage["trace_captured"] is True

    def test_missing_trace_records_false(self, tmp_path: Path) -> None:
        """A missing trace must be visible on the result, not silently pass."""
        result = _result(1)

        with patch.object(run_task, "_copy_agent_trace", return_value=False):
            _record_agent_trace(result, "container-123", tmp_path)

        assert result.tool_usage["trace_captured"] is False


class TestStatusIsPersisted:
    """An INVALID run must be identifiable from the artifacts alone."""

    @staticmethod
    def _save(tmp_path: Path, result: TaskRunResult) -> Path:
        config = TaskRunConfig(task_toml=tmp_path / "task.toml", mode="mcp_only")
        _save_results(result, {}, tmp_path, config)
        return tmp_path

    def test_invalid_status_lands_in_both_artifacts(self, tmp_path: Path) -> None:
        result = _result(0)
        _route_zero_mcp_run(result, "mcp_only")

        out = self._save(tmp_path, result)

        results = json.loads((out / "results.json").read_text())
        metrics = json.loads((out / "task_metrics.json").read_text())
        assert results["status"] == RUN_STATUS_INVALID
        assert metrics["status"] == RUN_STATUS_INVALID
        assert results["failure_class"] == "infra_mcp_unused"
        assert results["tool_usage"]["mcp_used"] is False

    def test_valid_run_persists_empty_status(self, tmp_path: Path) -> None:
        result = _result(5)
        _route_zero_mcp_run(result, "mcp_only")
        result.phase = "complete"
        result.success = True

        out = self._save(tmp_path, result)

        results = json.loads((out / "results.json").read_text())
        assert results["status"] == ""
        assert results["phase"] == "complete"

    @pytest.mark.parametrize(
        "phase",
        [
            # inline-flagged phases that reach the completion guard
            "agent_infra_error",
            "verifier_infra_error",
            # early-returning failure phases that set only phase/success — these
            # are exactly the ones an allow-list version of the field missed
            "agent_preflight_failed",
            "preflight_failed",
            "build_failed",
            "setup_failed",
            "mcp_infra_error",
            "error",
        ],
    )
    def test_infra_phase_persists_invalid_even_when_status_unset(
        self, tmp_path: Path, phase: str
    ) -> None:
        """status is derived from phase/success, so any failed-short-of-complete
        run lands as INVALID on disk without its branch remembering to set it.

        OOM, timeout, build-failed and setup-failed branches set only
        phase/success. Persisting the raw status field would leave those runs
        looking scoreable in the artifacts.
        """
        result = _result(3)
        result.phase = phase
        result.success = False
        assert result.status == ""  # nothing set it

        out = self._save(tmp_path, result)

        results = json.loads((out / "results.json").read_text())
        metrics = json.loads((out / "task_metrics.json").read_text())
        assert results["status"] == RUN_STATUS_INVALID
        assert metrics["status"] == RUN_STATUS_INVALID

    def test_dry_run_is_not_marked_invalid(self, tmp_path: Path) -> None:
        """A dry run completes with success=True — excluded from scoring but not
        an infra failure, so it must NOT persist status=invalid.

        This is the case a blanket 'phase != complete' rule would misclassify.
        """
        result = _result(0)
        result.phase = "dry_run_complete"
        result.success = True

        out = self._save(tmp_path, result)

        results = json.loads((out / "results.json").read_text())
        assert results["status"] == ""


def _assistant(*blocks: dict) -> str:
    """A stream-json assistant record carrying content blocks."""
    return json.dumps({"type": "assistant", "message": {"content": list(blocks)}})


def _tool_use(name: str) -> dict:
    return {"type": "tool_use", "id": "toolu_01ABC", "name": name, "input": {}}


def _usage(tmp_path: Path, stdout: str) -> dict:
    (tmp_path / "agent_stdout.log").write_text(stdout)
    return run_task._extract_tool_usage(tmp_path)


class TestMcpToolCallCounting:
    """mcp_tool_calls counts genuine tool_use records — never prose.

    The count feeds _route_zero_mcp_run, which invalidates an mcp_only run with
    0 MCP calls. A mere *mention* of the tool name — narration, an error string,
    a tool_result echo — must not make a genuinely-zero-MCP run look non-zero:
    that run would slip past the gate and into the mcp_only mean.
    """

    def test_prose_mention_in_assistant_text_is_not_a_call(
        self, tmp_path: Path
    ) -> None:
        stream = _assistant(
            {
                "type": "text",
                "text": "I could use mcp__sourcegraph__search_code, but Grep is faster.",
            }
        )

        assert _usage(tmp_path, stream)["mcp_tool_calls"] == 0

    def test_tool_result_echo_is_not_a_call(self, tmp_path: Path) -> None:
        stream = json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": (
                                "Error: mcp__sourcegraph__search_code is not "
                                "available in this session"
                            ),
                        }
                    ]
                },
            }
        )

        assert _usage(tmp_path, stream)["mcp_tool_calls"] == 0

    def test_nested_tool_use_block_counts(self, tmp_path: Path) -> None:
        stream = _assistant(_tool_use("mcp__sourcegraph__search_code"))

        assert _usage(tmp_path, stream)["mcp_tool_calls"] == 1

    def test_multiple_blocks_in_one_message_all_count(self, tmp_path: Path) -> None:
        stream = _assistant(
            {"type": "text", "text": "searching now"},
            _tool_use("mcp__sourcegraph__search_code"),
            _tool_use("mcp__sourcegraph__read_file"),
        )

        assert _usage(tmp_path, stream)["mcp_tool_calls"] == 2

    def test_flat_tool_use_record_counts(self, tmp_path: Path) -> None:
        """Some trace shapes emit tool_use as a top-level record, not nested."""
        stream = json.dumps(
            {"type": "tool_use", "name": "mcp__sourcegraph__nls_search", "input": {}}
        )

        assert _usage(tmp_path, stream)["mcp_tool_calls"] == 1

    def test_unknown_sourcegraph_tool_still_counts(self, tmp_path: Path) -> None:
        """Prefix match, not an allow-list.

        A gate that INVALIDATES on zero must not invalidate a real MCP run just
        because the agent used a sourcegraph tool added after this code shipped.
        """
        stream = _assistant(_tool_use("mcp__sourcegraph__brand_new_tool"))

        assert _usage(tmp_path, stream)["mcp_tool_calls"] == 1

    def test_non_sourcegraph_mcp_tool_does_not_count(self, tmp_path: Path) -> None:
        stream = _assistant(_tool_use("mcp__other__do_thing"))

        assert _usage(tmp_path, stream)["mcp_tool_calls"] == 0

    @pytest.mark.parametrize(
        "tool_name",
        ["mcp__sourcegraphql__query", "mcp__sourcegraph_public__search"],
    )
    def test_foreign_server_sharing_the_name_prefix_does_not_count(
        self, tmp_path: Path, tool_name: str
    ) -> None:
        """The server name must match whole, not as a prefix of a longer one.

        The sandbox registers exactly one server, `sourcegraph`, so a tool from
        any other server is not a Sourcegraph MCP call — even if that server's
        name happens to start with `sourcegraph`.
        """
        stream = _assistant(_tool_use(tool_name))

        assert _usage(tmp_path, stream)["mcp_tool_calls"] == 0

    def test_local_tool_does_not_count(self, tmp_path: Path) -> None:
        stream = _assistant(_tool_use("Grep"))

        assert _usage(tmp_path, stream)["mcp_tool_calls"] == 0


class TestUsageParsingAcrossOutputFormats:
    """Token/turn accounting must survive whatever --output-format was used.

    One record walk now serves both formats, where two duplicated parse paths
    (whole-file early return plus per-line scan) used to.
    """

    def test_whole_file_json_parses_usage(self, tmp_path: Path) -> None:
        """--output-format json emits one result object and no tool records.

        0 MCP calls is the correct count for it: tool_use records do not exist in
        that format, and the tool names its result *text* mentions are exactly the
        false positive being removed. The default agent command uses stream-json.
        """
        payload = json.dumps(
            {
                "modelUsage": {"claude": {"inputTokens": 10, "outputTokens": 5}},
                "numTurns": 3,
                "total_cost_usd": 0.25,
                "result": "used mcp__sourcegraph__search_code then read the file",
            }
        )

        usage = _usage(tmp_path, payload)

        assert usage["mcp_tool_calls"] == 0
        assert usage["num_turns"] == 3
        assert usage["total_input_tokens"] == 10
        assert usage["total_output_tokens"] == 5
        assert usage["cost_usd"] == 0.25  # falls back to total_cost_usd

    def test_stream_json_parses_usage_alongside_calls(self, tmp_path: Path) -> None:
        stream = (
            _assistant(_tool_use("mcp__sourcegraph__search_code"))
            + "\n"
            + json.dumps(
                {
                    "modelUsage": {"claude": {"inputTokens": 12, "outputTokens": 7}},
                    "num_turns": 2,
                }
            )
            + "\n"
        )

        usage = _usage(tmp_path, stream)

        assert usage["mcp_tool_calls"] == 1
        assert usage["num_turns"] == 2
        assert usage["total_input_tokens"] == 12
        assert usage["total_output_tokens"] == 7

    def test_non_json_noise_lines_are_skipped(self, tmp_path: Path) -> None:
        """Container logs interleave plain-text lines with the JSON stream."""
        stream = (
            "starting agent...\n"
            + _assistant(_tool_use("mcp__sourcegraph__read_file"))
            + "\n"
            "not json at all\n"
            '{"broken": \n'
            + json.dumps({"num_turns": 4})
            + "\n"
        )

        usage = _usage(tmp_path, stream)

        assert usage["mcp_tool_calls"] == 1
        assert usage["num_turns"] == 4

    def test_missing_log_reports_zeroes(self, tmp_path: Path) -> None:
        usage = run_task._extract_tool_usage(tmp_path)

        assert usage["mcp_tool_calls"] == 0
        assert usage["num_turns"] == 0
        assert usage["cost_usd"] == 0.0
