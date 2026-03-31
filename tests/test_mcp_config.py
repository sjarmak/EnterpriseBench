"""Tests for MCP configuration in run_task.py.

Verifies:
  - Correct Sourcegraph endpoint URL
  - Authorization headers present in MCP settings
  - NODE_TLS_REJECT_UNAUTHORIZED=0 set for MCP modes
  - SOURCEGRAPH_ACCESS_TOKEN passed for MCP modes
  - No MCP env vars set for baseline mode
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Make scripts importable
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts" / "orchestration")
)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "infra"))

from run_task import (
    SOURCEGRAPH_MCP_ENDPOINT,
    _DEFAULT_MCP_URL,
    _configure_mcp,
    run_task,
    TaskRunConfig,
)

# ---------------------------------------------------------------------------
# Endpoint URL
# ---------------------------------------------------------------------------


class TestMcpEndpointUrl:
    def test_endpoint_default_is_demo(self) -> None:
        """Default endpoint must point to demo.sourcegraph.com (matches CSB token)."""
        assert "demo.sourcegraph.com" in _DEFAULT_MCP_URL

    def test_endpoint_path_is_mcp_all(self) -> None:
        """Endpoint path must be /.api/mcp/all (not /mcp or /mcp/v1)."""
        assert SOURCEGRAPH_MCP_ENDPOINT.endswith("/.api/mcp/all")

    def test_endpoint_overridable_via_env(self) -> None:
        """SOURCEGRAPH_MCP_URL env var overrides the default endpoint."""
        import importlib
        import run_task

        with patch.dict(
            os.environ,
            {"SOURCEGRAPH_MCP_URL": "https://custom.example.com/.api/mcp/all"},
        ):
            importlib.reload(run_task)
            assert (
                run_task.SOURCEGRAPH_MCP_ENDPOINT
                == "https://custom.example.com/.api/mcp/all"
            )
        # Restore
        importlib.reload(run_task)


# ---------------------------------------------------------------------------
# Auth headers in _configure_mcp
# ---------------------------------------------------------------------------


class TestMcpAuthHeaders:
    """Verify that _configure_mcp writes settings.json with Authorization header."""

    def _capture_mcp_config(self, mode: str = "mcp_only") -> dict:
        """Call _configure_mcp with a mock docker exec and return the parsed config."""
        captured_cmds: list[list[str]] = []

        def mock_docker_exec(
            container_id: str,
            cmd: list[str],
            timeout: int = 120,
            workdir: str = "/workspace",
        ):
            captured_cmds.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("run_task._docker_exec", side_effect=mock_docker_exec), patch.dict(
            os.environ, {"SOURCEGRAPH_ACCESS_TOKEN": "sgp_test_token_123"}
        ):
            _configure_mcp("test-container", mode)

        # Find the bash -c command that writes settings.json
        for cmd in captured_cmds:
            if len(cmd) >= 3 and cmd[0] == "bash" and cmd[1] == "-c":
                bash_script = cmd[2]
                if "settings.json" in bash_script:
                    # Extract the JSON from the echo command
                    # The format is: echo '...' > /home/agent/.claude/settings.json
                    import re

                    match = re.search(r"echo '(\{.*?\})' >", bash_script, re.DOTALL)
                    if match:
                        return json.loads(match.group(1))
        pytest.fail("No settings.json write command found in docker exec calls")

    def test_mcp_config_includes_authorization_header(self) -> None:
        config = self._capture_mcp_config("mcp_only")
        sg_config = config.get("mcpServers", {}).get("sg", {})
        headers = sg_config.get("headers", {})
        assert (
            "Authorization" in headers
        ), "settings.json must include Authorization header"

    def test_mcp_config_auth_header_format(self) -> None:
        config = self._capture_mcp_config("mcp_only")
        auth = config["mcpServers"]["sg"]["headers"]["Authorization"]
        assert auth.startswith(
            "token "
        ), "Authorization header must start with 'token '"

    def test_mcp_config_uses_correct_endpoint(self) -> None:
        config = self._capture_mcp_config("mcp_only")
        url = config["mcpServers"]["sg"]["url"]
        assert url == SOURCEGRAPH_MCP_ENDPOINT

    def test_mcp_config_type_is_http(self) -> None:
        config = self._capture_mcp_config("mcp_only")
        assert config["mcpServers"]["sg"]["type"] == "http"

    def test_hybrid_mode_also_configures_mcp(self) -> None:
        config = self._capture_mcp_config("hybrid")
        assert "sg" in config.get("mcpServers", {})
        assert "Authorization" in config["mcpServers"]["sg"].get("headers", {})


# ---------------------------------------------------------------------------
# Environment variables for MCP modes
# ---------------------------------------------------------------------------


class TestMcpEnvVars:
    """Verify NODE_TLS_REJECT_UNAUTHORIZED and SOURCEGRAPH_ACCESS_TOKEN for MCP modes."""

    def _get_env_extra_for_mode(self, mode: str) -> dict[str, str]:
        """Extract env_extra that would be passed to _run_agent for the given mode.

        We patch everything heavy (parse, build, docker ops) and capture what
        env_extra is passed to _run_agent.
        """
        captured_env: dict[str, str] = {}

        def mock_run_agent(
            container_id, agent_command, timeout, output_dir, env_extra=None
        ):
            captured_env.update(env_extra or {})
            return (0, 10.0)

        fake_task_data = {
            "task": {
                "id": "test-mcp-env-001",
                "suite": "test",
                "task_type": "test",
                "difficulty": "easy",
                "session_type": "single",
            },
            "repos": [],
        }

        config = TaskRunConfig(
            task_toml=Path("/fake/task.toml"),
            agent_command="claude -p",
            timeout=300,
            mode=mode,
        )

        with patch("run_task._parse_task", return_value=fake_task_data), patch(
            "run_task._generate_dockerfile", return_value=Path("/fake/Dockerfile")
        ), patch("run_task._docker_build"), patch(
            "run_task._docker_create_container", return_value="fake-container-id"
        ), patch(
            "run_task._docker_start"
        ), patch(
            "run_task._setup_container"
        ), patch(
            "run_task._run_health_check", return_value=True
        ), patch(
            "run_task._configure_mcp"
        ), patch(
            "run_task._run_agent", side_effect=mock_run_agent
        ) as mock_agent, patch(
            "run_task._run_scoring", return_value={"task_score": 0.0}
        ), patch(
            "run_task._save_results"
        ), patch(
            "run_task._extract_tool_usage", return_value={}
        ), patch(
            "run_task._copy_agent_trace", return_value=False
        ), patch(
            "run_task._check_disk_space", return_value=True
        ), patch(
            "run_task._docker_stop_rm"
        ), patch.dict(
            os.environ, {"SOURCEGRAPH_ACCESS_TOKEN": "sgp_test_token_xyz"}
        ):
            run_task(config)

        return captured_env

    def test_mcp_only_sets_node_tls_reject(self) -> None:
        env = self._get_env_extra_for_mode("mcp_only")
        assert env.get("NODE_TLS_REJECT_UNAUTHORIZED") == "0"

    def test_hybrid_sets_node_tls_reject(self) -> None:
        env = self._get_env_extra_for_mode("hybrid")
        assert env.get("NODE_TLS_REJECT_UNAUTHORIZED") == "0"

    def test_baseline_does_not_set_node_tls_reject(self) -> None:
        env = self._get_env_extra_for_mode("baseline")
        assert "NODE_TLS_REJECT_UNAUTHORIZED" not in env

    def test_mcp_only_passes_sourcegraph_token(self) -> None:
        env = self._get_env_extra_for_mode("mcp_only")
        assert env.get("SOURCEGRAPH_ACCESS_TOKEN") == "sgp_test_token_xyz"

    def test_hybrid_passes_sourcegraph_token(self) -> None:
        env = self._get_env_extra_for_mode("hybrid")
        assert env.get("SOURCEGRAPH_ACCESS_TOKEN") == "sgp_test_token_xyz"

    def test_baseline_does_not_pass_sourcegraph_token(self) -> None:
        env = self._get_env_extra_for_mode("baseline")
        assert "SOURCEGRAPH_ACCESS_TOKEN" not in env


# ---------------------------------------------------------------------------
# _configure_mcp skips baseline
# ---------------------------------------------------------------------------


class TestMcpSkipsBaseline:
    def test_baseline_mode_skips_mcp_config(self) -> None:
        """_configure_mcp should be a no-op for baseline mode."""
        mock_exec = MagicMock()
        with patch("run_task._docker_exec", mock_exec):
            _configure_mcp("test-container", "baseline")
        mock_exec.assert_not_called()
