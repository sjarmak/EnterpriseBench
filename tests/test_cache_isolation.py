"""Cross-run prompt-cache isolation contracts for every measured harness."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agents.harnesses.cache_isolation import (
    CacheIsolationError,
    build_cache_isolation,
    evaluate_cache_isolation,
)
from agents.harnesses.registry import build_harness_plan
from scripts.orchestration import run_task


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["docker"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.mark.parametrize("harness", ["claude", "codex", "opencode"])
def test_cache_scope_is_unique_per_benchmark_invocation(harness: str) -> None:
    first = build_cache_isolation(harness)
    second = build_cache_isolation(harness)

    assert first.scope != second.scope
    assert first.environment["ENTERPRISEBENCH_CACHE_SCOPE"] == first.scope
    assert second.environment["ENTERPRISEBENCH_CACHE_SCOPE"] == second.scope


def test_claude_disables_prompt_caching_at_the_provider_boundary() -> None:
    isolation = build_cache_isolation("claude", scope="a" * 32)

    assert isolation.mechanism == "prompt-caching-disabled"
    assert isolation.environment == {
        "DISABLE_PROMPT_CACHING": "1",
        "ENTERPRISEBENCH_CACHE_SCOPE": "a" * 32,
    }


def test_codex_uses_fresh_ephemeral_thread_as_prompt_cache_scope() -> None:
    isolation = build_cache_isolation("codex", scope="b" * 32)

    assert isolation.mechanism == "fresh-session-prompt-cache-key"
    assert isolation.environment == {
        "ENTERPRISEBENCH_CACHE_SCOPE": "b" * 32,
    }


def test_opencode_uses_unique_prefix_and_disables_openrouter_response_cache() -> None:
    isolation = build_cache_isolation("opencode", scope="c" * 32)

    assert isolation.mechanism == "unique-system-prefix-and-session"
    assert isolation.environment == {
        "ENTERPRISEBENCH_CACHE_SCOPE": "c" * 32,
        "OPENCODE_CONFIG_DIR": "/home/agent/.config/opencode",
        "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
    }


@pytest.mark.parametrize(
    "scope",
    ["", "short", "contains spaces" + "a" * 20, "../" + "a" * 32],
)
def test_cache_scope_rejects_ambiguous_or_unsafe_values(scope: str) -> None:
    with pytest.raises(CacheIsolationError):
        build_cache_isolation("claude", scope=scope)


def test_stage_opencode_cache_plugin_is_private_and_uses_no_secret_values() -> None:
    plan = build_harness_plan(
        "opencode",
        model="openrouter/moonshotai/kimi-k3",
        mode="baseline",
    )
    isolation = build_cache_isolation("opencode", scope="d" * 32)
    copies: list[tuple[str, str]] = []
    exec_calls: list[list[str]] = []

    with (
        patch.object(
            run_task,
            "_docker_exec",
            side_effect=lambda _cid, argv, **_kwargs: (
                exec_calls.append(argv) or _completed()
            ),
        ),
        patch.object(
            run_task,
            "_docker_cp",
            side_effect=lambda source, destination: copies.append(
                (source, destination)
            ),
        ),
    ):
        environment = run_task._stage_cache_isolation(
            "container-1", plan, isolation
        )

    assert environment == isolation.environment
    assert copies == [
        (
            str(run_task.OPENCODE_CACHE_ISOLATION_PLUGIN_SRC),
            "container-1:/home/agent/.config/opencode/plugins/"
            "enterprisebench-cache-isolation.js",
        )
    ]
    assert [
        "chmod",
        "600",
        "/home/agent/.config/opencode/plugins/"
        "enterprisebench-cache-isolation.js",
    ] in exec_calls
    assert [
        "chown",
        "agent:agent",
        "/home/agent/.config/opencode/plugins/"
        "enterprisebench-cache-isolation.js",
    ] in exec_calls

    plugin = run_task.OPENCODE_CACHE_ISOLATION_PLUGIN_SRC.read_text()
    assert "ENTERPRISEBENCH_CACHE_SCOPE" in plugin
    assert "X-OpenRouter-Cache" in plugin
    assert '"false"' in plugin
    assert "X-Session-Id" in plugin
    assert "output.system[0]" in plugin
    assert "enterprisebench-cache-isolation.jsonl" in plugin
    assert "appendFile" in plugin
    assert "OPENROUTER_API_KEY" not in plugin


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_stage_non_opencode_cache_isolation_does_not_copy_files(
    harness: str,
) -> None:
    plan = build_harness_plan(
        harness,
        model="gpt-5.6-sol" if harness == "codex" else None,
        mode="baseline",
    )
    isolation = build_cache_isolation(harness, scope="e" * 32)
    with (
        patch.object(run_task, "_docker_exec") as docker_exec,
        patch.object(run_task, "_docker_cp") as docker_cp,
    ):
        environment = run_task._stage_cache_isolation(
            "container-1", plan, isolation
        )

    assert environment == isolation.environment
    docker_exec.assert_not_called()
    docker_cp.assert_not_called()


def test_claude_cache_proof_accepts_only_zero_reads_and_writes() -> None:
    isolation = build_cache_isolation("claude", scope="f" * 32)
    valid = evaluate_cache_isolation(
        isolation,
        [
            {
                "modelUsage": {
                    "claude-sonnet": {
                        "cacheReadInputTokens": 0,
                        "cacheCreationInputTokens": 0,
                    }
                }
            }
        ],
    )
    contaminated = evaluate_cache_isolation(
        isolation,
        [
            {
                "modelUsage": {
                    "claude-sonnet": {
                        "cacheReadInputTokens": 2048,
                        "cacheCreationInputTokens": 0,
                    }
                }
            }
        ],
    )

    assert valid["valid"] is True
    assert valid["cross_run_cache_read_tokens"] == 0
    assert valid["cache_write_tokens"] == 0
    assert contaminated["valid"] is False
    assert contaminated["cross_run_cache_read_tokens"] == 2048
    assert contaminated["invalid_reason"] == "Claude reported prompt-cache reuse"


def test_claude_cache_proof_fails_closed_without_authoritative_usage() -> None:
    isolation = build_cache_isolation("claude", scope="1" * 32)

    proof = evaluate_cache_isolation(isolation, [{"type": "assistant"}])
    incomplete = evaluate_cache_isolation(
        isolation,
        [{"modelUsage": {"claude-sonnet": {"inputTokens": 10}}}],
    )

    assert proof["valid"] is False
    assert proof["invalid_reason"] == "Claude cache telemetry is missing"
    assert incomplete["valid"] is False
    assert incomplete["invalid_reason"] == "Claude cache telemetry is incomplete"


def test_codex_cache_proof_uses_fresh_thread_not_cumulative_cache_reads() -> None:
    isolation = build_cache_isolation("codex", scope="2" * 32)
    proof = evaluate_cache_isolation(
        isolation,
        [
            {"type": "thread.started", "thread_id": "thread-unique-123"},
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 5000,
                    "cached_input_tokens": 3500,
                    "cache_write_input_tokens": 0,
                },
            },
        ],
    )

    assert proof["valid"] is True
    assert proof["scope"] == "thread-unique-123"
    assert proof["launcher_scope"] == "2" * 32
    assert proof["total_cache_read_tokens"] == 3500
    assert proof["cross_run_cache_read_tokens"] == 0
    assert proof["verification"] == "fresh Codex thread ID"


@pytest.mark.parametrize(
    "records, reason",
    [
        (
            [{"type": "turn.completed", "usage": {"cached_input_tokens": 0}}],
            "Codex thread cache scope is missing",
        ),
        (
            [
                {"type": "thread.started", "thread_id": "one"},
                {"type": "thread.started", "thread_id": "two"},
            ],
            "Codex emitted multiple thread cache scopes",
        ),
    ],
)
def test_codex_cache_proof_fails_closed_on_ambiguous_thread(
    records: list[dict], reason: str
) -> None:
    isolation = build_cache_isolation("codex", scope="3" * 32)

    proof = evaluate_cache_isolation(isolation, records)

    assert proof["valid"] is False
    assert proof["invalid_reason"] == reason


def test_opencode_cache_proof_allows_only_within_run_cache_hits() -> None:
    isolation = build_cache_isolation("opencode", scope="4" * 32)
    proof = evaluate_cache_isolation(
        isolation,
        [
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": "4" * 32,
                "hook": "system",
            },
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": "4" * 32,
                "hook": "headers",
            },
            {
                "type": "step_finish",
                "part": {
                    "type": "step-finish",
                    "tokens": {"cache": {"read": 0, "write": 4096}},
                },
            },
            {
                "type": "step_finish",
                "part": {
                    "type": "step-finish",
                    "tokens": {"cache": {"read": 4096, "write": 0}},
                },
            },
        ],
    )

    assert proof["valid"] is True
    assert proof["cross_run_cache_read_tokens"] == 0
    assert proof["total_cache_read_tokens"] == 4096
    assert proof["cache_write_tokens"] == 4096
    assert proof["verification"] == "zero cache reads on first OpenCode step"


def test_opencode_cache_proof_rejects_first_step_cache_hit() -> None:
    isolation = build_cache_isolation("opencode", scope="5" * 32)
    proof = evaluate_cache_isolation(
        isolation,
        [
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": "5" * 32,
                "hook": "system",
            },
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": "5" * 32,
                "hook": "headers",
            },
            {
                "type": "step_finish",
                "part": {
                    "type": "step-finish",
                    "tokens": {"cache": {"read": 2048, "write": 0}},
                },
            }
        ],
    )

    assert proof["valid"] is False
    assert proof["cross_run_cache_read_tokens"] == 2048
    assert proof["invalid_reason"] == "OpenCode first step read a prior cache"


def test_opencode_cache_proof_fails_closed_without_step_usage() -> None:
    isolation = build_cache_isolation("opencode", scope="6" * 32)

    proof = evaluate_cache_isolation(
        isolation,
        [
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": "6" * 32,
                "hook": "system",
            },
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": "6" * 32,
                "hook": "headers",
            },
            {"type": "text", "part": {}},
        ],
    )

    assert proof["valid"] is False
    assert proof["invalid_reason"] == "OpenCode cache telemetry is missing"


def test_opencode_cache_proof_fails_closed_when_first_step_omits_cache_usage() -> None:
    scope = "c" * 32
    isolation = build_cache_isolation("opencode", scope=scope)
    proof = evaluate_cache_isolation(
        isolation,
        [
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": scope,
                "hook": "system",
            },
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": scope,
                "hook": "headers",
            },
            {
                "type": "step_finish",
                "part": {
                    "type": "step-finish",
                    "tokens": {"input": 100, "output": 20},
                },
            },
        ],
    )

    assert proof["valid"] is False
    assert proof["invalid_reason"] == "OpenCode first-step cache telemetry is missing"


@pytest.mark.parametrize(
    "hook_records",
    [
        [],
        [
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": "9" * 32,
                "hook": "system",
            }
        ],
        [
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": "a" * 32,
                "hook": "system",
            },
            {
                "type": "enterprisebench.cache_isolation_hook",
                "scope": "a" * 32,
                "hook": "headers",
            },
        ],
    ],
)
def test_opencode_cache_proof_requires_both_hooks_at_the_launcher_scope(
    hook_records: list[dict],
) -> None:
    isolation = build_cache_isolation("opencode", scope="9" * 32)
    provider_record = {
        "type": "step_finish",
        "part": {
            "type": "step-finish",
            "tokens": {"cache": {"read": 0, "write": 0}},
        },
    }

    proof = evaluate_cache_isolation(
        isolation,
        [*hook_records, provider_record],
    )

    assert proof["valid"] is False
    assert proof["invalid_reason"] == "OpenCode cache-isolation hooks were not proven"


def test_extract_tool_usage_persists_cache_isolation_proof(tmp_path: Path) -> None:
    records = [
        {"type": "thread.started", "thread_id": "thread-proof"},
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 50,
                "output_tokens": 20,
            },
        },
    ]
    (tmp_path / "agent_stdout.log").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n"
    )
    isolation = build_cache_isolation("codex", scope="7" * 32)

    usage = run_task._extract_tool_usage(tmp_path, cache_isolation=isolation)

    assert usage["cache_isolation"]["valid"] is True
    assert usage["cache_isolation"]["scope"] == "thread-proof"


def test_opencode_hook_trace_is_captured_and_consumed(tmp_path: Path) -> None:
    scope = "b" * 32
    isolation = build_cache_isolation("opencode", scope=scope)
    hook_records = [
        {
            "type": "enterprisebench.cache_isolation_hook",
            "scope": scope,
            "hook": "system",
        },
        {
            "type": "enterprisebench.cache_isolation_hook",
            "scope": scope,
            "hook": "headers",
        },
    ]
    provider_record = {
        "type": "step_finish",
        "part": {
            "type": "step-finish",
            "tokens": {"cache": {"read": 0, "write": 0}},
        },
    }
    (tmp_path / "agent_stdout.log").write_text(json.dumps(provider_record) + "\n")
    telemetry = "\n".join(json.dumps(record) for record in hook_records) + "\n"

    with patch.object(
        run_task,
        "_docker_exec",
        return_value=_completed(stdout=telemetry),
    ):
        run_task._capture_cache_isolation_telemetry(
            "container-1",
            tmp_path,
            isolation,
        )

    usage = run_task._extract_tool_usage(
        tmp_path,
        cache_isolation=isolation,
    )

    assert (tmp_path / run_task.OPENCODE_CACHE_ISOLATION_TRACE_FILE).read_text() == telemetry
    assert usage["cache_isolation"]["valid"] is True
    assert usage["cache_isolation"]["hooks_observed"] == ["headers", "system"]


def test_cache_isolation_gate_invalidates_a_contaminated_run() -> None:
    result = run_task.TaskRunResult(
        task_id="task-1",
        tool_usage={
            "cache_isolation": {
                "valid": False,
                "invalid_reason": "OpenCode first step read a prior cache",
            }
        },
    )

    run_task._route_cache_isolation(result)

    assert result.status == run_task.RUN_STATUS_INVALID
    assert result.failure_class == "infra_cache_isolation"
    assert result.phase == "agent_infra_error"
    assert result.error == "OpenCode first step read a prior cache"


def test_cache_isolation_gate_fails_closed_when_proof_is_missing() -> None:
    result = run_task.TaskRunResult(task_id="task-1", tool_usage={})

    run_task._route_cache_isolation(result)

    assert result.status == run_task.RUN_STATUS_INVALID
    assert result.failure_class == "infra_cache_isolation"
    assert result.error == "cache-isolation proof is missing"


def test_run_task_passes_isolation_scope_to_agent_and_records_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_toml = tmp_path / "task.toml"
    task_toml.write_text(
        """
