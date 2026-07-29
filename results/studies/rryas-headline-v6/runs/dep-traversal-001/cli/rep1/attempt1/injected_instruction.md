# IMPORTANT: Source Code Access — `sgx` command

There are **NO MCP tools in this environment** — all remote code retrieval is via the `sgx` shell command (run it in Bash; do not search for MCP tools). Use only the mode-specific `sgx` workflow below for remote code retrieval via Sourcegraph.

## Repository Scoping

These repos are indexed on Sourcegraph under `sg-evals/` mirrors. **Use these exact mirror names to scope every `sgx` request:**

- **lodash**
  - sgx filter: `repo:^github.com/sg-evals/lodash--4.17.20$`
  - Upstream: `lodash/lodash@4.17.20`
- **webpack**
  - sgx filter: `repo:^github.com/sg-evals/webpack--v5.64.0$`
  - Upstream: `webpack/webpack@v5.64.0`
- **jest**
  - sgx filter: `repo:^github.com/sg-evals/jest--v29.0.0$`
  - Upstream: `jestjs/jest@v29.0.0`


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

# CVE Blast Radius Analysis: lodash Command Injection

## Context

Our security team flagged CVE-2021-23337, a command injection vulnerability in the `lodash` npm package affecting the `_.template` function. We use lodash across our JavaScript build toolchain — it's a dependency of both webpack and jest.

I need you to determine the full blast radius. Don't just check direct dependencies — trace through the transitive graph to find every package that could be pulling in a vulnerable version.

## What I Need

1. **CVE Identification**: Confirm the CVE ID, affected package, and vulnerable version range.

2. **Direct Dependents**: Which repos in the workspace directly depend on lodash? Show me the manifest files (package.json) where the dependency is declared.

3. **Transitive Paths**: Trace the full dependency chain. For example, if `jest-haste-map` depends on lodash, and `jest` depends on `jest-haste-map`, that's a 2-hop transitive path. Map all such paths.

4. **Version Analysis**: For each consumer, check whether their resolved lodash version falls within the vulnerable range (< 4.17.21). Some may have already upgraded.

## Output

Write your findings to `/workspace/BLAST_RADIUS.md` with clear sections for each of the above.


---

## Output Requirements

The grader reads only `/workspace/BLAST_RADIUS.md`. This exact path supersedes any other output path mentioned earlier.

Create its parent directory first: `mkdir -p /workspace`
Write the complete report as Markdown, following the task's requested structure.

Do not create secondary or legacy deliverables. After validating the graded artifact, stop immediately instead of starting another reasoning step.

All cited source-file paths MUST be absolute and anchored at `/workspace/<repo>/...` (the repo roots are the directories under `/workspace`). Repo-relative source paths will not match the oracle and score 0.

Your answer is evaluated against a closed-world oracle — completeness matters.
