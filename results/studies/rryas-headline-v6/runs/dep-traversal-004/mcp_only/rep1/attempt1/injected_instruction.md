**IMPORTANT: The repositories exist in /workspace but you do not have permission to read them — every local read will fail with Permission denied. Do not try to work around this; it is enforced by the filesystem, not by instruction. You MUST use Sourcegraph MCP tools for all code access.**

## Sourcegraph Repository Scoping

These repos are indexed on Sourcegraph under `sg-evals/` mirrors. **Always scope your MCP searches to these repos:**

- **kubernetes** (local: `/workspace/kubernetes/`)
  - MCP filter: `repo:^github.com/sg-evals/kubernetes--v1.28.0$`
  - Upstream: `kubernetes/kubernetes@v1.28.0`
- **etcd** (local: `/workspace/etcd/`)
  - MCP filter: `repo:^github.com/sg-evals/etcd--v3.5.9$`
  - Upstream: `etcd-io/etcd@v3.5.9`
- **grpc-go** (local: `/workspace/grpc-go/`)
  - MCP filter: `repo:^github.com/sg-evals/grpc-go--v1.58.0$`
  - Upstream: `grpc/grpc-go@v1.58.0`


## Direct MCP Arm

Do not call `code_finder`. This arm measures direct Sourcegraph retrieval with the search, navigation, and file-reading tools below; Code Finder is measured separately.

## Tool Selection

**Decision logic:**
1. Know the exact symbol? -> `keyword_search`
2. Know the concept, not the name? -> `nls_search`
3. Need definition of a symbol? -> `go_to_definition`
4. Need all callers/references? -> `find_references`
5. Need full file content? -> `read_file`
6. Need deep cross-repo analysis? -> `deepsearch` (then `deepsearch_read` after 60s)

## Scoping (Always Do This)

```
repo:^github.com/ORG/REPO$           # Exact repo (preferred)
repo:github.com/ORG/                 # All repos in org
file:.*\.ts$                         # TypeScript only
file:src/api/                        # Specific directory
```

Start narrow. Expand only if results are empty.

## Efficiency Rules

- Chain searches logically: search -> read -> references -> definition
- Don't re-search for the same pattern; use results from prior calls
- Prefer `keyword_search` over `nls_search` when you have exact terms
- Read 2-3 related files before synthesising, rather than one at a time
- Don't read 20+ remote files without writing code — once you understand the pattern, start implementing
- Use `deepsearch` only for complex cross-repo questions that simpler tools can't answer
- After calling `deepsearch`, wait at least 60 seconds before calling `deepsearch_read`
- Batch related searches together rather than making one-at-a-time calls

## If Stuck

If MCP search returns no results:
1. Broaden the search query (synonyms, partial identifiers)
2. Try `nls_search` for semantic matching
3. Use `list_files` to browse the directory structure
4. Use `list_repos` to verify the repository name
5. Try `deepsearch` for AI-powered deep analysis of the question
6. Check if the symbol exists under a different module or package name

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
