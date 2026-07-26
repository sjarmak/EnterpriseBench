"""Typed execution plans for benchmark coding-agent harnesses."""

from __future__ import annotations

import hashlib
import re
import shlex
from dataclasses import dataclass

CODEX_NPM_PACKAGE = "@openai/codex@0.145.0"
OPENCODE_NPM_PACKAGE = "opencode-ai@1.18.4"

HARNESS_NAMES = ("claude", "codex", "opencode")
_BASELINE_MODE = "baseline"
_MCP_MODES = frozenset({"mcp_only", "mcp_code_finder", "mcp_assisted"})
_SUPPORTED_MODES = {
    "codex": frozenset({_BASELINE_MODE, *_MCP_MODES, "cli"}),
    "opencode": frozenset({_BASELINE_MODE, *_MCP_MODES, "cli"}),
}
_SAFE_LABEL_CHARS = re.compile(r"[^a-z0-9]+")


class HarnessConfigurationError(ValueError):
    """The requested harness configuration cannot produce a comparable run."""


@dataclass(frozen=True)
class HarnessPlan:
    """Immutable command, installation, and credential contract for one run."""

    name: str
    model: str | None
    command: tuple[str, ...]
    binary: str
    npm_package: str | None = None
    required_env: tuple[str, ...] = ()

    @property
    def rendered_command(self) -> str:
        """Shell-escaped display form for logs and result metadata."""
        return shlex.join(self.command)


def _require_model(harness: str, model: str | None) -> str:
    value = (model or "").strip()
    if not value:
        raise HarnessConfigurationError(f"harness={harness} requires --model")
    return value


def _require_supported_mode(harness: str, mode: str) -> None:
    supported = _SUPPORTED_MODES.get(harness, frozenset({_BASELINE_MODE}))
    if mode not in supported:
        raise HarnessConfigurationError(
            f"harness={harness} does not support mode={mode!r}; "
            f"supported modes: {', '.join(sorted(supported))}"
        )


def build_harness_plan(
    harness: str,
    *,
    model: str | None,
    mode: str,
    agent_command: str = "",
) -> HarnessPlan:
    """Resolve user-facing harness options into an executable CLI plan."""
    normalized = harness.strip().lower()
    if normalized not in HARNESS_NAMES:
        raise HarnessConfigurationError(
            f"unknown harness {harness!r}; choose from {', '.join(HARNESS_NAMES)}"
        )

    if normalized == "claude":
        try:
            command = tuple(shlex.split(agent_command)) if agent_command else ()
        except ValueError as exc:
            raise HarnessConfigurationError(f"invalid --agent command: {exc}") from exc
        return HarnessPlan(
            name=normalized,
            model=model,
            command=command,
            binary="claude",
        )

    if agent_command:
        raise HarnessConfigurationError(
            f"--agent cannot be combined with --harness {normalized}; "
            "the selected harness generates its command"
        )

    _require_supported_mode(normalized, mode)
    selected_model = _require_model(normalized, model)

    if normalized == "codex":
        config_args = () if mode in _MCP_MODES else ("--ignore-user-config",)
        return HarnessPlan(
            name=normalized,
            model=selected_model,
            command=(
                "codex",
                "exec",
                "--model",
                selected_model,
                "--json",
                "--ephemeral",
                *config_args,
                "--skip-git-repo-check",
                "--dangerously-bypass-approvals-and-sandbox",
                "-",
            ),
            binary="codex",
            npm_package=CODEX_NPM_PACKAGE,
        )

    if not selected_model.startswith("openrouter/") or selected_model.count("/") < 2:
        raise HarnessConfigurationError(
            "harness=opencode currently requires an OpenRouter model ID in "
            "provider/model form, for example "
            "openrouter/deepseek/deepseek-v4-pro"
        )
    return HarnessPlan(
        name=normalized,
        model=selected_model,
        command=(
            "opencode",
            "run",
            "--model",
            selected_model,
            "--format",
            "json",
            "--pure",
            "--auto",
        ),
        binary="opencode",
        npm_package=OPENCODE_NPM_PACKAGE,
        required_env=("OPENROUTER_API_KEY",),
    )


def harness_variant_label(harness: str, model: str | None) -> str | None:
    """Return a stable path-safe label for a generated non-Claude harness."""
    normalized = harness.strip().lower()
    if normalized == "claude":
        return None
    raw_identity = f"{normalized}-{model or 'default'}"
    display_identity = raw_identity.lower()
    label = _SAFE_LABEL_CHARS.sub("-", display_identity).strip("-")
    if not label:
        raise HarnessConfigurationError("harness/model did not produce a run label")
    if label == raw_identity and len(label) <= 96:
        return label
    digest = hashlib.sha256(raw_identity.encode()).hexdigest()[:10]
    prefix = label[: 96 - len(digest) - 1].rstrip("-")
    return f"{prefix}-{digest}"
