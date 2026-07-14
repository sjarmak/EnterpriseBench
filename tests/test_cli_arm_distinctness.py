"""Arm-distinctness tests for the sgx `cli` mode wiring in run_task.py.

The three retrieval arms must stay structurally distinct — mislabeling one as
another corrupts the arm comparison:

  - cli       -> installs sgx, registers NO Sourcegraph MCP, uses the sgx
                 preamble (a plain shell command; no mcp__* tools)
  - mcp_only  -> registers MCP, installs NO sgx, uses the MCP preamble
  - baseline  -> neither install path fires, no retrieval preamble

These exercise the gating logic directly (docker/network helpers mocked); they
never build a container or hit the network.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts" / "orchestration"))

import run_task  # noqa: E402
from agents.harnesses.claude.cli import sgx as sgx_preamble  # noqa: E402


def _completed(stdout: str = "", returncode: int = 0):
    """A stand-in for subprocess.CompletedProcess."""
    return types.SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


# ---------------------------------------------------------------------------
# sgx install routing: only the cli arm installs sgx
# ---------------------------------------------------------------------------


class TestSgxInstallRouting:
    def test_cli_installs_sgx(self, monkeypatch):
        monkeypatch.setenv("SOURCEGRAPH_ACCESS_TOKEN", "tok")
        cp_calls = []
        with patch.object(run_task, "_docker_cp", side_effect=lambda *a: cp_calls.append(a)), patch.object(
            run_task, "_docker_exec", return_value=_completed("SG_CLI_OK\n")
        ):
            ok = run_task._install_sgx("cid", "cli")
        assert ok is True
        # The stdlib CLI was uploaded to /usr/local/lib/sg_cli.py.
        assert cp_calls, "cli arm must docker cp sg_cli.py into the container"
        src, dest = cp_calls[0]
        assert src.endswith("sg_cli.py")
        assert dest.endswith(":/usr/local/lib/sg_cli.py")

    def test_cli_install_fails_hard_on_bad_probe(self, monkeypatch):
        monkeypatch.setenv("SOURCEGRAPH_ACCESS_TOKEN", "tok")
        with patch.object(run_task, "_docker_cp"), patch.object(
            run_task, "_docker_exec", return_value=_completed("SG_CLI_FAIL\n")
        ):
            ok = run_task._install_sgx("cid", "cli")
        assert ok is False

    def test_mcp_only_does_not_install_sgx(self):
        def _boom(*a, **k):
            raise AssertionError("sgx must NOT be installed for mcp_only")

        with patch.object(run_task, "_docker_cp", side_effect=_boom), patch.object(
            run_task, "_docker_exec", side_effect=_boom
        ):
            assert run_task._install_sgx("cid", "mcp_only") is True

    def test_baseline_does_not_install_sgx(self):
        def _boom(*a, **k):
            raise AssertionError("sgx must NOT be installed for baseline")

        with patch.object(run_task, "_docker_cp", side_effect=_boom), patch.object(
            run_task, "_docker_exec", side_effect=_boom
        ):
            assert run_task._install_sgx("cid", "baseline") is True


# ---------------------------------------------------------------------------
# MCP registration routing: cli/baseline register NO MCP
# ---------------------------------------------------------------------------


class TestMcpRegistrationRouting:
    def test_cli_registers_no_mcp(self):
        def _boom(*a, **k):
            raise AssertionError("cli arm must NOT configure MCP")

        with patch.object(run_task, "_verify_mcp_endpoint", side_effect=_boom), patch.object(
            run_task, "_docker_cp", side_effect=_boom
        ):
            assert run_task._configure_mcp("cid", "cli") is True

    def test_baseline_registers_no_mcp(self):
        def _boom(*a, **k):
            raise AssertionError("baseline must NOT configure MCP")

        with patch.object(run_task, "_verify_mcp_endpoint", side_effect=_boom), patch.object(
            run_task, "_docker_cp", side_effect=_boom
        ):
            assert run_task._configure_mcp("cid", "baseline") is True


# ---------------------------------------------------------------------------
# Preamble dispatch: each arm gets the right instruction preamble
# ---------------------------------------------------------------------------


def _make_task_dir(tmp_path: Path) -> Path:
    (tmp_path / "instruction.md").write_text("# Task\nDo the thing.\n")
    return tmp_path


class TestPreambleDispatch:
    def test_cli_preamble_present_no_mcp_language(self, tmp_path):
        text = run_task._build_instruction_text(_make_task_dir(tmp_path), "cli", repos=[])
        assert "`sgx`" in text
        assert "NO MCP tools" in text
        # The cli arm must not advertise registered mcp tools.
        assert "mcp__sourcegraph__" not in text

    def test_mcp_only_preamble_present_no_sgx(self, tmp_path):
        text = run_task._build_instruction_text(
            _make_task_dir(tmp_path), "mcp_only", repos=[]
        )
        assert "Sourcegraph MCP tools" in text or "keyword_search" in text
        assert "sgx" not in text

    def test_baseline_has_no_retrieval_preamble(self, tmp_path):
        text = run_task._build_instruction_text(
            _make_task_dir(tmp_path), "baseline", repos=[]
        )
        assert "sgx" not in text
        assert "keyword_search" not in text
        # Still carries the base instruction + output appendix.
        assert "Do the thing." in text
        assert "answer.json" in text


# ---------------------------------------------------------------------------
# sgx preamble builder unit behavior
# ---------------------------------------------------------------------------


class TestSgxPreambleBuilder:
    def test_cli_mode_returns_sgx_guidance(self):
        out = sgx_preamble.build_system_prompt("cli", repos=[])
        assert "`sgx`" in out
        assert "NO MCP tools" in out
        assert "sgx search" in out

    @pytest.mark.parametrize("mode", ["baseline", "mcp_only", "hybrid", "bogus"])
    def test_non_cli_modes_return_empty(self, mode):
        assert sgx_preamble.build_system_prompt(mode, repos=[]) == ""

    def test_repo_scope_included(self):
        repos = [{"url": "https://github.com/grpc/grpc-go", "rev": "v1.4.0", "path": "grpc-go"}]
        out = sgx_preamble.build_system_prompt("cli", repos=repos)
        assert "repo:^github.com/" in out
        assert "grpc-go" in out


# ---------------------------------------------------------------------------
# Mode registry: cli is a recognized mode
# ---------------------------------------------------------------------------


def test_cli_in_valid_modes():
    assert "cli" in run_task.VALID_MODES
    assert "baseline" in run_task.VALID_MODES
    assert "mcp_only" in run_task.VALID_MODES
    assert "hybrid" in run_task.VALID_MODES


def test_sgx_endpoint_is_v1():
    # sg_cli.py hardcodes sg_-prefixed tool names served by /.api/mcp/v1.
    assert run_task.SGX_ENDPOINT.endswith("/.api/mcp/v1")
