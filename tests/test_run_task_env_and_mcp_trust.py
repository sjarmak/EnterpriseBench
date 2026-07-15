"""Unit coverage for two rryas fixes in run_task.py.

- ``_load_env_local`` (EnterpriseBench-rryas.2): .env.local must WIN over a stale
  value already in the ambient env, or a dead SOURCEGRAPH_ACCESS_TOKEN exported by
  a shell profile shadows the live one and every Sourcegraph arm 401s.
- ``_merge_mcp_trust`` (EnterpriseBench-rryas.4): the project-MCP trust flag must be
  added without clobbering other settings, so Claude Code >=2.1 stops leaving the
  harness-written server "Pending approval".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts" / "orchestration")
)

import run_task
from run_task import _load_env_local, _merge_mcp_trust, _trust_project_mcp_servers


class TestLoadEnvLocalPrecedence:
    """.env.local is authoritative — it overrides, never defers to, the ambient env."""

    def test_overrides_a_stale_sourcegraph_token_already_in_env(
        self, tmp_path: Path
    ) -> None:
        """The rryas.2 bug: a stale token in env must not shadow .env.local."""
        env = {"SOURCEGRAPH_ACCESS_TOKEN": "sgp_dead_token"}
        p = tmp_path / ".env.local"
        p.write_text('export SOURCEGRAPH_ACCESS_TOKEN="sgp_live_token"\n')

        _load_env_local(p, env)

        assert env["SOURCEGRAPH_ACCESS_TOKEN"] == "sgp_live_token"

    def test_does_not_override_an_unrelated_secret(self, tmp_path: Path) -> None:
        """Non-Sourcegraph keys keep setdefault semantics: importing this module must
        not clobber an ambient GITHUB_TOKEN/OPENAI_API_KEY that also lives in
        .env.local (the review's HIGH finding)."""
        env = {"GITHUB_TOKEN": "ambient-should-survive"}
        p = tmp_path / ".env.local"
        p.write_text(
            "GITHUB_TOKEN=ghp_from_file\n"
            'SOURCEGRAPH_ACCESS_TOKEN="sgp_live"\n'
        )

        _load_env_local(p, env)

        assert env["GITHUB_TOKEN"] == "ambient-should-survive"  # preserved
        assert env["SOURCEGRAPH_ACCESS_TOKEN"] == "sgp_live"  # overridden

    def test_overrides_sg_and_src_prefixed_endpoint_keys(self, tmp_path: Path) -> None:
        env = {"SG_URL": "stale", "SRC_ENDPOINT": "stale"}
        p = tmp_path / ".env.local"
        p.write_text("SG_URL=live\nSRC_ENDPOINT=live\n")

        _load_env_local(p, env)

        assert env["SG_URL"] == "live"
        assert env["SRC_ENDPOINT"] == "live"

    def test_sets_a_key_absent_from_env(self, tmp_path: Path) -> None:
        env: dict = {}
        (tmp_path / ".env.local").write_text("SOURCEGRAPH_URL=https://demo.example\n")

        _load_env_local(tmp_path / ".env.local", env)

        assert env["SOURCEGRAPH_URL"] == "https://demo.example"

    def test_parses_export_quotes_comments_and_blanks(self, tmp_path: Path) -> None:
        env: dict = {}
        (tmp_path / ".env.local").write_text(
            "# a comment\n"
            "\n"
            'export A="quoted"\n'
            "B='single'\n"
            "C=bare\n"
            "  # indented comment\n"
        )

        _load_env_local(tmp_path / ".env.local", env)

        assert env == {"A": "quoted", "B": "single", "C": "bare"}

    def test_missing_file_is_a_noop(self, tmp_path: Path) -> None:
        env = {"KEEP": "me"}
        _load_env_local(tmp_path / "does-not-exist", env)
        assert env == {"KEEP": "me"}

    def test_value_containing_equals_is_preserved(self, tmp_path: Path) -> None:
        """A token or URL query with '=' must keep everything after the first '='."""
        env: dict = {}
        (tmp_path / ".env.local").write_text("K=a=b=c\n")

        _load_env_local(tmp_path / ".env.local", env)

        assert env["K"] == "a=b=c"


class TestMergeMcpTrust:
    """The named server is trusted by merge — scoped, not blanket; settings survive."""

    def test_adds_named_server_to_empty_settings(self) -> None:
        assert _merge_mcp_trust({}, "sourcegraph") == {
            "enabledMcpjsonServers": ["sourcegraph"]
        }

    def test_is_scoped_not_blanket(self) -> None:
        """Must NOT set enableAllProjectMcpServers — that would auto-trust any
        .mcp.json an adversarial agent later writes (the security residual)."""
        merged = _merge_mcp_trust({}, "sourcegraph")
        assert "enableAllProjectMcpServers" not in merged

    def test_preserves_unrelated_keys(self) -> None:
        merged = _merge_mcp_trust({"theme": "dark", "model": "sonnet"}, "sourcegraph")
        assert merged["theme"] == "dark"
        assert merged["model"] == "sonnet"
        assert merged["enabledMcpjsonServers"] == ["sourcegraph"]

    def test_appends_to_and_dedups_an_existing_list(self) -> None:
        assert _merge_mcp_trust(
            {"enabledMcpjsonServers": ["other"]}, "sourcegraph"
        )["enabledMcpjsonServers"] == ["other", "sourcegraph"]
        assert _merge_mcp_trust(
            {"enabledMcpjsonServers": ["sourcegraph"]}, "sourcegraph"
        )["enabledMcpjsonServers"] == ["sourcegraph"]

    def test_does_not_mutate_the_input(self) -> None:
        original = {"enabledMcpjsonServers": ["other"]}
        _merge_mcp_trust(original, "sourcegraph")
        assert original == {"enabledMcpjsonServers": ["other"]}


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["docker"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestTrustProjectMcpServers:
    """The in-container settings write: merge on read, fail closed on docker errors."""

    def test_writes_fresh_trust_file_when_none_exists(self, tmp_path: Path) -> None:
        # cat -> file absent; mkdir/chown -> ok; capture what docker cp uploaded.
        uploaded: dict = {}

        def fake_exec(cid, argv, **kw):
            if argv[0] == "cat":
                return _completed(1, stderr="cat: ...: No such file or directory")
            return _completed(0)

        def fake_cp(src, dst):
            uploaded["content"] = Path(src).read_text()

        with patch.object(run_task, "_docker_exec", side_effect=fake_exec), patch.object(
            run_task, "_docker_cp", side_effect=fake_cp
        ):
            ok = _trust_project_mcp_servers("c1", "sourcegraph")

        assert ok is True
        assert json.loads(uploaded["content"]) == {
            "enabledMcpjsonServers": ["sourcegraph"]
        }

    def test_merges_into_existing_valid_settings(self) -> None:
        uploaded: dict = {}

        def fake_exec(cid, argv, **kw):
            if argv[0] == "cat":
                return _completed(0, stdout=json.dumps({"theme": "dark"}))
            return _completed(0)

        with patch.object(run_task, "_docker_exec", side_effect=fake_exec), patch.object(
            run_task, "_docker_cp", side_effect=lambda s, d: uploaded.update(
                content=Path(s).read_text()
            )
        ):
            assert _trust_project_mcp_servers("c1", "sourcegraph") is True

        merged = json.loads(uploaded["content"])
        assert merged["theme"] == "dark"
        assert merged["enabledMcpjsonServers"] == ["sourcegraph"]

    def test_malformed_existing_json_falls_back_to_trust_only(self) -> None:
        uploaded: dict = {}

        def fake_exec(cid, argv, **kw):
            if argv[0] == "cat":
                return _completed(0, stdout="{not json")
            return _completed(0)

        with patch.object(run_task, "_docker_exec", side_effect=fake_exec), patch.object(
            run_task, "_docker_cp", side_effect=lambda s, d: uploaded.update(
                content=Path(s).read_text()
            )
        ):
            assert _trust_project_mcp_servers("c1", "sourcegraph") is True

        assert json.loads(uploaded["content"]) == {
            "enabledMcpjsonServers": ["sourcegraph"]
        }

    def test_mkdir_failure_returns_false(self) -> None:
        def fake_exec(cid, argv, **kw):
            if argv[0] == "cat":
                return _completed(1, stderr="No such file")
            if argv[0] == "mkdir":
                return _completed(1, stderr="permission denied")
            return _completed(0)

        with patch.object(run_task, "_docker_exec", side_effect=fake_exec), patch.object(
            run_task, "_docker_cp", side_effect=AssertionError("must not cp on mkdir fail")
        ):
            assert _trust_project_mcp_servers("c1", "sourcegraph") is False

    def test_docker_cp_failure_returns_false(self) -> None:
        def fake_exec(cid, argv, **kw):
            return _completed(1, stderr="No such file") if argv[0] == "cat" else _completed(0)

        def raising_cp(src, dst):
            raise RuntimeError("docker cp failed")

        with patch.object(run_task, "_docker_exec", side_effect=fake_exec), patch.object(
            run_task, "_docker_cp", side_effect=raising_cp
        ):
            assert _trust_project_mcp_servers("c1", "sourcegraph") is False
