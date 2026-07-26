"""Unit tests for the sgx retrieval CLI (agents/harnesses/claude/mcp/sg_cli.py).

Verifies, with the HTTP layer fully mocked (never hits the network):
  - search arg parsing: positional terms joined, each -q/--query is an
    independent query, empty query raises
  - --flag value extraction (_pop_flag) removes the pair in place
  - cmd_read range logic: no range -> 1..120 + hint note; --start only ->
    start..start+119 + note; --end only -> 1..end; --rev adds revision
  - subcommand dispatch through main() to the right MCP tool name/arguments
  - missing-token exit code (2) and the token fallback (SRC_ACCESS_TOKEN)
  - unknown command -> exit 2; help / no args -> exit 0
  - exit-code mapping: tool isError -> 1, JSON-RPC error -> 1, HTTPError -> 3,
    URLError/transport -> 3
"""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
        / "agents"
        / "harnesses"
        / "claude"
        / "mcp"
    ),
)

import sg_cli  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Give every test a known token unless it overrides, and a stable URL."""
    monkeypatch.setenv("SOURCEGRAPH_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("SRC_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("SG_URL", "https://example.test/.api/mcp/v1")


def _mcp_response(text: str = "hit", is_error: bool = False) -> bytes:
    """A plain-JSON JSON-RPC tools/call result body."""
    import json

    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": text}],
                "isError": is_error,
            },
        }
    ).encode()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


class TestParseSearchArgs:
    def test_positional_terms_joined_into_one_query(self):
        assert sg_cli._parse_search_args(["foo", "bar", "baz"]) == ["foo bar baz"]

    def test_each_q_flag_is_independent_query(self):
        got = sg_cli._parse_search_args(["a", "-q", "b", "--query", "c"])
        assert got == ["a", "b", "c"]

    def test_only_q_flags_no_positional(self):
        assert sg_cli._parse_search_args(["-q", "one", "-q", "two"]) == ["one", "two"]

    def test_empty_argv_raises(self):
        with pytest.raises(ValueError):
            sg_cli._parse_search_args([])

    def test_q_without_value_raises(self):
        with pytest.raises(ValueError):
            sg_cli._parse_search_args(["term", "-q"])


class TestPopFlag:
    def test_pops_value_and_removes_pair(self):
        argv = ["a", "--start", "10", "b"]
        assert sg_cli._pop_flag(argv, "--start") == "10"
        assert argv == ["a", "b"]

    def test_returns_empty_when_absent(self):
        argv = ["a", "b"]
        assert sg_cli._pop_flag(argv, "--start") == ""
        assert argv == ["a", "b"]

    def test_aliases(self):
        argv = ["a", "--revision", "deadbeef"]
        assert sg_cli._pop_flag(argv, "--rev", "--revision") == "deadbeef"

    def test_missing_value_raises(self):
        with pytest.raises(ValueError):
            sg_cli._pop_flag(["a", "--start"], "--start")


# ---------------------------------------------------------------------------
# cmd_read range logic (mock call_tool to capture the arguments)
# ---------------------------------------------------------------------------


class TestCmdReadRange:
    def _capture(self, argv):
        seen = {}

        def fake_call_tool(name, arguments):
            seen["name"] = name
            seen["args"] = arguments
            return "file body", False

        with patch.object(sg_cli, "call_tool", side_effect=fake_call_tool):
            rc = sg_cli.cmd_read(argv)
        return rc, seen

    def test_no_range_defaults_to_preview(self):
        rc, seen = self._capture(["repo", "path.py"])
        assert rc == 0
        assert seen["name"] == "sg_read_file"
        assert seen["args"]["startLine"] == 1
        assert seen["args"]["endLine"] == sg_cli._DEFAULT_READ_LINES

    def test_start_only_reads_window_from_start(self):
        _, seen = self._capture(["repo", "path.py", "--start", "100"])
        assert seen["args"]["startLine"] == 100
        assert seen["args"]["endLine"] == 100 + sg_cli._DEFAULT_READ_LINES - 1

    def test_end_only_reads_from_top(self):
        _, seen = self._capture(["repo", "path.py", "--end", "40"])
        assert seen["args"]["startLine"] == 1
        assert seen["args"]["endLine"] == 40

    def test_rev_passthrough(self):
        _, seen = self._capture(["repo", "path.py", "--rev", "v1.2.3"])
        assert seen["args"]["revision"] == "v1.2.3"

    def test_wrong_arity_raises(self):
        with pytest.raises(ValueError):
            sg_cli.cmd_read(["only-repo"])


# ---------------------------------------------------------------------------
# Subcommand dispatch through main() (mock the HTTP layer, not the network)
# ---------------------------------------------------------------------------


class TestDispatch:
    def _run(self, argv, body=None):
        body = body if body is not None else _mcp_response()
        with patch.object(sg_cli, "_http_post", return_value=body) as post:
            rc = sg_cli.main(argv)
        return rc, post

    def test_search_calls_keyword_tool(self, capsys):
        seen = {}

        def fake_http(url, data, headers):
            import json

            seen["payload"] = json.loads(data)
            return _mcp_response("results")

        with patch.object(sg_cli, "_http_post", side_effect=fake_http):
            rc = sg_cli.main(["search", "needle", "repo:^x$"])
        assert rc == 0
        assert seen["payload"]["params"]["name"] == "sg_keyword_search"
        assert seen["payload"]["params"]["arguments"]["query"] == "needle repo:^x$"

    def test_batched_search_fans_out_and_propagates_any_error(self, capsys):
        results = iter([("first", False), ("second", True)])
        with patch.object(
            sg_cli, "call_tool", side_effect=lambda *_args: next(results)
        ):
            rc = sg_cli.cmd_search(["one", "-q", "two"])

        output = capsys.readouterr().out
        assert rc == 1
        assert "## Query 1: one" in output
        assert "## Query 2: two" in output

    def test_nls_joins_args(self):
        seen = {}

        def fake_http(url, data, headers):
            import json

            seen["payload"] = json.loads(data)
            return _mcp_response()

        with patch.object(sg_cli, "_http_post", side_effect=fake_http):
            rc = sg_cli.main(["nls", "how", "does", "auth", "work"])
        assert rc == 0
        assert seen["payload"]["params"]["name"] == "sg_nls_search"
        assert seen["payload"]["params"]["arguments"]["query"] == "how does auth work"

    def test_finder_calls_unprefixed_all_endpoint_tool(self):
        seen = {}

        def fake_http(url, data, headers):
            import json

            seen["payload"] = json.loads(data)
            return _mcp_response()

        with patch.object(sg_cli, "_http_post", side_effect=fake_http):
            rc = sg_cli.main(["finder", "inspect", "github.com/org/repo"])
        assert rc == 0
        assert seen["payload"]["params"] == {
            "name": "code_finder",
            "arguments": {"task": "inspect github.com/org/repo"},
        }

    def test_def_maps_to_go_to_definition(self):
        seen = {}

        def fake_http(url, data, headers):
            import json

            seen["payload"] = json.loads(data)
            return _mcp_response()

        with patch.object(sg_cli, "_http_post", side_effect=fake_http):
            rc = sg_cli.main(["def", "repo", "src/x.go", "Parse"])
        assert rc == 0
        params = seen["payload"]["params"]
        assert params["name"] == "sg_go_to_definition"
        assert params["arguments"] == {
            "repo": "repo",
            "path": "src/x.go",
            "symbol": "Parse",
        }

    def test_refs_maps_to_find_references(self):
        seen = {}

        def fake_http(url, data, headers):
            import json

            seen["payload"] = json.loads(data)
            return _mcp_response()

        with patch.object(sg_cli, "_http_post", side_effect=fake_http):
            rc = sg_cli.main(["refs", "repo", "src/x.go", "Parse"])
        assert rc == 0
        assert seen["payload"]["params"]["name"] == "sg_find_references"

    def test_ls_defaults_dir_to_dot(self):
        seen = {}

        def fake_http(url, data, headers):
            import json

            seen["payload"] = json.loads(data)
            return _mcp_response()

        with patch.object(sg_cli, "_http_post", side_effect=fake_http):
            rc = sg_cli.main(["ls", "repo"])
        assert rc == 0
        params = seen["payload"]["params"]
        assert params["name"] == "sg_list_files"
        assert params["arguments"]["path"] == "."


# ---------------------------------------------------------------------------
# Token handling and usage errors
# ---------------------------------------------------------------------------


class TestTokenAndUsage:
    def test_missing_token_exits_2(self, monkeypatch):
        monkeypatch.delenv("SOURCEGRAPH_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("SRC_ACCESS_TOKEN", raising=False)
        # Should never touch HTTP; fail before dispatch.
        with patch.object(sg_cli, "_http_post", side_effect=AssertionError("net")):
            assert sg_cli.main(["search", "x"]) == 2

    def test_src_access_token_fallback(self, monkeypatch):
        monkeypatch.delenv("SOURCEGRAPH_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("SRC_ACCESS_TOKEN", "fallback-tok")
        seen = {}

        def fake_http(url, data, headers):
            seen["auth"] = headers.get("Authorization")
            return _mcp_response()

        with patch.object(sg_cli, "_http_post", side_effect=fake_http):
            assert sg_cli.main(["search", "x"]) == 0
        assert seen["auth"] == "token fallback-tok"

    def test_unknown_command_exits_2(self):
        assert sg_cli.main(["frobnicate"]) == 2

    def test_help_exits_0(self, capsys):
        assert sg_cli.main(["--help"]) == 0
        assert "usage: sgx" in capsys.readouterr().out

    def test_no_args_prints_usage_exits_0(self, capsys):
        assert sg_cli.main([]) == 0
        assert "usage: sgx" in capsys.readouterr().out

    def test_bad_flag_arity_exits_2(self):
        # read with a missing value for --start is a ValueError -> exit 2
        with patch.object(sg_cli, "_http_post", side_effect=AssertionError("net")):
            assert sg_cli.main(["read", "repo", "path", "--start"]) == 2

    def test_finder_requires_a_task_description(self):
        assert sg_cli.main(["finder"]) == 2


# ---------------------------------------------------------------------------
# Exit-code mapping for tool / transport errors
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_tool_iserror_exits_1(self):
        with patch.object(
            sg_cli, "_http_post", return_value=_mcp_response("boom", is_error=True)
        ):
            assert sg_cli.main(["search", "x"]) == 1

    def test_jsonrpc_error_exits_1(self):
        import json

        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "error": {"message": "nope"}}
        ).encode()
        with patch.object(sg_cli, "_http_post", return_value=body):
            assert sg_cli.main(["search", "x"]) == 1

    def test_http_error_exits_3(self):
        err = urllib.error.HTTPError(
            url="https://example.test", code=503, msg="err", hdrs=None, fp=None
        )
        with patch.object(sg_cli, "_http_post", side_effect=err):
            assert sg_cli.main(["search", "x"]) == 3

    def test_url_error_exits_3(self):
        err = urllib.error.URLError("connection refused")
        with patch.object(sg_cli, "_http_post", side_effect=err):
            assert sg_cli.main(["search", "x"]) == 3


# ---------------------------------------------------------------------------
# SSE body parsing
# ---------------------------------------------------------------------------


class TestSseParsing:
    def test_sse_framed_body(self):
        body = (
            b'event: message\ndata: {"result": {"content": [{"text": "sse-hit"}]}}\n\n'
        )
        payloads = list(sg_cli._iter_sse_json(body))
        assert payloads == [{"result": {"content": [{"text": "sse-hit"}]}}]

    def test_plain_json_body(self):
        payloads = list(sg_cli._iter_sse_json(b'{"result": {"content": []}}'))
        assert payloads == [{"result": {"content": []}}]
