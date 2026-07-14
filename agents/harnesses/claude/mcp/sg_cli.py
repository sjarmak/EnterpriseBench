#!/usr/bin/env python3
"""sgx — Bash-composable Sourcegraph retrieval CLI.

Installed in task containers as ``/usr/local/bin/sgx``. The name is `sgx`,
not `sg`, because shadow-utils ships ``/usr/bin/sg`` (setgroups) in the
task images and it shadows the wrapper in PATH.

Wraps the Sourcegraph MCP endpoint's tools as plain-text subcommands so an
agent can compose remote retrieval with ordinary shell tools (pipes, head,
&&, Task subagents) instead of registered MCP tools. Stateless: every
invocation is one (or, for multi-query search, a few concurrent) JSON-RPC
``tools/call`` POSTs to ``$SG_URL``.

Stdlib-only by design — this file runs inside task containers where pip
installs are unavailable.

Environment:
    SG_URL                     MCP endpoint (default
                               https://demo.sourcegraph.com/.api/mcp/v1)
    SOURCEGRAPH_ACCESS_TOKEN   auth token (SRC_ACCESS_TOKEN also accepted)

Subcommands:
    search QUERY... [-q EXTRA_QUERY]...    keyword search; each -q adds an
                                           independent query, fanned out
                                           concurrently and merged with
                                           per-query headers
    nls QUERY...                           natural-language/semantic search
    read REPO PATH [--start N] [--end N]   ranged file read (defaults to the
                                           first 120 lines when no range is
                                           given)
    def REPO PATH SYMBOL                   go to definition
    refs REPO PATH SYMBOL                  find references
    ls REPO [DIR]                          list files in a directory

Exit codes: 0 ok, 1 tool error (isError / JSON-RPC error), 2 usage or
missing-token error, 3 transport failure.
"""

import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_SG_URL = "https://demo.sourcegraph.com/.api/mcp/v1"

# demo.sourcegraph.com's WAF 403s the default Python-urllib user agent.
_USER_AGENT = "sg-cli/1.0"
_TIMEOUT = 120
_MAX_RETRIES = 2
_RETRY_DELAY = 2  # seconds
_MAX_WORKERS = 6
_DEFAULT_READ_LINES = 120
_READ_NOTE = (
    "\n(showing lines {start}-{end} — use --start/--end to read a "
    "specific range)"
)

USAGE = """usage: sgx <command> [args]

commands:
  search QUERY... [-q EXTRA_QUERY]...   keyword search (Sourcegraph query
                                        syntax passes through: repo:, file:,
                                        count:, type:). Each -q adds another
                                        query, run concurrently.
  nls QUERY...                          natural-language/semantic search
  read REPO PATH [--start N] [--end N] [--rev REV]
                                        read a file (default: first 120 lines)
  def REPO PATH SYMBOL [--rev REV]      go to a symbol's definition
  refs REPO PATH SYMBOL [--rev REV]     find references to a symbol
  ls REPO [DIR] [--rev REV]             list files in a directory

examples:
  sgx search 'HyperLogLog repo:^github.com/sg-evals/bustub--f5b1b76$'
  sgx search 'repo:^github.com/org/repo$ parseConfig' -q 'repo:^github.com/org/repo$ loadConfig'
  sgx read github.com/org/repo src/main.c --start 100 --end 160
  sgx def github.com/org/repo src/main.c ParseArgs
"""


def _http_post(url: str, body: bytes, headers: dict) -> bytes:
    """POST and return the raw response body. Retries transient failures.

    Isolated so tests can monkeypatch the HTTP layer.
    """
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < _MAX_RETRIES:
                last_exc = e
                time.sleep(_RETRY_DELAY)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < _MAX_RETRIES:
                last_exc = e
                time.sleep(_RETRY_DELAY)
                continue
            raise
    raise last_exc  # pragma: no cover - loop always raises or returns


def _iter_sse_json(body: bytes):
    """Yield JSON payloads from a response body (SSE-framed or plain JSON)."""
    text = body.decode("utf-8", errors="replace")
    found_sse = False
    for line in text.splitlines():
        if line.startswith("data: "):
            found_sse = True
            try:
                yield json.loads(line[len("data: "):])
            except json.JSONDecodeError:
                continue
    if not found_sse:
        try:
            yield json.loads(text)
        except json.JSONDecodeError:
            return


def _endpoint() -> tuple:
    url = os.environ.get("SG_URL", "").strip() or DEFAULT_SG_URL
    token = (
        os.environ.get("SOURCEGRAPH_ACCESS_TOKEN")
        or os.environ.get("SRC_ACCESS_TOKEN")
        or ""
    )
    return url, token


