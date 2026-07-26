"""Provider-specific proof that benchmark runs cannot share prompt caches."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

_SCOPE_RE = re.compile(r"^[a-f0-9]{32}$")
_HARNESS_MECHANISMS = {
    "claude": "prompt-caching-disabled",
    "codex": "fresh-session-prompt-cache-key",
    "opencode": "unique-system-prefix-and-session",
}


class CacheIsolationError(ValueError):
    """A harness cannot establish an unambiguous cache-isolation scope."""


@dataclass(frozen=True)
class CacheIsolation:
    """Immutable launcher contract for one measured invocation."""

    harness: str
    scope: str
    mechanism: str
    environment: Mapping[str, str]


def build_cache_isolation(
    harness: str,
    *,
    scope: str | None = None,
) -> CacheIsolation:
    """Create a fresh cache scope and the environment that enforces it."""

    normalized = harness.strip().lower()
    mechanism = _HARNESS_MECHANISMS.get(normalized)
    if mechanism is None:
        raise CacheIsolationError(f"unsupported cache-isolation harness: {harness!r}")

    selected_scope = scope if scope is not None else secrets.token_hex(16)
    if not _SCOPE_RE.fullmatch(selected_scope):
        raise CacheIsolationError(
            "cache-isolation scope must be exactly 32 lowercase hex characters"
        )

    environment = {"ENTERPRISEBENCH_CACHE_SCOPE": selected_scope}
    if normalized == "claude":
        environment = {
            "DISABLE_PROMPT_CACHING": "1",
            **environment,
        }
    elif normalized == "opencode":
        environment = {
            **environment,
            "OPENCODE_CONFIG_DIR": "/home/agent/.config/opencode",
            "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
        }

    return CacheIsolation(
        harness=normalized,
        scope=selected_scope,
        mechanism=mechanism,
        environment=MappingProxyType(environment),
    )


def evaluate_cache_isolation(
    isolation: CacheIsolation,
    records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Return an auditable, fail-closed proof from provider-native telemetry."""

    evaluators = {
        "claude": _evaluate_claude,
        "codex": _evaluate_codex,
        "opencode": _evaluate_opencode,
    }
    return evaluators[isolation.harness](isolation, records)


def _base_proof(isolation: CacheIsolation) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "harness": isolation.harness,
        "scope": isolation.scope,
        "launcher_scope": isolation.scope,
        "mechanism": isolation.mechanism,
        "configured": True,
    }


def _non_negative_int(value: Any) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else 0
    )


def _cache_token_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _claude_cache_counts(model_usage: dict[str, Any]) -> tuple[int, int] | None:
    entries = (
        (model_usage,)
        if "inputTokens" in model_usage
        else tuple(value for value in model_usage.values() if isinstance(value, dict))
    )
    counts = tuple(
        (
            _cache_token_int(entry.get("cacheReadInputTokens")),
            _cache_token_int(entry.get("cacheCreationInputTokens")),
        )
        for entry in entries
    )
    if not counts or any(read is None or write is None for read, write in counts):
        return None
    return (
        sum(read for read, _write in counts if read is not None),
        sum(write for _read, write in counts if write is not None),
    )


