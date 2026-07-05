"""Tests for MCP instruction preamble injection in run_task.py.

Verifies:
  - instruction_mcp.md content is prepended for mcp_only and hybrid modes
  - instruction_mcp.md is NOT prepended for baseline mode
  - Mode-specific header lines are included for mcp_only and hybrid
  - Missing instruction_mcp.md is handled gracefully (header still appears)
  - Missing instruction.md returns None
  - _setup_container passes mode through correctly
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make scripts importable
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts" / "orchestration")
)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "infra"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from run_task import _build_instruction_text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MCP_ONLY_HEADER = (
    "**IMPORTANT: Local source files are not present in /workspace. "
    "You MUST use Sourcegraph MCP tools for all code access.**"
)

HYBRID_HEADER = "# Sourcegraph MCP Tools Available"


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    """Create a minimal task directory with instruction.md."""
    (tmp_path / "instruction.md").write_text("# Task\nDo the thing.\n")
    return tmp_path


@pytest.fixture()
def task_dir_with_mcp(task_dir: Path) -> Path:
    """Task directory that also has instruction_mcp.md."""
    (task_dir / "instruction_mcp.md").write_text(
        "# MCP Tools\nUse sg_keyword_search to find code.\n"
    )
    return task_dir


# ---------------------------------------------------------------------------
# Baseline mode
# ---------------------------------------------------------------------------


class TestBaselineMode:
    def test_baseline_does_not_prepend_mcp_content(
        self, task_dir_with_mcp: Path
    ) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "baseline")
        assert result is not None
        assert "MCP Tools" not in result
        assert "sg_keyword_search" not in result

    def test_baseline_does_not_include_mcp_header(self, task_dir: Path) -> None:
        result = _build_instruction_text(task_dir, "baseline")
        assert result is not None
        assert MCP_ONLY_HEADER not in result
        assert HYBRID_HEADER not in result

    def test_baseline_includes_instruction_content(self, task_dir: Path) -> None:
        result = _build_instruction_text(task_dir, "baseline")
        assert result is not None
        assert "# Task" in result
        assert "Do the thing." in result

    def test_baseline_includes_output_appendix(self, task_dir: Path) -> None:
        result = _build_instruction_text(task_dir, "baseline")
        assert result is not None
        assert "## Output Requirements" in result


# ---------------------------------------------------------------------------
# mcp_only mode
# ---------------------------------------------------------------------------


class TestMcpOnlyMode:
    def test_mcp_only_prepends_mcp_content(self, task_dir_with_mcp: Path) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "mcp_only")
        assert result is not None
        assert "MCP Tools" in result
        assert "sg_keyword_search" in result

    def test_mcp_only_includes_header(self, task_dir_with_mcp: Path) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "mcp_only")
        assert result is not None
        assert MCP_ONLY_HEADER in result

    def test_mcp_only_does_not_include_hybrid_header(
        self, task_dir_with_mcp: Path
    ) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "mcp_only")
        assert result is not None
        assert HYBRID_HEADER not in result

    def test_mcp_only_preamble_before_instruction(
        self, task_dir_with_mcp: Path
    ) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "mcp_only")
        assert result is not None
        mcp_pos = result.index("sg_keyword_search")
        task_pos = result.index("# Task")
        assert mcp_pos < task_pos, "MCP preamble must appear before instruction body"

    def test_mcp_only_includes_instruction_content(
        self, task_dir_with_mcp: Path
    ) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "mcp_only")
        assert result is not None
        assert "Do the thing." in result

    def test_mcp_only_includes_output_appendix(self, task_dir_with_mcp: Path) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "mcp_only")
        assert result is not None
        assert "## Output Requirements" in result

    def test_mcp_only_without_mcp_file_still_has_header(self, task_dir: Path) -> None:
        """Even without instruction_mcp.md, the mode header should appear."""
        result = _build_instruction_text(task_dir, "mcp_only")
        assert result is not None
        assert MCP_ONLY_HEADER in result


# ---------------------------------------------------------------------------
# hybrid mode
# ---------------------------------------------------------------------------


class TestHybridMode:
    def test_hybrid_prepends_mcp_content(self, task_dir_with_mcp: Path) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "hybrid")
        assert result is not None
        assert "MCP Tools" in result

    def test_hybrid_includes_header(self, task_dir_with_mcp: Path) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "hybrid")
        assert result is not None
        assert HYBRID_HEADER in result

    def test_hybrid_does_not_include_mcp_only_header(
        self, task_dir_with_mcp: Path
    ) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "hybrid")
        assert result is not None
        assert MCP_ONLY_HEADER not in result

    def test_hybrid_preamble_before_instruction(self, task_dir_with_mcp: Path) -> None:
        result = _build_instruction_text(task_dir_with_mcp, "hybrid")
        assert result is not None
        mcp_pos = result.index("sg_keyword_search")
        task_pos = result.index("# Task")
        assert mcp_pos < task_pos

    def test_hybrid_without_mcp_file_still_has_header(self, task_dir: Path) -> None:
        result = _build_instruction_text(task_dir, "hybrid")
        assert result is not None
        assert HYBRID_HEADER in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_missing_instruction_md_returns_none(self, tmp_path: Path) -> None:
        result = _build_instruction_text(tmp_path, "baseline")
        assert result is None

    def test_missing_instruction_md_returns_none_mcp_mode(self, tmp_path: Path) -> None:
        result = _build_instruction_text(tmp_path, "mcp_only")
        assert result is None

    def test_separator_between_preamble_and_instruction(
        self, task_dir_with_mcp: Path
    ) -> None:
        """There should be a --- separator between preamble and instruction body."""
        result = _build_instruction_text(task_dir_with_mcp, "mcp_only")
        assert result is not None
        # Find the separator between preamble and instruction
        # The preamble ends, then ---, then instruction begins
        parts = result.split("---")
        assert len(parts) >= 2, "Expected at least one --- separator"


# ---------------------------------------------------------------------------
# _setup_container passes mode
# ---------------------------------------------------------------------------


class TestSetupContainerPassesMode:
    """Verify _setup_container calls _build_instruction_text with the correct mode."""

    def test_setup_container_passes_mode_to_build(self, task_dir: Path) -> None:
        with patch(
            "run_task._build_instruction_text", return_value=None
        ) as mock_build, patch("run_task._docker_exec"), patch("run_task._docker_cp"):
            from run_task import _setup_container

            _setup_container("fake-container", task_dir, {}, mode="hybrid")
            mock_build.assert_called_once_with(
                task_dir, "hybrid", repos=[], require_grounded_citations=False
            )

    def test_setup_container_defaults_to_baseline(self, task_dir: Path) -> None:
        with patch(
            "run_task._build_instruction_text", return_value=None
        ) as mock_build, patch("run_task._docker_exec"), patch("run_task._docker_cp"):
            from run_task import _setup_container

            _setup_container("fake-container", task_dir, {})
            mock_build.assert_called_once_with(
                task_dir, "baseline", repos=[], require_grounded_citations=False
            )

    def test_setup_container_passes_require_grounded_citations_true(
        self, task_dir: Path
    ) -> None:
        with patch(
            "run_task._build_instruction_text", return_value=None
        ) as mock_build, patch("run_task._docker_exec"), patch("run_task._docker_cp"):
            from run_task import _setup_container

            task_data = {"ground_truth": {"require_grounded_citations": True}}
            _setup_container("fake-container", task_dir, task_data)
            mock_build.assert_called_once_with(
                task_dir, "baseline", repos=[], require_grounded_citations=True
            )


# ---------------------------------------------------------------------------
# answer.json appendix citation-awareness
# ---------------------------------------------------------------------------


class TestAnswerAppendixCitations:
    """require_grounded_citations must add citations guidance to the answer.json
    appendix, mirroring the schema lib/eb_verify/plugins/answer.py's groundedness
    gate expects (top-level `citations` list of {repo, file, evidence_span})."""

    def test_flag_true_adds_citations_guidance(self, task_dir: Path) -> None:
        result = _build_instruction_text(
            task_dir, "baseline", require_grounded_citations=True
        )
        assert result is not None
        assert "answer.json" in result
        assert "citations" in result
        assert "evidence_span" in result

    def test_flag_false_omits_citations_guidance(self, task_dir: Path) -> None:
        result = _build_instruction_text(
            task_dir, "baseline", require_grounded_citations=False
        )
        assert result is not None
        assert "answer.json" in result
        assert "citations" not in result
        assert "evidence_span" not in result

    def test_flag_defaults_to_false(self, task_dir: Path) -> None:
        """Existing callers that don't pass the new param keep current behavior."""
        result = _build_instruction_text(task_dir, "baseline")
        assert result is not None
        assert "citations" not in result

    def test_flag_true_requires_verbatim_evidence(self, task_dir: Path) -> None:
        result = _build_instruction_text(
            task_dir, "baseline", require_grounded_citations=True
        )
        assert result is not None
        assert "verbatim" in result.lower()

    def test_flag_true_span_length_matches_groundedness_gate(
        self, task_dir: Path
    ) -> None:
        """The advertised minimum evidence-span length must track
        eb_verify.groundedness.MIN_SPAN_CHARS, not a hardcoded copy — otherwise
        the appendix can silently drift out of sync with what the gate enforces."""
        from eb_verify.groundedness import MIN_SPAN_CHARS

        result = _build_instruction_text(
            task_dir, "baseline", require_grounded_citations=True
        )
        assert result is not None
        assert f">={MIN_SPAN_CHARS} characters" in result
