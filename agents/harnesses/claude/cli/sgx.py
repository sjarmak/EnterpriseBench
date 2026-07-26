"""sgx (CLI arm) preamble builder for EnterpriseBench.

The `cli` arm gives the agent the same remote Sourcegraph retrieval reach as the
MCP arms, but exposed as a plain shell command (`/usr/local/bin/sgx`) rather
than registered MCP tools. There are NO MCP tools in this environment and no
`.mcp.json` — the lean tool prefix is the experimental point, and `sgx` composes
with pipes, `head`, `&&`, and Task subagents like any local command.

This mirrors ``sourcegraph.build_system_prompt``: it dispatches on mode and
concatenates section constants into the instruction preamble. Ported from CSB's
``SG_CLI_V1_PREAMBLE`` (claude_baseline_agent.py), adapted to EB's repo-scope
shape (sg-evals mirror names via ``derive_mirror_name``).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "infra"))
from mirror_naming import derive_mirror_name  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Preamble sections
# ---------------------------------------------------------------------------

# Named `sgx` (not `sg`): shadow-utils ships /usr/bin/sg (setgroups) in the task
# images and it shadows an `sg` wrapper in PATH. The "NO MCP tools" line stops
# the agent from burning ToolSearch calls hunting for nonexistent MCP tools.
_HEADER = (
    "# IMPORTANT: Source Code Access — `sgx` command\n\n"
    "There are **NO MCP tools in this environment** — all remote code "
    "retrieval is via the `sgx` shell command (run it in Bash; do not search "
    "for MCP tools). Use only the mode-specific `sgx` workflow below for "
    "remote code retrieval via Sourcegraph."
)

_USAGE = """\
## `sgx` usage (a normal command — composes with pipes, `head`, `&&`; works inside Task subagents)

- `sgx search 'QUERY'` — keyword search; Sourcegraph filters pass through (`repo:`, `file:`, `count:`, `type:`).
- **Prefer combining related queries in ONE call:** `sgx search 'q1' -q 'q2' -q 'q3'` runs them concurrently and returns per-query results.
  Example: `sgx search 'ParseConfig repo:^github.com/org/repo$' -q 'loadConfig repo:^github.com/org/repo$'`
- `sgx read REPO PATH --start N --end M` — read a line range (no range = first 120 lines only; always prefer targeted ranges).
- `sgx def REPO PATH SYMBOL` / `sgx refs REPO PATH SYMBOL` — jump to a symbol's definition / list its callers.
- `sgx nls 'natural language question'` — semantic search when you don't know exact terms.
- `sgx ls REPO [DIR]` — list files. Pipe long output: `sgx search '...' | head -40`."""

_WORKFLOW = """\
## Workflow

1. **Search first** — one batched `sgx search` (scoped with `repo:`, several `-q` queries); judge from the returned line-numbered snippets.
2. **Read only the span you need** — `sgx read REPO PATH --start N --end M` around the hits.
3. **Navigate** — `sgx def` / `sgx refs` to trace symbols across repo boundaries.
4. **Then implement** — once you understand the pattern, stop searching and start writing."""

_DIRECT_CLI_RULE = """\
## Direct CLI Arm

Do not use `sgx finder`. This arm measures direct Sourcegraph retrieval through \
the search, navigation, and file-reading commands below; the `code_finder` \
backend is measured separately."""

_FINDER_USAGE = """\
## Required Code Finder Workflow

Use `sgx finder` **exactly once per repository**, passing the task description \
as one quoted argument. Give each \
call a comprehensive description of the task, failure symptoms, and evidence \
needed from that repository. Include that repository's exact Sourcegraph mirror \
name in the task text so invocation scope is auditable.

Do not use any other `sgx` retrieval command. This prohibition includes \
`sgx search`, `sgx nls`, `sgx read`, `sgx def`, `sgx refs`, and `sgx ls`. \
This arm measures the `code_finder` backend through a Bash-composable CLI without registering \
any MCP tools.

You may use the shell only to reason over already-returned context and to write \
the required `/workspace/agent_output/answer.json`. Local repository source is \
filesystem-gated and must not be read."""


# ---------------------------------------------------------------------------
# Repo scope builder
# ---------------------------------------------------------------------------


def _build_repo_scope(repos: Sequence[dict]) -> str:
    """Build the sgx repo-scoping section from task repos.

    Maps each task repo (e.g. github.com/grpc/grpc-go@v1.4.0) to its sg-evals
    mirror name so `sgx search ... repo:^github.com/<mirror>$` scopes correctly.
    """
    if not repos:
        return ""

    lines = ["## Repository Scoping\n"]
    lines.append(
        "These repos are indexed on Sourcegraph under `sg-evals/` mirrors. "
        "**Use these exact mirror names to scope every `sgx` request:**\n"
    )

    for repo in repos:
        url = repo.get("url", "")
        rev = repo.get("rev", "")
        path = repo.get("path", "")
        if not url:
            continue

        org_repo = (
            url.replace("https://github.com/", "")
            .replace("http://github.com/", "")
            .rstrip("/")
        )
        if org_repo.endswith(".git"):
            org_repo = org_repo[:-4]
        repo_name = org_repo.split("/")[-1]

        sg_mirror = derive_mirror_name(url, rev)

        lines.append(f"- **{path or repo_name}**")
        lines.append(f"  - sgx filter: `repo:^github.com/{sg_mirror}$`")
        lines.append(f"  - Upstream: `{org_repo}@{rev}`")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_system_prompt(
    mode: str,
    repos: Sequence[dict] | None = None,
) -> str:
    """Assemble the sgx CLI-arm preamble.

    Args:
        mode: Expected to be "cli" or "cli_code_finder". Any other mode
            returns an empty string.
        repos: List of repo dicts from task.toml (each with url, rev, path).

    Returns:
        The assembled preamble string, or empty string for non-cli modes.
    """
    if mode not in {"cli", "cli_code_finder"}:
        if mode not in (
            "baseline",
            "mcp_only",
            "mcp_code_finder",
            "mcp_assisted",
            "hybrid",
        ):
            logger.warning("Unknown mode %r; returning empty sgx preamble", mode)
        return ""

    parts: list[str] = [_HEADER]

    repo_scope = _build_repo_scope(repos or [])
    if repo_scope:
        parts.append(repo_scope)

    if mode == "cli_code_finder":
        parts.append(_FINDER_USAGE)
    else:
        parts.append(_DIRECT_CLI_RULE)
        parts.append(_USAGE)
        parts.append(_WORKFLOW)

    return "\n\n".join(parts)