def _evaluate_claude(
    isolation: CacheIsolation,
    records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    model_usages = [
        model_usage
        for record in records
        if isinstance((model_usage := record.get("modelUsage")), dict)
    ]
    if not model_usages:
        return {
            **_base_proof(isolation),
            "valid": False,
            "invalid_reason": "Claude cache telemetry is missing",
            "cross_run_cache_read_tokens": None,
            "total_cache_read_tokens": None,
            "cache_write_tokens": None,
        }

    cache_counts = _claude_cache_counts(model_usages[-1])
    if cache_counts is None:
        return {
            **_base_proof(isolation),
            "valid": False,
            "invalid_reason": "Claude cache telemetry is incomplete",
            "cross_run_cache_read_tokens": None,
            "total_cache_read_tokens": None,
            "cache_write_tokens": None,
        }

    reads, writes = cache_counts
    valid = reads == 0 and writes == 0
    return {
        **_base_proof(isolation),
        "valid": valid,
        "invalid_reason": None if valid else "Claude reported prompt-cache reuse",
        "cross_run_cache_read_tokens": reads,
        "total_cache_read_tokens": reads,
        "cache_write_tokens": writes,
        "verification": "all Claude cache reads and writes are zero",
    }


def _evaluate_codex(
    isolation: CacheIsolation,
    records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    thread_ids = tuple(
        str(record["thread_id"])
        for record in records
        if record.get("type") == "thread.started"
        and isinstance(record.get("thread_id"), str)
        and record["thread_id"]
    )
    unique_thread_ids = tuple(dict.fromkeys(thread_ids))
    if not unique_thread_ids:
        return {
            **_base_proof(isolation),
            "valid": False,
            "invalid_reason": "Codex thread cache scope is missing",
            "cross_run_cache_read_tokens": None,
            "total_cache_read_tokens": None,
            "cache_write_tokens": None,
        }
    if len(unique_thread_ids) != 1:
        return {
            **_base_proof(isolation),
            "valid": False,
            "invalid_reason": "Codex emitted multiple thread cache scopes",
            "cross_run_cache_read_tokens": None,
            "total_cache_read_tokens": None,
            "cache_write_tokens": None,
        }

    usages = tuple(
        usage
        for record in records
        if record.get("type") == "turn.completed"
        and isinstance((usage := record.get("usage")), dict)
    )
    total_reads = sum(
        _non_negative_int(usage.get("cached_input_tokens")) for usage in usages
    )
    total_writes = sum(
        _non_negative_int(usage.get("cache_write_input_tokens")) for usage in usages
    )
    return {
        **_base_proof(isolation),
        "scope": unique_thread_ids[0],
        "valid": True,
        "invalid_reason": None,
        "cross_run_cache_read_tokens": 0,
        "total_cache_read_tokens": total_reads,
        "cache_write_tokens": total_writes,
        "verification": "fresh Codex thread ID",
    }


def _is_opencode_step_finish(record: dict[str, Any]) -> bool:
    part = record.get("part")
    return (
        record.get("type") == "step_finish"
        and isinstance(part, dict)
        and part.get("type") == "step-finish"
    )


def _opencode_cache_counts(record: dict[str, Any]) -> tuple[int, int] | None:
    part = record["part"]
    tokens = part.get("tokens")
    if not isinstance(tokens, dict):
        return None
    cache = tokens.get("cache")
    if not isinstance(cache, dict):
        return None
    read = _cache_token_int(cache.get("read"))
    write = _cache_token_int(cache.get("write"))
    if read is None or write is None:
        return None
    return (read, write)


def _evaluate_opencode(
    isolation: CacheIsolation,
    records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    hook_records = tuple(
        record
        for record in records
        if record.get("type") == "enterprisebench.cache_isolation_hook"
    )
    hook_names = {
        record.get("hook")
        for record in hook_records
        if record.get("scope") == isolation.scope
    }
    hooks_valid = (
        bool(hook_records)
        and all(record.get("scope") == isolation.scope for record in hook_records)
        and {"system", "headers"}.issubset(hook_names)
    )
    if not hooks_valid:
        return {
            **_base_proof(isolation),
            "valid": False,
            "invalid_reason": "OpenCode cache-isolation hooks were not proven",
            "cross_run_cache_read_tokens": None,
            "total_cache_read_tokens": None,
            "cache_write_tokens": None,
            "hooks_observed": sorted(str(name) for name in hook_names if name),
        }

    step_records = tuple(record for record in records if _is_opencode_step_finish(record))
    if not step_records:
        return {
            **_base_proof(isolation),
            "valid": False,
            "invalid_reason": "OpenCode cache telemetry is missing",
            "cross_run_cache_read_tokens": None,
            "total_cache_read_tokens": None,
            "cache_write_tokens": None,
        }

    first_counts = _opencode_cache_counts(step_records[0])
    if first_counts is None:
        return {
            **_base_proof(isolation),
            "valid": False,
            "invalid_reason": "OpenCode first-step cache telemetry is missing",
            "cross_run_cache_read_tokens": None,
            "total_cache_read_tokens": None,
            "cache_write_tokens": None,
            "hooks_observed": sorted(str(name) for name in hook_names if name),
        }

    cache_counts = tuple(_opencode_cache_counts(record) for record in step_records)
    if any(counts is None for counts in cache_counts):
        return {
            **_base_proof(isolation),
            "valid": False,
            "invalid_reason": "OpenCode cache telemetry is incomplete",
            "cross_run_cache_read_tokens": first_counts[0],
            "total_cache_read_tokens": None,
            "cache_write_tokens": None,
            "hooks_observed": sorted(str(name) for name in hook_names if name),
        }
    complete_counts = tuple(counts for counts in cache_counts if counts is not None)
    first_reads = first_counts[0]
    total_reads = sum(reads for reads, _writes in complete_counts)
    total_writes = sum(writes for _reads, writes in complete_counts)
    valid = first_reads == 0
    return {
        **_base_proof(isolation),
        "valid": valid,
        "invalid_reason": None if valid else "OpenCode first step read a prior cache",
        "cross_run_cache_read_tokens": first_reads,
        "total_cache_read_tokens": total_reads,
        "cache_write_tokens": total_writes,
        "hooks_observed": sorted(str(name) for name in hook_names if name),
        "verification": "zero cache reads on first OpenCode step",
    }


__all__ = [
    "CacheIsolation",
    "CacheIsolationError",
    "build_cache_isolation",
    "evaluate_cache_isolation",
]
