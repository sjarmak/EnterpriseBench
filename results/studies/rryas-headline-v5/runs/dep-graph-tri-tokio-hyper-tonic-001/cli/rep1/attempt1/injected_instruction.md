# IMPORTANT: Source Code Access — `sgx` command

There are **NO MCP tools in this environment** — all remote code retrieval is via the `sgx` shell command (run it in Bash; do not search for MCP tools). Use only the mode-specific `sgx` workflow below for remote code retrieval via Sourcegraph.

## Repository Scoping

These repos are indexed on Sourcegraph under `sg-evals/` mirrors. **Use these exact mirror names to scope every `sgx` request:**

- **tokio**
  - sgx filter: `repo:^github.com/sg-evals/tokio--tokio-1.0.0$`
  - Upstream: `tokio-rs/tokio@tokio-1.0.0`
- **hyper**
  - sgx filter: `repo:^github.com/sg-evals/hyper--v0.14.0$`
  - Upstream: `hyperium/hyper@v0.14.0`
- **tonic**
  - sgx filter: `repo:^github.com/sg-evals/tonic--v0.6.0$`
  - Upstream: `hyperium/tonic@v0.6.0`


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

        # dep-graph-tri-tokio-hyper-tonic-001

        **Suite:** dependency_management | **Type:** dependency_graph | **Difficulty:** expert
        **Repos:** tokio + hyper + tonic

        ## Context

        The Rust gRPC stack uses tonic (gRPC) → hyper (HTTP/2) → tokio (async
runtime). A tokio version bump can cascade through hyper into tonic.

Your task:
1. Map the full dependency chain: tonic → hyper → tokio with exact
   version constraints from each Cargo.toml
2. Identify which tokio APIs hyper uses that tonic depends on transitively
3. Find any version pinning conflicts across the three repos
4. Document the upgrade coordination strategy

Write your analysis to /workspace/analysis/IMPACT_REPORT.md

        ## Expected Output

        Write your analysis to `/workspace/analysis/IMPACT_REPORT.md`.

        Your report should include:
        - File paths from each repository that are relevant
        - Specific code symbols, functions, or types involved
        - The nature of each change (removal, rename, signature change, behavioral)
        - Migration recommendations

        ## Hints

        - All repos are cloned under `/workspace/`
        - Focus on import/dependency declarations first, then trace into implementation
        - Check version constraints in dependency manifests (Cargo.toml, go.mod, pom.xml, requirements.txt)


---

## Output Requirements

The grader reads only `/workspace/analysis/IMPACT_REPORT.md`. This exact path supersedes any other output path mentioned earlier.

Create its parent directory first: `mkdir -p /workspace/analysis`
Write the complete report as Markdown, following the task's requested structure.

Do not create secondary or legacy deliverables. After validating the graded artifact, stop immediately instead of starting another reasoning step.

All cited source-file paths MUST be absolute and anchored at `/workspace/<repo>/...` (the repo roots are the directories under `/workspace`). Repo-relative source paths will not match the oracle and score 0.

Your answer is evaluated against a closed-world oracle — completeness matters.
