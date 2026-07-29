# IMPORTANT: Source Code Access — `sgx` command

There are **NO MCP tools in this environment** — all remote code retrieval is via the `sgx` shell command (run it in Bash; do not search for MCP tools). Use only the mode-specific `sgx` workflow below for remote code retrieval via Sourcegraph.

## Repository Scoping

These repos are indexed on Sourcegraph under `sg-evals/` mirrors. **Use these exact mirror names to scope every `sgx` request:**

- **axios**
  - sgx filter: `repo:^github.com/sg-evals/axios--v0.21.1$`
  - Upstream: `axios/axios@v0.21.1`
- **grafana**
  - sgx filter: `repo:^github.com/sg-evals/grafana--v9.5.0$`
  - Upstream: `grafana/grafana@v9.5.0`
- **druid**
  - sgx filter: `repo:^github.com/sg-evals/druid--druid-26.0.0$`
  - Upstream: `apache/druid@druid-26.0.0`


## Direct CLI Arm

Do not use `sgx finder`. This arm measures direct Sourcegraph retrieval through the search, navigation, and file-reading commands below; the `code_finder` backend is measured separately.

You MUST make at least one repository-scoped `sgx` call before inspecting repository contents with local tools such as `ls`, `find`, `grep`, `rg`, or `cat`. A run with zero `sgx` calls is invalid and stops the study. Generic task hints that repositories are cloned under `/workspace` describe path and output locations; they do not permit skipping this required Sourcegraph retrieval. After that first `sgx` call, local repository tools are allowed and may be composed with further `sgx` calls.

## `sgx` usage (a normal command — composes with pipes, `head`, `&&`; works inside Task subagents)

- `sgx search 'QUERY'` — keyword search; Sourcegraph filters pass through (`repo:`, `file:`, `count:`, `type:`).
- **Prefer combining related queries in ONE call:** `sgx search 'q1' -q 'q2' -q 'q3'` runs them concurrently and returns per-query results.
  Example: `sgx search 'ParseConfig repo:^github.com/org/repo$' -q 'loadConfig repo:^github.com/org/repo$'`
- `sgx read REPO PATH --start N --end M` — read a line range (no range = first 120 lines only; always prefer targeted ranges).
- `sgx def REPO PATH SYMBOL` / `sgx refs REPO PATH SYMBOL` — jump to a symbol's definition / list its callers.
- `sgx nls 'natural language question'` — semantic search when you don't know exact terms.
- `sgx ls REPO [DIR]` — list files. Pipe long output: `sgx search '...' | head -40`.

## Workflow

1. **Search first** — one batched `sgx search` (scoped with `repo:`, several `-q` queries); judge from the returned line-numbered snippets.
2. **Read only the span you need** — `sgx read REPO PATH --start N --end M` around the hits.
3. **Navigate** — `sgx def` / `sgx refs` to trace symbols across repo boundaries.
4. **Then implement** — once you understand the pattern, stop searching and start writing.

---

# CVE Blast Radius Analysis: axios ReDoS

## Context

A ReDoS vulnerability (CVE-2021-3749) was found in the axios HTTP client library. Our frontend teams use axios extensively — it's embedded in Grafana plugins and the Druid web console.

I need to know the full blast radius across our frontend infrastructure before we can prioritize patching.

## What I Need

1. **CVE Identification**: Confirm the CVE, affected package, and version range.

2. **Direct Dependents**: Which workspace repos depend on axios? Show the manifest files.

3. **Transitive Paths**: Trace how axios gets pulled in. Grafana uses a plugin SDK that may vendor axios. Druid has a web-console subfolder with its own package.json.

4. **Version Analysis**: Check resolved versions — are we actually running a vulnerable version, or have we already patched?

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.


---

## Output Requirements

The grader reads only `/workspace/BLAST_RADIUS.md`. This exact path supersedes any other output path mentioned earlier.

Create its parent directory first: `mkdir -p /workspace`
Write the complete report as Markdown, following the task's requested structure.

Do not create secondary or legacy deliverables. After validating the graded artifact, stop immediately instead of starting another reasoning step.

All cited source-file paths MUST be absolute and anchored at `/workspace/<repo>/...` (the repo roots are the directories under `/workspace`). Repo-relative source paths will not match the oracle and score 0.

Your answer is evaluated against a closed-world oracle — completeness matters.
