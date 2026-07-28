# IMPORTANT: Source Code Access — `sgx` command

There are **NO MCP tools in this environment** — all remote code retrieval is via the `sgx` shell command (run it in Bash; do not search for MCP tools). Use only the mode-specific `sgx` workflow below for remote code retrieval via Sourcegraph.

## Repository Scoping

These repos are indexed on Sourcegraph under `sg-evals/` mirrors. **Use these exact mirror names to scope every `sgx` request:**

- **envoy**
  - sgx filter: `repo:^github.com/sg-evals/envoy--v1.28.0$`
  - Upstream: `envoyproxy/envoy@v1.28.0`
- **istio**
  - sgx filter: `repo:^github.com/sg-evals/istio--1.20.0$`
  - Upstream: `istio/istio@1.20.0`


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

        # api-contract-dual-envoy-istio-001

        **Suite:** dependency_management | **Type:** api_contract | **Difficulty:** expert
        **Repos:** envoy + istio

        ## Context

        Envoy's xDS (discovery service) API evolved from v2 to v3, changing
resource type names and proto message structures. Istio's control
plane (istiod) generates xDS configuration for Envoy sidecars.

Your task:
1. Find where Envoy defines xDS v3 API proto messages
2. Find where Istio generates xDS configuration for Envoy
3. Identify v2 → v3 API changes in cluster, listener, and route configs
4. Document the contract points between Istio's xDS generator and
   Envoy's xDS consumer

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
