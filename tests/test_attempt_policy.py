"""Unit tests for the attempt-selection policy shared by the two analysis modules.

The integration between them lives in tests/test_cost_tracker.py
(``TestAgreesWithAnalyzeScores``); these pin the primitives that agreement rests
on, so a break here names the cause rather than the symptom.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.attempt_policy import (  # noqa: E402
    RUN_STATUS_INVALID,
    attempt_sort_key,
    is_invalid_status,
    newer_timestamp,
    read_trace_timestamp,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "orchestration"))
from run_task import RUN_STATUS_INVALID as ORCHESTRATOR_INVALID  # noqa: E402


def test_the_marker_matches_the_one_the_orchestrator_writes() -> None:
    """Pinned to the writer's constant, not to a literal, so a rename trips here
    and not in a headline number six weeks later (the te9ah failure mode)."""
    assert RUN_STATUS_INVALID == ORCHESTRATOR_INVALID


class TestIsInvalidStatus:
    @pytest.mark.parametrize("status", ["invalid", "INVALID", "Invalid", " invalid "])
    def test_the_marker_excludes_in_any_case_or_padding(self, status: str) -> None:
        assert is_invalid_status(status)

    @pytest.mark.parametrize("status", ["", None, "complete", "VALID", "fallback", 0])
    def test_everything_else_is_not_marked(self, status) -> None:
        """Absent and empty both mean "not marked". A corpus written before the
        field existed must not be dropped wholesale by a stricter reading."""
        assert not is_invalid_status(status)

    def test_a_substring_is_not_the_marker(self) -> None:
        assert not is_invalid_status("invalidated_later")


class TestTimestampReading:
    def test_the_maximum_timestamp_dates_the_attempt(self, tmp_path: Path) -> None:
        lines = [
            {"type": "queue-operation", "timestamp": "2026-01-01T00:00:00Z"},
            {"type": "assistant", "timestamp": "2026-01-01T00:05:00Z"},
            {"type": "user", "timestamp": "2026-01-01T00:02:00Z"},
        ]
        (tmp_path / "agent_trace.jsonl").write_text(
            "".join(json.dumps(entry) + "\n" for entry in lines)
        )
        assert read_trace_timestamp(tmp_path) == "2026-01-01T00:05:00Z"

    def test_a_malformed_line_does_not_abort_the_read(self, tmp_path: Path) -> None:
        (tmp_path / "agent_trace.jsonl").write_text(
            "{not json\n\n" + json.dumps({"timestamp": "2026-02-02T00:00:00Z"}) + "\n"
        )
        assert read_trace_timestamp(tmp_path) == "2026-02-02T00:00:00Z"

    def test_a_missing_trace_leaves_the_attempt_undated(self, tmp_path: Path) -> None:
        assert read_trace_timestamp(tmp_path) == ""

    def test_a_trace_with_no_timestamps_leaves_it_undated(self, tmp_path: Path) -> None:
        (tmp_path / "agent_trace.jsonl").write_text(json.dumps({"type": "x"}) + "\n")
        assert read_trace_timestamp(tmp_path) == ""

    @pytest.mark.parametrize("stamp", [None, 17, {"at": "now"}])
    def test_a_non_string_timestamp_is_ignored(self, stamp) -> None:
        assert newer_timestamp({"timestamp": stamp}, "2026-01-01T00:00:00Z") == (
            "2026-01-01T00:00:00Z"
        )


class TestAttemptSortKey:
    def test_earlier_sorts_first(self) -> None:
        assert attempt_sort_key("2026-01-01T00:00:00Z", "z") < attempt_sort_key(
            "2026-06-01T00:00:00Z", "a"
        )

    def test_equal_timestamps_fall_through_to_run_dir(self) -> None:
        assert attempt_sort_key("T", "a") < attempt_sort_key("T", "b")

    def test_undated_sorts_after_every_dated_attempt(self) -> None:
        """The trap: "" is the smallest string, so a plain tuple would rank an
        attempt that could not be dated ahead of every one that could."""
        assert attempt_sort_key("", "a") > attempt_sort_key("1970-01-01T00:00:00Z", "z")
