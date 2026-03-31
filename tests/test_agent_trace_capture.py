"""Tests for agent conversation trace capture from container.

Covers the _copy_agent_trace() function that extracts Claude Code session
JSONL from /home/agent/.claude/projects/ inside the Docker container.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Import will work once the function exists
from scripts.orchestration.run_task import _copy_agent_trace


class TestCopyAgentTrace:
    """Unit tests for _copy_agent_trace()."""

    def test_copies_trace_file_when_found(self, tmp_path: Path) -> None:
        """Should find and copy the JSONL trace file from the container."""
        output_dir = tmp_path / "results"
        output_dir.mkdir()

        # Mock: `docker exec ... find ...` returns a path
        find_result = MagicMock()
        find_result.returncode = 0
        find_result.stdout = "/home/agent/.claude/projects/abc123/conversation.jsonl\n"

        # Mock: `docker cp ...` succeeds
        cp_result = MagicMock()
        cp_result.returncode = 0
        cp_result.stderr = ""

        with patch("scripts.orchestration.run_task.subprocess.run") as mock_run:
            mock_run.side_effect = [find_result, cp_result]
            result = _copy_agent_trace("container-123", output_dir)

        assert result is True
        # Verify find command was called
        find_call = mock_run.call_args_list[0]
        assert "find" in find_call[0][0] or "find" in str(find_call)

    def test_returns_false_when_no_trace_found(self, tmp_path: Path) -> None:
        """Should return False and not error when no trace file exists."""
        output_dir = tmp_path / "results"
        output_dir.mkdir()

        find_result = MagicMock()
        find_result.returncode = 0
        find_result.stdout = ""  # No files found

        with patch("scripts.orchestration.run_task.subprocess.run") as mock_run:
            mock_run.return_value = find_result
            result = _copy_agent_trace("container-123", output_dir)

        assert result is False

    def test_returns_false_when_find_fails(self, tmp_path: Path) -> None:
        """Should return False gracefully when docker exec find fails."""
        output_dir = tmp_path / "results"
        output_dir.mkdir()

        find_result = MagicMock()
        find_result.returncode = 1
        find_result.stdout = ""
        find_result.stderr = "No such file or directory"

        with patch("scripts.orchestration.run_task.subprocess.run") as mock_run:
            mock_run.return_value = find_result
            result = _copy_agent_trace("container-123", output_dir)

        assert result is False

    def test_returns_false_when_docker_cp_fails(self, tmp_path: Path) -> None:
        """Should return False when docker cp fails (e.g., permission denied)."""
        output_dir = tmp_path / "results"
        output_dir.mkdir()

        find_result = MagicMock()
        find_result.returncode = 0
        find_result.stdout = "/home/agent/.claude/projects/abc/conversation.jsonl\n"

        cp_result = MagicMock()
        cp_result.returncode = 1
        cp_result.stderr = "permission denied"

        with patch("scripts.orchestration.run_task.subprocess.run") as mock_run:
            mock_run.side_effect = [find_result, cp_result]
            result = _copy_agent_trace("container-123", output_dir)

        assert result is False

    def test_handles_multiple_trace_files(self, tmp_path: Path) -> None:
        """When multiple trace files exist, should copy the most recent one."""
        output_dir = tmp_path / "results"
        output_dir.mkdir()

        find_result = MagicMock()
        find_result.returncode = 0
        # find with -printf '%T@ %p\n' | sort -rn returns newest first
        find_result.stdout = (
            "/home/agent/.claude/projects/abc/conversation.jsonl\n"
            "/home/agent/.claude/projects/def/conversation.jsonl\n"
        )

        cp_result = MagicMock()
        cp_result.returncode = 0
        cp_result.stderr = ""

        with patch("scripts.orchestration.run_task.subprocess.run") as mock_run:
            mock_run.side_effect = [find_result, cp_result]
            result = _copy_agent_trace("container-123", output_dir)

        assert result is True
        # Should copy the first (newest) file
        cp_call = mock_run.call_args_list[1]
        cmd = cp_call[0][0]
        assert "abc/conversation.jsonl" in " ".join(cmd)

    def test_output_filename_is_agent_trace_jsonl(self, tmp_path: Path) -> None:
        """Output file should be named agent_trace.jsonl."""
        output_dir = tmp_path / "results"
        output_dir.mkdir()

        find_result = MagicMock()
        find_result.returncode = 0
        find_result.stdout = "/home/agent/.claude/projects/abc/conversation.jsonl\n"

        cp_result = MagicMock()
        cp_result.returncode = 0
        cp_result.stderr = ""

        with patch("scripts.orchestration.run_task.subprocess.run") as mock_run:
            mock_run.side_effect = [find_result, cp_result]
            _copy_agent_trace("container-123", output_dir)

        cp_call = mock_run.call_args_list[1]
        cmd = cp_call[0][0]
        dest = cmd[-1]  # last arg of docker cp is destination
        assert dest == str(output_dir / "agent_trace.jsonl")

    def test_handles_timeout_gracefully(self, tmp_path: Path) -> None:
        """Should return False if docker exec times out."""
        output_dir = tmp_path / "results"
        output_dir.mkdir()

        with patch("scripts.orchestration.run_task.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=30)
            result = _copy_agent_trace("container-123", output_dir)

        assert result is False
