# IMPORTANT: Source Code Access — `sgx` command

There are **NO MCP tools in this environment** — all remote code retrieval is via the `sgx` shell command (run it in Bash; do not search for MCP tools). Use only the mode-specific `sgx` workflow below for remote code retrieval via Sourcegraph.

## Repository Scoping

These repos are indexed on Sourcegraph under `sg-evals/` mirrors. **Use these exact mirror names to scope every `sgx` request:**

- **kubernetes**
  - sgx filter: `repo:^github.com/sg-evals/kubernetes--v1.28.0$`
  - Upstream: `kubernetes/kubernetes@v1.28.0`
- **etcd**
  - sgx filter: `repo:^github.com/sg-evals/etcd--v3.5.9$`
  - Upstream: `etcd-io/etcd@v3.5.9`
- **grpc-go**
  - sgx filter: `repo:^github.com/sg-evals/grpc-go--v1.58.0$`
  - Upstream: `grpc/grpc-go@v1.58.0`


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

# CVE Blast Radius Analysis: HTTP/2 Rapid Reset in golang.org/x/net

## Context

CVE-2023-39325 is an HTTP/2 Rapid Reset denial-of-service vulnerability in golang.org/x/net. This is the Go-specific advisory for the industry-wide HTTP/2 Rapid Reset attack (CVE-2023-44487) that affected nearly every HTTP/2 implementation.

Our CNCF infrastructure is built on Go — Kubernetes, etcd, and gRPC are all potentially affected. I need a complete blast radius assessment before we can coordinate patching.

## What I Need

1. **CVE Identification**: Confirm the CVE, module, and version range.

2. **Direct Dependents**: Check go.mod in each workspace repo. All three likely depend on golang.org/x/net, but the dependency may be direct or transitive.

3. **Transitive Paths**: This is complex. grpc-go uses x/net's HTTP/2 transport. etcd uses grpc-go for its client/server communication. Kubernetes uses both x/net directly (API server) and grpc-go transitively. Map the full dependency DAG.

4. **Version Analysis**: Check go.sum files for the actual resolved x/net version. Determine if each repo pins a version before or after 0.17.0.

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