def call_tool(name: str, arguments: dict) -> tuple:
    """Call one MCP tool. Returns (text, is_error).

    is_error covers both tool-level isError results and JSON-RPC errors;
    transport failures raise (handled by the caller as exit 3).
    """
    url, token = _endpoint()
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"token {token}",
        "User-Agent": _USER_AGENT,
    }
    raw = _http_post(url, body, headers)
    for payload in _iter_sse_json(raw):
        if "error" in payload:
            err = payload["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            return f"Error: {msg}", True
        if "result" in payload:
            result = payload["result"] or {}
            text = "".join(
                c.get("text", "")
                for c in result.get("content", [])
                if isinstance(c, dict)
            )
            return text, bool(result.get("isError"))
    return "Error: no JSON-RPC payload in response", True


# ---------------------------------------------------------------------------
# Argument parsing (manual: query terms and filters may start with '-')
# ---------------------------------------------------------------------------

def _parse_search_args(argv: list) -> list:
    """Return the list of queries: positional terms joined, plus each -q."""
    extra = []
    terms = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-q", "--query"):
            if i + 1 >= len(argv):
                raise ValueError(f"{arg} requires a value")
            extra.append(argv[i + 1])
            i += 2
        else:
            terms.append(arg)
            i += 1
    queries = []
    if terms:
        queries.append(" ".join(terms))
    queries.extend(extra)
    if not queries:
        raise ValueError("search requires at least one query")
    return queries


def _pop_flag(argv: list, *names: str) -> str:
    """Remove `--flag value` from argv (in place); return value or ''."""
    for name in names:
        if name in argv:
            idx = argv.index(name)
            if idx + 1 >= len(argv):
                raise ValueError(f"{name} requires a value")
            value = argv[idx + 1]
            del argv[idx:idx + 2]
            return value
    return ""


def _emit(text: str, is_error: bool) -> int:
    if is_error:
        print(text or "Error: tool call failed", file=sys.stderr)
        return 1
    print(text)
    return 0


def cmd_search(argv: list, tool: str = "sg_keyword_search") -> int:
    queries = _parse_search_args(argv)
    if len(queries) == 1:
        return _emit(*call_tool(tool, {"query": queries[0]}))

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(_MAX_WORKERS, len(queries))
    ) as pool:
        results = list(pool.map(
            lambda q: call_tool(tool, {"query": q}), queries
        ))

    any_error = False
    sections = []
    for i, (query, (text, is_error)) in enumerate(zip(queries, results), 1):
        if is_error:
            any_error = True
            text = f"Error: {text}" if not text.startswith("Error") else text
        sections.append(f"## Query {i}: {query}\n\n{text or '(no results)'}")
    print("\n\n".join(sections))
    return 1 if any_error else 0


def cmd_nls(argv: list) -> int:
    if not argv:
        raise ValueError("nls requires a query")
    return _emit(*call_tool("sg_nls_search", {"query": " ".join(argv)}))


def cmd_read(argv: list) -> int:
    argv = list(argv)
    start = _pop_flag(argv, "--start")
    end = _pop_flag(argv, "--end")
    rev = _pop_flag(argv, "--rev", "--revision")
    if len(argv) != 2:
        raise ValueError("read requires REPO and PATH")
    repo, path = argv

    note = ""
    args = {"repo": repo, "path": path}
    if not start and not end:
        # Payload hygiene by default: preview instead of the whole file.
        args["startLine"], args["endLine"] = 1, _DEFAULT_READ_LINES
        note = _READ_NOTE.format(start=1, end=_DEFAULT_READ_LINES)
    else:
        start_n = int(start) if start else 1
        end_n = int(end) if end else start_n + _DEFAULT_READ_LINES - 1
        args["startLine"], args["endLine"] = start_n, end_n
        if not end:
            note = _READ_NOTE.format(start=start_n, end=end_n)
    if rev:
        args["revision"] = rev

    text, is_error = call_tool("sg_read_file", args)
    if is_error:
        return _emit(text, True)
    if note:
        text = text.rstrip("\n") + note
    print(text)
    return 0


def _cmd_codenav(argv: list, tool: str) -> int:
    argv = list(argv)
    rev = _pop_flag(argv, "--rev", "--revision")
    if len(argv) != 3:
        raise ValueError(f"{tool} requires REPO, PATH, and SYMBOL")
    repo, path, symbol = argv
    args = {"repo": repo, "path": path, "symbol": symbol}
    if rev:
        args["revision"] = rev
    return _emit(*call_tool(tool, args))


def cmd_ls(argv: list) -> int:
    argv = list(argv)
    rev = _pop_flag(argv, "--rev", "--revision")
    if not argv or len(argv) > 2:
        raise ValueError("ls requires REPO and optionally DIR")
    # The server rejects an empty path; "." lists the repo root.
    args = {"repo": argv[0], "path": argv[1] if len(argv) == 2 else "."}
    if rev:
        args["revision"] = rev
    return _emit(*call_tool("sg_list_files", args))


COMMANDS = {
    "search": cmd_search,
    "nls": cmd_nls,
    "read": cmd_read,
    "def": lambda argv: _cmd_codenav(argv, "sg_go_to_definition"),
    "refs": lambda argv: _cmd_codenav(argv, "sg_find_references"),
    "ls": cmd_ls,
}


def main(argv: list = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    command, rest = argv[0], argv[1:]
    handler = COMMANDS.get(command)
    if handler is None:
        print(f"sgx: unknown command '{command}'\n\n{USAGE}", file=sys.stderr)
        return 2

    _, token = _endpoint()
    if not token:
        print(
            "sgx: SOURCEGRAPH_ACCESS_TOKEN is not set (SRC_ACCESS_TOKEN also "
            "accepted)",
            file=sys.stderr,
        )
        return 2

    try:
        return handler(rest)
    except ValueError as e:
        print(f"sgx {command}: {e}\n\n{USAGE}", file=sys.stderr)
        return 2
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = (e.read() or b"").decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001 - detail is best-effort
            pass
        print(f"sgx {command}: HTTP {e.code} from {_endpoint()[0]} {detail}",
              file=sys.stderr)
        return 3
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"sgx {command}: transport error: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
