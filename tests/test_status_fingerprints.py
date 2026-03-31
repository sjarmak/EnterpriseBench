"""Tests for scripts/triage/status_fingerprints.py."""

import sys
from pathlib import Path

import pytest

# Ensure scripts/triage is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "triage"))

from status_fingerprints import Fingerprint, FINGERPRINTS, match_fingerprint


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------

class TestFingerprint:
    """Test the Fingerprint dataclass."""

    def test_fingerprint_is_frozen(self) -> None:
        fp = Fingerprint(
            id="test",
            label="Test",
            severity="infra",
            pattern="test",
            advice="Do something.",
        )
        with pytest.raises(AttributeError):
            fp.id = "changed"  # type: ignore[misc]

    def test_fingerprint_fields(self) -> None:
        fp = Fingerprint(
            id="test",
            label="Test label",
            severity="setup",
            pattern="foo.*bar",
            advice="Fix it.",
        )
        assert fp.id == "test"
        assert fp.label == "Test label"
        assert fp.severity == "setup"
        assert fp.pattern == "foo.*bar"
        assert fp.advice == "Fix it."


class TestFingerprintsList:
    """Sanity checks on the global FINGERPRINTS list."""

    def test_not_empty(self) -> None:
        assert len(FINGERPRINTS) > 0

    def test_all_entries_are_fingerprints(self) -> None:
        for fp in FINGERPRINTS:
            assert isinstance(fp, Fingerprint)

    def test_ids_unique(self) -> None:
        ids = [fp.id for fp in FINGERPRINTS]
        assert len(ids) == len(set(ids)), f"Duplicate fingerprint IDs: {ids}"

    def test_severities_valid(self) -> None:
        valid = {"infra", "setup", "verifier", "agent", "timeout", "pass"}
        for fp in FINGERPRINTS:
            assert fp.severity in valid, f"{fp.id} has invalid severity: {fp.severity}"


# ---------------------------------------------------------------------------
# Infra patterns
# ---------------------------------------------------------------------------

class TestInfraPatterns:
    """Infra category: docker daemon, OOM, network, auth."""

    def test_docker_daemon_not_running(self) -> None:
        text = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "infra"

    def test_oom_killed(self) -> None:
        text = "Container killed due to OOMKilled"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "infra"

    def test_permission_denied(self) -> None:
        text = "permission denied while trying to connect to Docker"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "infra"

    def test_network_unreachable(self) -> None:
        text = "dial tcp: lookup registry-1.docker.io: Temporary failure in name resolution"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "infra"

    def test_disk_space(self) -> None:
        text = "no space left on device"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "infra"

    def test_api_rate_limit(self) -> None:
        text = "429 Too Many Requests - rate limit exceeded"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "infra"

    def test_api_500(self) -> None:
        text = "500 Internal Server Error from API"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "infra"

    def test_context_window_exceeded(self) -> None:
        text = "conversation is too long for context window"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "infra"

    def test_token_auth_failure(self) -> None:
        text = "403 Forbidden: credentials expired, token refresh failed"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "infra"


# ---------------------------------------------------------------------------
# Setup patterns
# ---------------------------------------------------------------------------

class TestSetupPatterns:
    """Setup category: missing deps, image build, clone failures."""

    def test_npm_install_fail(self) -> None:
        text = "npm ERR! code ERESOLVE\nnpm install failed with exit code 1"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "setup"

    def test_pip_install_fail(self) -> None:
        text = "pip install -r requirements.txt failed: No matching distribution found"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "setup"

    def test_import_error(self) -> None:
        text = "ModuleNotFoundError: No module named 'flask'"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "setup"

    def test_docker_build_fail(self) -> None:
        text = "Docker build failed (exit 1):\nStep 5/12 : RUN apt-get install"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "setup"

    def test_git_clone_fail(self) -> None:
        text = "fatal: repository 'https://github.com/org/repo' not found"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "setup"

    def test_repo_clone_multi(self) -> None:
        text = "git clone failed for repo kubernetes/kubernetes"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "setup"


# ---------------------------------------------------------------------------
# Timeout patterns
# ---------------------------------------------------------------------------

class TestTimeoutPatterns:
    """Timeout category."""

    def test_timeout_keyword(self) -> None:
        text = "Task exceeded timeout of 1800 seconds"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "timeout"

    def test_timed_out(self) -> None:
        text = "Agent timed out after 300s"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "timeout"

    def test_sigterm(self) -> None:
        text = "Process killed by SIGTERM"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "timeout"

    def test_deadline_exceeded(self) -> None:
        text = "deadline exceeded waiting for container"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "timeout"


# ---------------------------------------------------------------------------
# Verifier patterns
# ---------------------------------------------------------------------------

class TestVerifierPatterns:
    """Verifier category: checkpoint script errors."""

    def test_checkpoint_script_error(self) -> None:
        text = "checkpoint script exited with code 2: /workspace/.verifiers/error_chain.sh"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "verifier"

    def test_verifier_parse_error(self) -> None:
        text = "JSONDecodeError in verifier output: Expecting value"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "verifier"

    def test_test_runner_fail(self) -> None:
        text = "test.sh failed with exit code 1"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "verifier"

    def test_eb_verify_error(self) -> None:
        text = "eb_verify plugin raised ValueError: invalid artifact format"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "verifier"


# ---------------------------------------------------------------------------
# Agent patterns
# ---------------------------------------------------------------------------

class TestAgentPatterns:
    """Agent category: quality/hallucination issues."""

    def test_empty_output(self) -> None:
        text = "Agent produced no output file at /workspace/agent_output/answer.json"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "agent"

    def test_hallucinated_file(self) -> None:
        text = "Referenced file does not exist: /workspace/src/nonexistent.py"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "agent"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and ordering."""

    def test_none_returns_none(self) -> None:
        assert match_fingerprint(None) is None  # type: ignore[arg-type]

    def test_empty_string_returns_none(self) -> None:
        assert match_fingerprint("") is None

    def test_whitespace_returns_none(self) -> None:
        assert match_fingerprint("   \n\t  ") is None

    def test_unmatched_text_returns_none(self) -> None:
        text = "Everything completed successfully with no issues"
        assert match_fingerprint(text) is None

    def test_first_match_wins(self) -> None:
        """When text matches multiple patterns, the first in FINGERPRINTS wins."""
        # OOMKilled should match infra (OOM) not setup (docker)
        text = "Container OOMKilled during docker build"
        result = match_fingerprint(text)
        assert result is not None
        # OOM is more specific than generic docker, should match first
        assert "oom" in result.id.lower() or result.severity == "infra"

    def test_match_returns_fingerprint_type(self) -> None:
        text = "timeout exceeded"
        result = match_fingerprint(text)
        assert result is not None
        assert isinstance(result, Fingerprint)

    def test_dict_input(self) -> None:
        """match_fingerprint should handle dict exception_info like CSB."""
        data = {"type": "RuntimeError", "message": "Docker build failed (exit 1)"}
        result = match_fingerprint(data)
        assert result is not None
        assert result.severity == "setup"

    def test_case_insensitive(self) -> None:
        text = "OOMKILLED"
        result = match_fingerprint(text)
        assert result is not None
        assert result.severity == "infra"
