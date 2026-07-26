"""Contracts that keep Code Finder distinct from direct MCP and CLI retrieval."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.harnesses.claude.mcp.sourcegraph import build_system_prompt
from scripts import run_benchmark
from scripts.lib import shared
from scripts.orchestration import mode_gate, run_task
from scripts.orchestration import run_pilot

REPOS = [
    {
        "url": "https://github.com/pallets/flask",
        "rev": "3.1.0",
        "path": "flask",
    }
]


@pytest.mark.parametrize("mode", ["mcp_code_finder", "mcp_assisted", "cli_code_finder"])
def test_finder_modes_are_registered_and_filesystem_gated(mode: str) -> None:
    assert mode in run_task.VALID_MODES
    assert mode in mode_gate.GATED_MODES


def test_forced_finder_prompt_requires_one_call_per_repo_and_no_direct_tools() -> None:
    prompt = build_system_prompt("mcp_code_finder", REPOS)

    assert "`code_finder`" in prompt
    assert "exactly once per repository" in prompt
    assert "Do not call any direct Sourcegraph retrieval tool" in prompt
    assert "`read_file`" in prompt
    assert "repo:^github.com/sg-evals/flask--3.1.0$" in prompt


def test_assisted_finder_prompt_requires_bootstrap_then_allows_follow_up() -> None:
    prompt = build_system_prompt("mcp_assisted", REPOS)

    assert "`code_finder`" in prompt
    assert "at least once" in prompt
    assert "targeted follow-up" in prompt
    assert "`read_file`" in prompt


def test_cli_finder_prompt_requires_same_retrieval_contract_without_mcp() -> None:
    prompt = run_task._build_cli_preamble("cli_code_finder", REPOS)

    assert "NO MCP tools" in prompt
    assert "`sgx finder`" in prompt
    assert "exactly once per repository" in prompt
    assert "Do not use any other `sgx` retrieval command" in prompt
    assert "Use `sgx` to search and read code" not in prompt
    assert "repo:^github.com/sg-evals/flask--3.1.0$" in prompt


def test_direct_mcp_prompt_prohibits_code_finder_to_keep_arms_distinct() -> None:
    prompt = build_system_prompt("mcp_only", REPOS)

    assert "Do not call `code_finder`" in prompt
    assert "direct Sourcegraph retrieval" in prompt


@pytest.mark.parametrize("mode", ["mcp_code_finder", "mcp_assisted", "cli_code_finder"])
def test_instruction_builder_injects_finder_prompt(
    tmp_path: Path,
    mode: str,
) -> None:
    (tmp_path / "instruction.md").write_text("Find the root cause.")

    instruction = run_task._build_instruction_text(tmp_path, mode, REPOS)

    assert instruction is not None
    assert "code_finder" in instruction
    assert "Find the root cause." in instruction


def test_forced_finder_validity_failure_routes_run_to_infra_error() -> None:
    result = run_task.TaskRunResult(
        task_id="cal-err-flask-blueprint-001",
        tool_usage={
            "mcp_tool_calls": 1,
            "retrieval": {
                "valid": False,
                "invalid_reason": "expected 1 code_finder call, observed 0",
            },
        },
    )

    run_task._route_code_finder_run(result, "mcp_code_finder")

    assert result.status == run_task.RUN_STATUS_INVALID
    assert result.failure_class == "infra_code_finder_contract"
    assert "expected 1" in result.error


@pytest.mark.parametrize(
    ("mode", "tool_usage"),
    [
        (
            "mcp_code_finder",
            {
                "mcp_tool_calls": 0,
                "mcp_tool_breakdown": {},
            },
        ),
        (
            "cli_code_finder",
            {
                "sgx_tool_calls": 0,
                "sgx_tool_breakdown": {},
            },
        ),
    ],
)
def test_forced_finder_rejects_raw_http_bypass_of_the_assigned_interface(
    mode: str,
    tool_usage: dict,
) -> None:
    result = run_task.TaskRunResult(
        task_id="dep-traversal-003",
        tool_usage={
            **tool_usage,
            "retrieval": {
                "valid": True,
                "code_finder_calls": 2,
            },
        },
    )

    run_task._route_code_finder_run(result, mode)

    assert result.status == run_task.RUN_STATUS_INVALID
    assert result.failure_class == "invalid_arm_contamination"
    assert "interface" in result.error


@pytest.mark.parametrize("mode", ["mcp_code_finder", "mcp_assisted"])
def test_finder_modes_route_mcp_clients_through_local_proxy(mode: str) -> None:
    assert run_task._mcp_endpoint_for_mode(mode) == run_task.MCP_PROXY_ENDPOINT


@pytest.mark.parametrize("mode", ["mcp_only", "hybrid"])
def test_existing_mcp_modes_still_use_sourcegraph_directly(mode: str) -> None:
    assert run_task._mcp_endpoint_for_mode(mode) == run_task.SOURCEGRAPH_MCP_ENDPOINT


def test_expected_sourcegraph_repositories_use_exact_mirror_names() -> None:
    repos = [
        {
            "url": "https://github.com/pallets/flask",
            "rev": "2.3.3",
            "path": "flask",
        },
        {
            "url": "https://github.com/pallets/werkzeug",
            "rev": "2.3.7",
            "path": "werkzeug",
        },
    ]

    assert run_task._expected_sourcegraph_repositories(repos) == [
        "github.com/sg-evals/flask--2.3.3",
        "github.com/sg-evals/werkzeug--2.3.7",
    ]


def test_cli_is_explicitly_a_separate_direct_retrieval_treatment() -> None:
    assert run_task.CLI_RETRIEVAL_TREATMENT == "direct_sgx_plus_local_source"
    assert run_task.CLI_FINDER_TREATMENT == "code_finder_via_sgx_no_mcp"
    assert "cli_code_finder" in run_task.VALID_MODES


@pytest.mark.parametrize("mode", ["mcp_code_finder", "mcp_assisted", "cli_code_finder"])
def test_all_benchmark_entry_points_recognize_finder_modes(mode: str) -> None:
    assert mode in shared.VALID_MODES
    assert mode in run_benchmark.VALID_MODES
    assert mode in run_pilot.VALID_MODES


def test_proxy_installer_stages_root_owned_script_without_secret_env() -> None:
    healthy = MagicMock(returncode=0, stdout='{"status":"ok"}', stderr="")
    with (
        patch.object(run_task, "_docker_exec", return_value=healthy),
        patch.object(run_task, "_docker_cp") as docker_cp,
        patch.object(
            run_task,
            "_docker_exec_detached",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ) as detached,
    ):
        assert run_task._install_mcp_telemetry_proxy("cid") is True

    docker_cp.assert_called_once_with(
        run_task.MCP_PROXY_SRC.as_posix(),
        f"cid:{run_task.MCP_PROXY_SCRIPT_PATH}",
    )
    assert "SOURCEGRAPH_ACCESS_TOKEN" not in detached.call_args.kwargs["env"]
    assert detached.call_args.kwargs["env"]["MCP_PROXY_UPSTREAM_URL"] == (
        run_task.SOURCEGRAPH_MCP_ENDPOINT
    )


def test_run_task_copies_and_summarizes_finder_proxy_trace(tmp_path: Path) -> None:
    result = run_task.TaskRunResult(
        task_id="dep-traversal-003",
        tool_usage={
            "total_input_tokens": 100,
            "total_output_tokens": 25,
            "cost_usd": 0.2,
            "mcp_tool_calls": 1,
        },
    )
    repository = "github.com/sg-evals/flask--3.1.0"
    request = {
        "trace_version": 1,
        "direction": "request",
        "id": 1,
        "method": "tools/call",
        "tool": "code_finder",
        "arguments": {"task": f"Inspect {repository}"},
    }
    response = {
        "trace_version": 1,
        "direction": "response",
        "id": 1,
        "method": "tools/call",
        "tool": "code_finder",
        "status": 200,
        "is_error": False,
        "meta": {
            "sourcegraphToolTelemetry": {
                "subAgentTurns": 1,
                "subAgentToolCalls": 2,
                "subAgentTotalTokens": 3,
            }
        },
    }

    def copy_trace(_source: str, destination: str) -> None:
        Path(destination).write_text(
            json.dumps(request) + "\n" + json.dumps(response) + "\n"
        )

    with patch.object(run_task, "_docker_cp", side_effect=copy_trace):
        run_task._capture_mcp_telemetry(
            result,
            "cid",
            tmp_path,
            mode="mcp_code_finder",
            expected_repo_count=1,
            expected_repositories=[repository],
        )

    assert (tmp_path / "mcp_telemetry.jsonl").is_file()
    assert result.tool_usage["retrieval"]["valid"] is True
    assert result.tool_usage["retrieval"]["inner"]["turns"] == 1


def test_cli_finder_uses_proxy_without_registering_mcp() -> None:
    assert "cli_code_finder" not in run_task.MCP_MODES
    assert "cli_code_finder" in run_task.CLI_MODES
    assert "cli_code_finder" in run_task.FINDER_MODES


def test_cli_finder_preflight_starts_all_endpoint_proxy_and_checks_inventory() -> None:
    with (
        patch.dict(
            run_task.os.environ,
            {"SOURCEGRAPH_ACCESS_TOKEN": "sgp_test_secret"},
        ),
        patch.object(run_task, "_verify_mcp_endpoint", return_value=True),
        patch.object(
            run_task,
            "_install_mcp_telemetry_proxy",
            return_value=True,
        ) as install,
        patch.object(
            run_task,
            "_verify_cli_finder_inventory",
            return_value=True,
        ) as inventory,
    ):
        assert run_task._configure_cli_code_finder("cid", "cli_code_finder") is True

    install.assert_called_once_with(
        "cid",
        upstream_url=run_task.SOURCEGRAPH_MCP_ENDPOINT,
    )
    inventory.assert_called_once_with("cid", "sgp_test_secret")
