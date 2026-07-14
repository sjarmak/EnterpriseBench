"""CLI-arm harness helpers for EnterpriseBench.

The `cli` arm exposes the same remote Sourcegraph reach as the MCP arms, but as
a plain Bash-composable executable (`sgx`) instead of registered MCP tools. No
`.mcp.json` is written for this arm — the lean, no-MCP tool prefix is the whole
experimental point.
"""
