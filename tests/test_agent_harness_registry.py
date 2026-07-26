"""Unit tests for benchmark agent harness planning."""

from __future__ import annotations

import pytest

from agents.harnesses.registry import (
    CODEX_NPM_PACKAGE,
    OPENCODE_NPM_PACKAGE,
    HarnessConfigurationError,
    build_harness_plan,
    harness_variant_label,
)


def test_codex_plan_uses_real_noninteractive_cli() -> None:
    plan = build_harness_plan("codex", model="gpt-5.6-sol", mode="baseline")

    assert plan.command == (
        "codex",
        "exec",
        "--model",
        "gpt-5.6-sol",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "-",
    )
    assert plan.binary == "codex"
    assert plan.npm_package == CODEX_NPM_PACKAGE


def test_codex_mcp_plan_loads_isolated_config() -> None:
    plan = build_harness_plan("codex", model="gpt-5.6-sol", mode="mcp_only")

    assert plan.command == (
        "codex",
        "exec",
        "--model",
        "gpt-5.6-sol",
        "--json",
        "--ephemeral",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "-",
    )
    assert "--ignore-user-config" not in plan.command


def test_codex_cli_plan_ignores_mcp_user_config() -> None:
    plan = build_harness_plan("codex", model="gpt-5.6-sol", mode="cli")

    assert "--ignore-user-config" in plan.command


def test_opencode_plan_uses_explicit_provider_model_and_auto_permissions() -> None:
    plan = build_harness_plan(
        "opencode",
        model="openrouter/deepseek/deepseek-v4-pro",
        mode="baseline",
    )

    assert plan.command == (
        "opencode",
        "run",
        "--model",
        "openrouter/deepseek/deepseek-v4-pro",
        "--format",
        "json",
        "--auto",
    )
    assert "--pure" not in plan.command
    assert plan.binary == "opencode"
    assert plan.npm_package == OPENCODE_NPM_PACKAGE
    assert plan.required_env == ("OPENROUTER_API_KEY",)


def test_opencode_mcp_plan_preserves_noninteractive_cli_contract() -> None:
    plan = build_harness_plan(
        "opencode",
        model="openrouter/moonshotai/kimi-k3",
        mode="mcp_only",
    )

    assert plan.command == (
        "opencode",
        "run",
        "--model",
        "openrouter/moonshotai/kimi-k3",
        "--format",
        "json",
        "--auto",
    )
    assert "--pure" not in plan.command


def test_opencode_cli_plan_preserves_noninteractive_cli_contract() -> None:
    plan = build_harness_plan(
        "opencode",
        model="openrouter/moonshotai/kimi-k3",
        mode="cli",
    )

    assert plan.command == (
        "opencode",
        "run",
        "--model",
        "openrouter/moonshotai/kimi-k3",
        "--format",
        "json",
        "--auto",
    )
    assert "--pure" not in plan.command


@pytest.mark.parametrize("harness", ["codex", "opencode"])
def test_new_harnesses_require_explicit_models(harness: str) -> None:
    with pytest.raises(HarnessConfigurationError, match="requires --model"):
        build_harness_plan(harness, model=None, mode="baseline")


@pytest.mark.parametrize(
    ("harness", "mode"),
    [
        ("codex", "hybrid"),
        ("opencode", "hybrid"),
    ],
)
def test_new_harnesses_fail_closed_on_claude_specific_modes(
    harness: str, mode: str
) -> None:
    with pytest.raises(HarnessConfigurationError, match="does not support mode"):
        build_harness_plan(
            harness,
            model=(
                "gpt-5.6-sol"
                if harness == "codex"
                else "openrouter/openai/gpt-oss-120b"
            ),
            mode=mode,
        )


def test_opencode_initially_requires_openrouter_model_ids() -> None:
    with pytest.raises(HarnessConfigurationError, match="openrouter/"):
        build_harness_plan("opencode", model="ollama/qwen3-coder", mode="baseline")


def test_generated_harness_rejects_legacy_agent_override() -> None:
    with pytest.raises(HarnessConfigurationError, match="cannot be combined"):
        build_harness_plan(
            "codex",
            model="gpt-5.6-sol",
            mode="baseline",
            agent_command="codex exec -",
        )


def test_claude_preserves_legacy_agent_command() -> None:
    plan = build_harness_plan(
        "claude",
        model=None,
        mode="baseline",
        agent_command="claude -p",
    )
    assert plan.command == ("claude", "-p")
    assert plan.npm_package is None


@pytest.mark.parametrize(
    ("harness", "model", "expected"),
    [
        ("codex", "gpt-5.6-sol", "codex-gpt-5-6-sol-2507d95681"),
        (
            "opencode",
            "openrouter/deepseek/deepseek-v4-pro",
            "opencode-openrouter-deepseek-deepseek-v4-pro-600d7d9311",
        ),
    ],
)
def test_generated_harness_has_stable_run_label(
    harness: str, model: str, expected: str
) -> None:
    assert harness_variant_label(harness, model) == expected


def test_long_model_ids_get_collision_resistant_variant_labels() -> None:
    shared_prefix = "openrouter/vendor/" + ("model-segment-" * 12)

    first = harness_variant_label("opencode", shared_prefix + "a")
    second = harness_variant_label("opencode", shared_prefix + "b")

    assert first != second
    assert len(first) <= 96
    assert len(second) <= 96


def test_separator_normalization_cannot_collapse_distinct_model_ids() -> None:
    first = harness_variant_label("opencode", "openrouter/foo/bar-baz")
    second = harness_variant_label("opencode", "openrouter/foo-bar/baz")

    assert first != second
    assert first.startswith("opencode-openrouter-foo-bar-baz-")
    assert second.startswith("opencode-openrouter-foo-bar-baz-")


def test_case_distinct_model_ids_cannot_overwrite_each_other() -> None:
    first = harness_variant_label("opencode", "openrouter/Foo/Model")
    second = harness_variant_label("opencode", "openrouter/foo/model")

    assert first != second