[task]
id = "cache-flow-001"
suite = "customer_escalation"
task_type = "error_provenance"
description = "Cache isolation flow fixture"
prompt = "Inspect the repository."

[artifacts]
required = ["answer"]
""".strip()
        + "\n"
    )
    captured_environment: dict[str, str] = {}
    scope = "8" * 32

    def fake_run_agent(
        _container_id: str,
        _agent_command: object,
        _timeout: int,
        output_dir: Path,
        *,
        env_extra: dict[str, str],
    ) -> tuple[int, float]:
        captured_environment.update(env_extra)
        records = [
            {"type": "thread.started", "thread_id": "fresh-thread"},
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 50,
                    "output_tokens": 10,
                },
            },
        ]
        (output_dir / "agent_stdout.log").write_text(
            "\n".join(json.dumps(record) for record in records) + "\n"
        )
        return (0, 1.0)

    replacements = {
        "_check_disk_space": lambda **_kwargs: True,
        "_docker_create_container": lambda *_args, **_kwargs: "container-1",
        "_docker_start": lambda *_args, **_kwargs: None,
        "_setup_container": lambda *_args, **_kwargs: None,
        "_run_health_check": lambda *_args, **_kwargs: True,
        "_install_harness_cli": lambda *_args, **_kwargs: True,
        "_prepare_harness_credentials": lambda *_args, **_kwargs: {},
        "_stage_cache_isolation": lambda *_args, **_kwargs: {
            "ENTERPRISEBENCH_CACHE_SCOPE": scope
        },
        "_chown_to_agent": lambda *_args, **_kwargs: None,
        "_assert_agent_readable": lambda *_args, **_kwargs: (True, ""),
        "_apply_mode_gate": lambda *_args, **_kwargs: (True, ""),
        "_run_agent": fake_run_agent,
        "_capture_mcp_telemetry": lambda *_args, **_kwargs: None,
        "_scan_mcp_config_error": lambda *_args, **_kwargs: False,
        "_run_scoring": lambda *_args, **_kwargs: {
            "task_score": 1.0,
            "all_passed": True,
        },
        "_save_results": lambda *_args, **_kwargs: None,
        "_docker_stop_rm": lambda *_args, **_kwargs: None,
    }
    for name, replacement in replacements.items():
        monkeypatch.setattr(run_task, name, replacement)
    monkeypatch.setattr(
        run_task,
        "build_cache_isolation",
        lambda _harness: build_cache_isolation("codex", scope=scope),
    )

    result = run_task.run_task(
        run_task.TaskRunConfig(
            task_toml=task_toml,
            harness="codex",
            model="gpt-5.6-sol",
            no_build=True,
            output_dir=tmp_path / "out",
        )
    )

    assert captured_environment["ENTERPRISEBENCH_CACHE_SCOPE"] == scope
    assert result.tool_usage["cache_isolation"]["valid"] is True
    assert result.tool_usage["cache_isolation"]["scope"] == "fresh-thread"
    assert result.status == ""
    assert result.success is True
