"""Tests for the cli-arm sgx auth preflight in run_task.py (EnterpriseBench-rryas.3).

``_install_sgx`` only probes that the ``sgx`` wrapper resolves in PATH — it is
token-free by design, so a dead/expired Sourcegraph token sails straight past it.
Left unchecked, that token 401s on every ``sgx`` call, yet the cli run scores off
the agent's local grep fallback and is recorded with ``sgx_used=true``: a
false-valid cli measurement, and asymmetric with ``mcp_only``, which already
fails loudly on the same token at ``_verify_mcp_endpoint``.

``_verify_sgx_endpoint`` closes the gap: it makes ONE authenticated ``sgx`` call
in the container and reports whether the token was accepted. The caller HARD-gates
on a False and routes the run to the infra-error re-run channel
(``failure_class == "infra_sgx_auth"``) instead of scoring a degraded run — the
cli-arm analog of the MCP preflight gate (EnterpriseBench-vl0k).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts" / "orchestration")
)

import run_task
from run_task import _verify_sgx_endpoint


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestAuthAccepted:
    """A token the server accepts (sgx exit 0) passes the preflight."""

    def test_exit_zero_returns_true(self) -> None:
        with patch.object(
            run_task.subprocess, "run", return_value=_proc(0, stdout="result...")
        ):
            assert _verify_sgx_endpoint("cid", "good-tok") is True

    def test_exit_zero_with_empty_results_still_passes(self) -> None:
        # "no results" is a valid authenticated answer, not a failure.
        with patch.object(run_task.subprocess, "run", return_value=_proc(0, stdout="")):
            assert _verify_sgx_endpoint("cid", "good-tok") is True

    def test_forwards_token_by_name_never_in_argv(self) -> None:
        """The token VALUE must not appear on the docker exec command line.

        Forwarding by name (``-e SOURCEGRAPH_ACCESS_TOKEN``) keeps the secret out
        of argv where a host ``ps`` could read it (EnterpriseBench-rryas.5).
        """
        run = MagicMock(return_value=_proc(0))
        with patch.object(run_task.subprocess, "run", run):
            _verify_sgx_endpoint("cid", "s3cr3t-value")
        argv = run.call_args.args[0]
        assert "-e" in argv
        assert "SOURCEGRAPH_ACCESS_TOKEN" in argv
        assert "s3cr3t-value" not in argv
        # Runs as the agent user against the real sgx binary.
        assert "agent" in argv
        assert "sgx" in argv


class TestAuthRejected:
    """A definitive credential rejection fails loudly and fast (no retry)."""

    def test_missing_token_fails_without_calling_docker(self) -> None:
        run = MagicMock()
        with patch.object(run_task.subprocess, "run", run):
            assert _verify_sgx_endpoint("cid", "") is False
        run.assert_not_called()

    def test_http_401_returns_false(self) -> None:
        rejected = _proc(3, stderr="sgx search: HTTP 401 Invalid access token")
        with patch.object(run_task.subprocess, "run", return_value=rejected):
            assert _verify_sgx_endpoint("cid", "dead-tok") is False

    def test_401_does_not_retry(self) -> None:
        """A bad token never heals — one call, then fail; the backoff ladder is
        reserved for transient transport failures."""
        run = MagicMock(return_value=_proc(1, stderr="Error: 401 Unauthorized"))
        sleep = MagicMock()
        with (
            patch.object(run_task.subprocess, "run", run),
            patch.object(run_task.time, "sleep", sleep),
        ):
            assert _verify_sgx_endpoint("cid", "dead-tok") is False
        assert run.call_count == 1
        sleep.assert_not_called()

    def test_invalid_access_token_marker_matches_case_insensitively(self) -> None:
        rejected = _proc(1, stderr="Error: Invalid Access Token")
        with patch.object(run_task.subprocess, "run", return_value=rejected):
            assert _verify_sgx_endpoint("cid", "dead-tok") is False


class TestTransientFailure:
    """A transport blip retries with backoff, then gives up if it never clears."""

    def test_transient_then_success_returns_true(self) -> None:
        outcomes = [
            _proc(3, stderr="sgx search: transport error: timed out"),
            _proc(0, stdout="result..."),
        ]
        run = MagicMock(side_effect=outcomes)
        with (
            patch.object(run_task.subprocess, "run", run),
            patch.object(run_task.time, "sleep", MagicMock()),
        ):
            assert _verify_sgx_endpoint("cid", "good-tok") is True
        assert run.call_count == 2

    def test_persistent_transport_failure_exhausts_retries_and_fails(self) -> None:
        run = MagicMock(
            return_value=_proc(3, stderr="sgx search: transport error: refused")
        )
        with (
            patch.object(run_task.subprocess, "run", run),
            patch.object(run_task.time, "sleep", MagicMock()),
        ):
            assert _verify_sgx_endpoint("cid", "good-tok") is False
        assert run.call_count == 5  # max_retries


class TestAuthFailMarkers:
    """Every rejection marker fails fast; a non-auth error still retries."""

    @pytest.mark.parametrize(
        "stderr",
        [
            "HTTP 401 Invalid access token",
            "HTTP 403 Forbidden",
            "Error: unauthorized",
            "authentication required",
        ],
    )
    def test_each_marker_fails_fast(self, stderr: str) -> None:
        run = MagicMock(return_value=_proc(1, stderr=stderr))
        with (
            patch.object(run_task.subprocess, "run", run),
            patch.object(run_task.time, "sleep", MagicMock()),
        ):
            assert _verify_sgx_endpoint("cid", "dead-tok") is False
        assert run.call_count == 1

    def test_non_auth_error_is_treated_as_transient_and_retries(self) -> None:
        # A 500 / malformed-query error carries no auth marker, so it must ride
        # the retry ladder rather than being mistaken for a dead token.
        run = MagicMock(return_value=_proc(3, stderr="sgx search: HTTP 500 server error"))
        with (
            patch.object(run_task.subprocess, "run", run),
            patch.object(run_task.time, "sleep", MagicMock()),
        ):
            assert _verify_sgx_endpoint("cid", "good-tok") is False
        assert run.call_count == 5
