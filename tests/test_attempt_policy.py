"""Unit tests for the attempt-selection policy shared by the two analysis modules.

The integration between them lives in tests/test_cost_tracker.py
(``TestAgreesWithAnalyzeScores``); these pin the primitives that agreement rests
on, so a break here names the cause rather than the symptom.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.attempt_policy import (  # noqa: E402
    ATTEMPT_TIMESTAMP_HOST,
    ATTEMPT_TIMESTAMP_LEGACY_TRACE,
    ATTEMPT_TIMESTAMP_UNDATED,
    RUN_STATUS_INVALID,
    SELECTION_EARLIEST_VALID,
    SELECTION_RULE,
    STUDY_SPEC_SCHEMA_VERSION,
    AttemptPolicy,
    AttemptPolicyError,
    attempt_sort_key,
    instant,
    is_invalid_status,
    load_attempt_policy,
    newer_timestamp,
    read_attempt_timestamp,
    read_trace_timestamp,
)

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts" / "orchestration")
)
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


class TestAttemptTimestamp:
    def _write_results(self, attempt_dir: Path, **fields: object) -> None:
        (attempt_dir / "results.json").write_text(json.dumps(fields))

    def _write_trace(self, attempt_dir: Path, timestamp: str) -> None:
        (attempt_dir / "agent_trace.jsonl").write_text(
            json.dumps({"timestamp": timestamp}) + "\n"
        )

    def test_host_started_at_wins_over_forged_trace(self, tmp_path: Path) -> None:
        self._write_results(tmp_path, started_at="2026-06-01T00:00:00Z")
        self._write_trace(tmp_path, "1970-01-01T00:00:00Z")

        dated = read_attempt_timestamp(tmp_path)

        assert dated.value == "2026-06-01T00:00:00Z"
        assert dated.source == ATTEMPT_TIMESTAMP_HOST

    def test_legacy_result_falls_back_to_trace_with_disclosure(
        self, tmp_path: Path
    ) -> None:
        self._write_results(tmp_path, task_id="legacy")
        self._write_trace(tmp_path, "2025-01-01T00:00:00Z")

        dated = read_attempt_timestamp(tmp_path)

        assert dated.value == "2025-01-01T00:00:00Z"
        assert dated.source == ATTEMPT_TIMESTAMP_LEGACY_TRACE

    def test_malformed_host_timestamp_never_falls_back_to_trace(
        self, tmp_path: Path
    ) -> None:
        self._write_results(tmp_path, started_at="not-a-time")
        self._write_trace(tmp_path, "1970-01-01T00:00:00Z")

        dated = read_attempt_timestamp(tmp_path)

        assert dated.value == ""
        assert dated.source == ATTEMPT_TIMESTAMP_UNDATED


class TestFormatDrift:
    """Timestamps are parsed, not compared as text. A study runs for months
    across CLI versions, and raw string order only matches chronological order
    when every stamp shares one exact format."""

    def test_fractional_seconds_do_not_reorder_an_earlier_attempt(self) -> None:
        """The lexical trap: "." (0x2E) < "Z" (0x5A), so plain string comparison
        ranks the later fractional stamp ahead of the earlier whole-second one."""
        earlier = "2026-01-01T00:00:00Z"
        later = "2026-01-01T00:00:05.123456Z"
        assert later > earlier  # ... as text, which is why text is not used
        assert attempt_sort_key(earlier, "z") < attempt_sort_key(later, "a")

    def test_an_offset_and_a_zulu_stamp_compare_by_instant(self) -> None:
        assert attempt_sort_key("2026-01-01T01:00:00+01:00", "z") == attempt_sort_key(
            "2026-01-01T00:00:00Z", "z"
        )

    def test_a_naive_stamp_is_read_as_utc(self) -> None:
        """Guessing local time would make the order depend on the machine the
        report was generated on."""
        assert instant("2026-01-01T00:00:00") == instant("2026-01-01T00:00:00Z")

    def test_an_unparseable_stamp_sorts_after_every_parseable_one(self) -> None:
        assert attempt_sort_key("not-a-date", "a") > attempt_sort_key(
            "9999-01-01T00:00:00Z", "z"
        )

    def test_a_non_object_trace_line_leaves_the_running_maximum_alone(self) -> None:
        """A line that is valid JSON but not an object carries no timestamp. The
        guard lives at the shared seam so neither reader can crash on input the
        other skips — the drift this helper exists to prevent."""
        assert newer_timestamp([1, 2, 3], "2026-01-01T00:00:00Z") == (
            "2026-01-01T00:00:00Z"
        )
        assert newer_timestamp("a string", "") == ""

    def test_the_running_maximum_uses_the_instant_not_the_text(self) -> None:
        current = "2026-01-01T00:00:05.123456Z"
        assert newer_timestamp({"timestamp": "2026-01-01T00:00:09Z"}, current) == (
            "2026-01-01T00:00:09Z"
        )


class TestTheRuleDisclosesTimestampProvenance:
    def test_the_published_rule_names_host_clock_and_legacy_fallback(self) -> None:
        assert "host-authored results.json.started_at" in SELECTION_RULE
        assert "agent_trace.jsonl" in SELECTION_RULE
        assert "legacy_trace" in SELECTION_RULE


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

    def test_a_corrupt_stamp_does_not_outrank_a_missing_one(self) -> None:
        """Undateable is one class, not two. An absent stamp and an unparseable
        one say exactly as much about when the attempt ran — nothing — so if a
        corrupt stamp sorted ahead of a missing one, writing garbage into
        agent_trace.jsonl would be a cheaper way to win selection than writing a
        plausible early date (EnterpriseBench-rryas.23)."""
        assert attempt_sort_key("not-a-date", "z") > attempt_sort_key("", "a")
        assert attempt_sort_key("not-a-date", "a") < attempt_sort_key("", "z")

    def test_a_corrupt_and_a_missing_stamp_tie_on_run_dir(self) -> None:
        """The consequence of the class being one: the tie falls through to the
        documented run_dir tiebreak rather than to the presence of garbage."""
        assert attempt_sort_key("not-a-date", "a") == attempt_sort_key("", "a")


def _write_spec(path: Path, spec: object) -> Path:
    path.write_text(json.dumps(spec))
    return path


class TestLoadAttemptPolicy:
    """The pin. Every failure here must raise, never fall back to a default:

    a loader that silently substituted the built-in policy for a spec it could
    not read would report a study under a rule the study did not declare, which
    is the whole thing the spec exists to prevent.
    """

    def test_the_shipped_spec_declares_the_implemented_selection(self) -> None:
        """Not a tautology: this is what fails if someone edits configs/study_spec.json
        to a selection the code does not implement, or renames the constant."""
        policy = load_attempt_policy()
        assert policy.selection == SELECTION_EARLIEST_VALID
        assert policy.as_dict()["rule"] == SELECTION_RULE

    def test_a_wellformed_spec_round_trips(self, tmp_path: Path) -> None:
        spec = _write_spec(
            tmp_path / "study_spec.json",
            {
                "schema_version": STUDY_SPEC_SCHEMA_VERSION,
                "attempt_policy": {"selection": SELECTION_EARLIEST_VALID, "version": 1},
            },
        )
        policy = load_attempt_policy(spec)
        assert (policy.selection, policy.version) == (SELECTION_EARLIEST_VALID, 1)
        assert policy.spec_path == str(spec)

    def test_an_unknown_selection_raises(self, tmp_path: Path) -> None:
        """The drift this bead exists to stop. 'highest_score' is not an accepted
        value anywhere in the loader, so the old rule cannot be re-declared."""
        spec = _write_spec(
            tmp_path / "study_spec.json",
            {
                "schema_version": STUDY_SPEC_SCHEMA_VERSION,
                "attempt_policy": {"selection": "highest_score", "version": 1},
            },
        )
        with pytest.raises(AttemptPolicyError, match="highest_score"):
            load_attempt_policy(spec)

    def test_an_unknown_schema_version_raises(self, tmp_path: Path) -> None:
        spec = _write_spec(
            tmp_path / "study_spec.json",
            {
                "schema_version": STUDY_SPEC_SCHEMA_VERSION + 1,
                "attempt_policy": {"selection": SELECTION_EARLIEST_VALID, "version": 1},
            },
        )
        with pytest.raises(AttemptPolicyError, match="schema_version"):
            load_attempt_policy(spec)

    def test_a_missing_attempt_policy_block_raises(self, tmp_path: Path) -> None:
        spec = _write_spec(
            tmp_path / "study_spec.json",
            {"schema_version": STUDY_SPEC_SCHEMA_VERSION},
        )
        with pytest.raises(AttemptPolicyError, match="attempt_policy"):
            load_attempt_policy(spec)

    def test_a_missing_selection_raises(self, tmp_path: Path) -> None:
        spec = _write_spec(
            tmp_path / "study_spec.json",
            {
                "schema_version": STUDY_SPEC_SCHEMA_VERSION,
                "attempt_policy": {"version": 1},
            },
        )
        with pytest.raises(AttemptPolicyError, match="selection"):
            load_attempt_policy(spec)

    @pytest.mark.parametrize("version", ["1", 1.0, None, True, False])
    def test_a_non_integer_policy_version_raises(self, tmp_path: Path, version) -> None:
        """``True`` is the dangerous one: bool subclasses int, so a bare
        isinstance check would accept it and compare equal to 1."""
        spec = _write_spec(
            tmp_path / "study_spec.json",
            {
                "schema_version": STUDY_SPEC_SCHEMA_VERSION,
                "attempt_policy": {
                    "selection": SELECTION_EARLIEST_VALID,
                    "version": version,
                },
            },
        )
        with pytest.raises(AttemptPolicyError, match="version"):
            load_attempt_policy(spec)

    @pytest.mark.parametrize("schema", [True, "1", 1.0, None])
    def test_a_non_integer_schema_version_raises(self, tmp_path: Path, schema) -> None:
        """Same bool trap one level up: ``True == 1`` is True, so a plain
        equality check would read "schema_version": true as version 1."""
        spec = _write_spec(
            tmp_path / "study_spec.json",
            {
                "schema_version": schema,
                "attempt_policy": {"selection": SELECTION_EARLIEST_VALID, "version": 1},
            },
        )
        with pytest.raises(AttemptPolicyError, match="schema_version"):
            load_attempt_policy(spec)

    def test_one_except_clause_catches_both_failure_channels(self) -> None:
        """The loader and the guard must raise one catchable thing, so an entry
        point can wrap "the declared policy is unusable" in a single handler."""
        assert issubclass(AttemptPolicyError, ValueError)
        with pytest.raises(AttemptPolicyError):
            AttemptPolicy(
                selection="highest_score", version=1, spec_path="/x.json"
            ).require_implemented("test")

    def test_a_missing_spec_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AttemptPolicyError, match="not found"):
            load_attempt_policy(tmp_path / "absent.json")

    def test_a_malformed_spec_raises(self, tmp_path: Path) -> None:
        spec = tmp_path / "study_spec.json"
        spec.write_text("{not json")
        with pytest.raises(AttemptPolicyError, match="not valid JSON"):
            load_attempt_policy(spec)

    def test_a_spec_that_is_not_an_object_raises(self, tmp_path: Path) -> None:
        spec = _write_spec(tmp_path / "study_spec.json", [1, 2, 3])
        with pytest.raises(AttemptPolicyError, match="object"):
            load_attempt_policy(spec)

    def test_the_loader_ignores_blocks_it_does_not_own(self, tmp_path: Path) -> None:
        """configs/study_spec.json is shared with the wider Study Capsule
        (EnterpriseBench-rryas.11). Reading only its own key is what lets that
        bead add sibling blocks without this loader rejecting the file."""
        spec = _write_spec(
            tmp_path / "study_spec.json",
            {
                "schema_version": STUDY_SPEC_SCHEMA_VERSION,
                "attempt_policy": {"selection": SELECTION_EARLIEST_VALID, "version": 1},
                "arms": ["baseline", "mcp_only", "cli"],
                "repetitions": 3,
            },
        )
        assert load_attempt_policy(spec).selection == SELECTION_EARLIEST_VALID

    def test_require_implemented_refuses_a_policy_built_in_code(self) -> None:
        """The loader cannot produce such a policy, but a caller can construct
        one; a report must never name a rule its rows were not chosen by."""
        policy = AttemptPolicy(
            selection="highest_score", version=1, spec_path="/x.json"
        )
        with pytest.raises(ValueError, match="highest_score"):
            policy.require_implemented("some_report")

    def test_require_implemented_passes_the_shipped_policy(self) -> None:
        load_attempt_policy().require_implemented("some_report")

    def test_the_policy_is_frozen(self) -> None:
        """It is read once at an entry point and passed down; a stage that could
        rewrite it mid-run would defeat 'pinned before outcomes'."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            load_attempt_policy().selection = "something_else"  # type: ignore[misc]
