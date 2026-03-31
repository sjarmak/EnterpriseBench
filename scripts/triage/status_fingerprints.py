#!/usr/bin/env python3
"""Error fingerprinting for EnterpriseBench task failures.

Classifies error text from agent logs and results.json into known failure
categories with severity, advice, and matched pattern.

Ported from CodeScaleBench's status_fingerprints.py, adapted for EB's
Docker-based sandbox, checkpoint verifiers, and multi-repo task format.

Categories:
    infra    - Docker daemon, OOM, network, auth, disk, API errors
    setup    - Missing deps, image build, clone failures
    verifier - Checkpoint script errors, eb_verify issues
    agent    - Agent quality/hallucination issues
    timeout  - Task or agent timeout
    pass     - (reserved for explicit pass markers)

Standalone usage:
    python3 scripts/triage/status_fingerprints.py path/to/results.json [...]
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union


@dataclass(frozen=True)
class Fingerprint:
    """A single error fingerprint definition."""

    id: str
    label: str
    severity: str
    pattern: str
    advice: str


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# Ordered list of fingerprints. First match wins, so most specific first.
FINGERPRINTS: list[Fingerprint] = [
    # ── Infra: OOM ──────────────────────────────────────────────────────
    Fingerprint(
        id="oom_killed",
        label="Container killed by OOM",
        severity="infra",
        pattern=r"OOMKill|out of memory|cannot allocate memory",
        advice="Increase --memory limit in run_task.py or reduce task memory requirements.",
    ),
    # ── Infra: disk ─────────────────────────────────────────────────────
    Fingerprint(
        id="disk_full",
        label="No disk space left",
        severity="infra",
        pattern=r"no space left on device|ENOSPC|disk quota exceeded",
        advice="Free disk space or increase volume size. Check docker system df.",
    ),
    # ── Infra: Docker daemon ────────────────────────────────────────────
    Fingerprint(
        id="docker_daemon",
        label="Docker daemon unavailable",
        severity="infra",
        pattern=r"Cannot connect to the Docker daemon|docker.*daemon.*not running|Is the docker daemon running",
        advice="Start the Docker daemon: sudo systemctl start docker",
    ),
    # ── Infra: permission denied ────────────────────────────────────────
    Fingerprint(
        id="permission_denied",
        label="Permission denied",
        severity="infra",
        pattern=r"permission denied|EACCES|Operation not permitted",
        advice="Check file/directory permissions. Docker socket may need group membership.",
    ),
    # ── Infra: network ──────────────────────────────────────────────────
    Fingerprint(
        id="network_failure",
        label="Network connectivity failure",
        severity="infra",
        pattern=r"name resolution|DNS.*fail|network.*unreachable|connection refused|ETIMEDOUT|ECONNREFUSED|Could not resolve host",
        advice="Check network connectivity and DNS. Verify firewall rules.",
    ),
    # ── Infra: auth/token ───────────────────────────────────────────────
    Fingerprint(
        id="token_auth_failure",
        label="Authentication/token failure",
        severity="infra",
        pattern=r"403.*Forbidden|credentials.*expired|token.*refresh.*fail|refresh.*token.*fail|401.*Unauthorized",
        advice="Re-authenticate. Check API credentials and token expiry.",
    ),
    # ── Infra: API rate limit ───────────────────────────────────────────
    Fingerprint(
        id="api_rate_limit",
        label="API rate limit / overloaded",
        severity="infra",
        pattern=r"rate.?limit|429|too many requests|throttl|overloaded",
        advice="Reduce parallelism or wait before retrying. Check account quotas.",
    ),
    # ── Infra: API 500 ──────────────────────────────────────────────────
    Fingerprint(
        id="api_500",
        label="API server error (5xx)",
        severity="infra",
        pattern=r"500\s*Internal Server Error|api.*500|server.*error.*5\d{2}",
        advice="Transient API issue; retry the task. If persistent, check API status.",
    ),
    # ── Infra: context window ───────────────────────────────────────────
    Fingerprint(
        id="context_window_exceeded",
        label="Context window exceeded",
        severity="infra",
        pattern=r"conversation is too long|context_window|context window|max_tokens exceeded|maximum context length|prompt is too long",
        advice="Task hit context window limit. Not a task quality failure.",
    ),
    # ── Setup: Docker build ─────────────────────────────────────────────
    Fingerprint(
        id="docker_build_fail",
        label="Docker image build failure",
        severity="setup",
        pattern=r"Docker build failed|docker build.*(?:fail|error)|dockerfile.*(?:error|fail)",
        advice="Check Dockerfile and build logs. Verify base image availability.",
    ),
    # ── Setup: npm ──────────────────────────────────────────────────────
    Fingerprint(
        id="npm_install_fail",
        label="npm install failure",
        severity="setup",
        pattern=r"npm ERR!|npm install.*fail|yarn.*(?:error|fail).*install",
        advice="Check package.json and npm registry access. May need --legacy-peer-deps.",
    ),
    # ── Setup: pip ──────────────────────────────────────────────────────
    Fingerprint(
        id="pip_install_fail",
        label="pip install failure",
        severity="setup",
        pattern=r"pip install.*fail|No matching distribution|Could not find a version",
        advice="Check requirements.txt and PyPI access. May need version constraint fix.",
    ),
    # ── Setup: import error ─────────────────────────────────────────────
    Fingerprint(
        id="import_error",
        label="Python import error",
        severity="setup",
        pattern=r"ImportError|ModuleNotFoundError|No module named|cannot import name",
        advice="Missing dependency. Update Dockerfile or requirements.txt.",
    ),
    # ── Setup: git clone ────────────────────────────────────────────────
    Fingerprint(
        id="git_clone_fail",
        label="Git clone/checkout failure",
        severity="setup",
        pattern=r"fatal:.*(?:repository|git)|git.*clone.*fail|repository not found|git.*checkout.*fail",
        advice="Check repository URL and network access. Verify git credentials.",
    ),
    # ── Timeout ─────────────────────────────────────────────────────────
    Fingerprint(
        id="timeout",
        label="Task timeout",
        severity="timeout",
        pattern=r"timeout|timed?\s*out|deadline exceeded|SIGTERM|killed.*signal|exceeded.*\d+\s*(?:s|sec|seconds)",
        advice="Task exceeded time limit. Consider increasing timeout or simplifying task.",
    ),
    # ── Verifier: eb_verify ─────────────────────────────────────────────
    Fingerprint(
        id="eb_verify_error",
        label="eb_verify plugin error",
        severity="verifier",
        pattern=r"eb_verify.*(?:error|fail|exception|raised)|plugin.*(?:raised|error|fail).*(?:ValueError|TypeError|KeyError)",
        advice="Check eb_verify plugin implementation. Validate artifact format.",
    ),
    # ── Verifier: checkpoint script ─────────────────────────────────────
    Fingerprint(
        id="checkpoint_script_error",
        label="Checkpoint script error",
        severity="verifier",
        pattern=r"checkpoint.*(?:script|\.sh).*(?:exit|fail|error)|\.verifiers/.*(?:error|fail)",
        advice="Check checkpoint script logic. May be a verifier bug, not agent failure.",
    ),
    # ── Verifier: JSON decode ───────────────────────────────────────────
    Fingerprint(
        id="verifier_parse_error",
        label="Verifier output parse error",
        severity="verifier",
        pattern=r"JSONDecodeError.*verifier|verifier.*(?:parse|json|decode|invalid)|reward.*parse",
        advice="Check verifier script output format. Ensure valid JSON output.",
    ),
    # ── Verifier: test.sh ───────────────────────────────────────────────
    Fingerprint(
        id="test_runner_fail",
        label="test.sh runner failure",
        severity="verifier",
        pattern=r"test\.sh.*(?:fail|error|exit code)",
        advice="Check test_runner.sh and checkpoint scripts for bugs.",
    ),
    # ── Agent: no output ────────────────────────────────────────────────
    Fingerprint(
        id="agent_no_output",
        label="Agent produced no output",
        severity="agent",
        pattern=r"no output|produced no.*(?:output|file|answer)|answer\.json.*not found|agent_output.*(?:missing|empty|not found)",
        advice="Agent did not write required output. May need clearer instructions.",
    ),
    # ── Agent: hallucinated reference ───────────────────────────────────
    Fingerprint(
        id="agent_hallucination",
        label="Agent referenced nonexistent file",
        severity="agent",
        pattern=r"does not exist|file not found|nonexistent|hallucinated|referenced.*not.*exist",
        advice="Agent hallucinated file paths. May indicate poor codebase navigation.",
    ),
]

# Pre-compiled patterns (same order as FINGERPRINTS)
_COMPILED: list[tuple[Fingerprint, re.Pattern[str]]] = [
    (fp, _compile(fp.pattern)) for fp in FINGERPRINTS
]


def match_fingerprint(
    text: Union[str, dict, None],
) -> Optional[Fingerprint]:
    """Classify error text into a known failure category.

    Args:
        text: Error text to classify. Can be:
            - A string (log output or error message)
            - A dict with 'type', 'message', 'traceback' keys (results.json)
            - None (returns None)

    Returns:
        The first matching Fingerprint, or None if no match.
    """
    if text is None:
        return None

    # Build searchable string
    if isinstance(text, dict):
        parts = [
            str(text.get("type", "")),
            str(text.get("message", "")),
            str(text.get("traceback", "")),
        ]
        search_text = " ".join(parts)
    elif isinstance(text, str):
        search_text = text
    else:
        search_text = str(text)

    if not search_text.strip():
        return None

    for fp, compiled in _COMPILED:
        if compiled.search(search_text):
            return fp

    return None


def main() -> None:
    """CLI: fingerprint one or more results.json files."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} path/to/results.json [...]", file=sys.stderr)
        sys.exit(1)

    for path_str in sys.argv[1:]:
        path = Path(path_str)
        if not path.is_file():
            print(f"SKIP (not a file): {path}")
            continue

        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"SKIP (read error): {path}: {e}")
            continue

        error = data.get("error", "")
        if not error:
            print(f"  OK (no error): {path}")
            continue

        fp = match_fingerprint(error)
        if fp is None:
            print(f"  UNKNOWN: {path}")
            print(f"         error: {error[:120]}")
        else:
            sev = fp.severity.upper()
            print(f"  [{sev}] {fp.id}: {fp.label}")
            print(f"         advice: {fp.advice}")
            print(f"         file:   {path}")
        print()


if __name__ == "__main__":
    main()
