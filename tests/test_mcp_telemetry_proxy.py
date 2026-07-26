"""Provider-neutral MCP proxy and Code Finder telemetry contracts."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from agents.harnesses.mcp_telemetry_proxy import (
    TelemetryProxyServer,
    build_retrieval_telemetry,
    extract_response_meta,
    iter_jsonrpc_payloads,
    redact_sensitive,
    sanitize_request,
)

REPOSITORY = "github.com/sg-evals/flask--3.1.0"


def _request(call_id: int, tool: str, task: str | None = None) -> dict:
    arguments = {"task": task or f"Inspect {REPOSITORY} for the Flask failure"}
    return {
        "timestamp": "2026-07-25T12:00:00Z",
        "trace_version": 1,
        "direction": "request",
        "id": call_id,
        "method": "tools/call",
        "tool": tool,
        "arguments": arguments,
    }


def _response(call_id: int, *, with_meta: bool = True, is_error: bool = False) -> dict:
    telemetry = {
        "subAgentTurns": 4,
        "subAgentDurationMs": 1250,
        "subAgentToolCalls": 7,
        "subAgentTotalInputTokens": 1200,
        "subAgentCachedTokens": 300,
        "subAgentCacheCreationInputTokens": 0,
        "subAgentPromptTokens": 900,
        "subAgentCompletionTokens": 200,
        "subAgentTotalTokens": 1400,
        "subAgentContextUsagePercent": 12.5,
    }
    return {
        "timestamp": "2026-07-25T12:00:01Z",
        "trace_version": 1,
        "direction": "response",
        "id": call_id,
        "method": "tools/call",
        "tool": "code_finder",
        "status": 200,
        "is_error": is_error,
        "meta": {"sourcegraphToolTelemetry": telemetry} if with_meta else {},
    }


def _write_trace(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")


def _summary(path: Path, mode: str = "mcp_code_finder") -> dict:
    return build_retrieval_telemetry(
        path,
        mode=mode,
        expected_repo_count=1,
        expected_repositories=[REPOSITORY],
        outer_usage={
            "total_input_tokens": 100,
            "total_output_tokens": 25,
            "cost_usd": 0.2,
        },
    )


def test_iter_jsonrpc_payloads_accepts_json_and_sse() -> None:
    payload = {"jsonrpc": "2.0", "id": 7, "result": {"content": []}}
    encoded = json.dumps(payload).encode()

    assert list(iter_jsonrpc_payloads(encoded, "application/json")) == [payload]
    assert list(
        iter_jsonrpc_payloads(
            b"event: message\ndata: " + encoded + b"\n\n",
            "text/event-stream",
        )
    ) == [payload]


def test_nested_sensitive_values_are_redacted() -> None:
    assert redact_sensitive([{"token": "secret"}, "safe"]) == [
        {"token": "[REDACTED]"},
        "safe",
    ]
    captured = sanitize_request(
        {
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "code_finder",
                "arguments": {"task": "trace it", "Authorization": "token secret"},
            },
        }
    )
    assert "secret" not in json.dumps(captured)


def test_extract_response_meta_captures_beta_aggregate_without_content() -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": 7,
        "result": {
            "content": [{"type": "text", "text": "large answer"}],
            "_meta": {
                "sourcegraphToolTelemetry": {
                    "subAgentTurns": 2,
                    "subAgentTotalTokens": 44,
                }
            },
        },
    }

    captured = extract_response_meta(payload, tool="code_finder", status=200)

    assert captured["meta"] == payload["result"]["_meta"]
    assert "content" not in captured


def test_tool_inventory_fingerprints_code_finder_schema_order_independently() -> None:
    tools = [
        {"name": "read_file", "inputSchema": {"type": "object"}},
        {
            "name": "code_finder",
            "inputSchema": {
                "type": "object",
                "properties": {"task": {"type": "string"}},
                "required": ["task"],
            },
        },
    ]
    first = extract_response_meta(
        {"id": 2, "result": {"tools": tools}},
        method="tools/list",
        tool=None,
        status=200,
    )
    second = extract_response_meta(
        {"id": 2, "result": {"tools": list(reversed(tools))}},
        method="tools/list",
        tool=None,
        status=200,
    )

    assert first["provenance"]["tool_names"] == ["code_finder", "read_file"]
    assert len(first["provenance"]["code_finder_schema_sha256"]) == 64
    assert (
        first["provenance"]["tool_inventory_sha256"]
        == second["provenance"]["tool_inventory_sha256"]
    )


def test_forced_finder_validates_exact_scoped_call_and_inner_outer_usage(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "trace.jsonl"
    _write_trace(trace, [_request(1, "code_finder"), _response(1)])

    telemetry = _summary(trace)

    assert telemetry["valid"] is True
    assert telemetry["code_finder_calls"] == 1
    assert telemetry["direct_retrieval_calls"] == 0
    assert telemetry["repository_scope"]["finder_calls_by_repo"] == {REPOSITORY: 1}
    assert telemetry["inner"]["turns"] == 4
    assert telemetry["inner"]["tool_calls"] == 7
    assert telemetry["combined"]["total_tokens"] == 1525


@pytest.mark.parametrize(
    ("records", "reason"),
    [
        ([], "observed 0"),
        (
            [_request(1, "code_finder"), _response(1, with_meta=False)],
            "aggregate telemetry missing",
        ),
        (
            [
                _request(1, "code_finder"),
                _response(1),
                _request(2, "read_file"),
            ],
            "direct retrieval",
        ),
        (
            [_request(1, "code_finder", task="an unscoped task"), _response(1)],
            "repository scope",
        ),
        (
            [_request(1, "code_finder"), _response(1, is_error=True)],
            "failed response",
        ),
    ],
)
def test_forced_finder_fails_closed(
    tmp_path: Path,
    records: list[dict],
    reason: str,
) -> None:
    trace = tmp_path / "trace.jsonl"
    _write_trace(trace, records)

    telemetry = _summary(trace)

    assert telemetry["valid"] is False
    assert reason in telemetry["invalid_reason"]


def test_assisted_finder_allows_targeted_direct_follow_up(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    _write_trace(
        trace,
        [
            _request(1, "code_finder"),
            _response(1),
            _request(2, "read_file"),
        ],
    )

    telemetry = _summary(trace, mode="mcp_assisted")

    assert telemetry["valid"] is True
    assert telemetry["direct_retrieval_calls"] == 1


def test_cli_finder_has_the_same_forced_validity_contract(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    _write_trace(trace, [_request(1, "code_finder"), _response(1)])

    telemetry = _summary(trace, mode="cli_code_finder")

    assert telemetry["valid"] is True
    assert telemetry["code_finder_calls"] == 1
    assert telemetry["direct_retrieval_calls"] == 0


def test_proxy_forwards_authorization_but_never_persists_it(tmp_path: Path) -> None:
    observed: dict[str, str] = {}

    class UpstreamHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            observed["authorization"] = self.headers.get("Authorization", "")
            size = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(size))
            body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "result": {
                        "content": [],
                        "_meta": {
                            "sourcegraphToolTelemetry": {
                                "subAgentTurns": 1,
                                "subAgentTotalTokens": 2,
                            }
                        },
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    trace = tmp_path / "trace.jsonl"
    proxy = TelemetryProxyServer(
        ("127.0.0.1", 0),
        upstream_url=f"http://127.0.0.1:{upstream.server_port}/mcp",
        trace_path=trace,
    )
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()
    secret = "token sgp_super_secret_value"
    request = urllib.request.Request(
        f"http://127.0.0.1:{proxy.server_port}/mcp",
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "code_finder",
                    "arguments": {"task": f"Inspect {REPOSITORY}"},
                },
            }
        ).encode(),
        headers={"Authorization": secret, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
    finally:
        proxy.shutdown()
        proxy.server_close()
        upstream.shutdown()
        upstream.server_close()

    assert observed["authorization"] == secret
    assert "sgp_super_secret_value" not in trace.read_text()
    assert trace.stat().st_mode & 0o777 == 0o600
