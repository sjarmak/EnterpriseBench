**IMPORTANT: The repositories exist in /workspace but you do not have permission to read them — every local read will fail with Permission denied. Do not try to work around this; it is enforced by the filesystem, not by instruction. You MUST use Sourcegraph MCP tools for all code access.**

## Sourcegraph Repository Scoping

These repos are indexed on Sourcegraph under `sg-evals/` mirrors. **Always scope your MCP searches to these repos:**

- **tokio** (local: `/workspace/tokio/`)
  - MCP filter: `repo:^github.com/sg-evals/tokio--tokio-1.0.0$`
  - Upstream: `tokio-rs/tokio@tokio-1.0.0`
- **hyper** (local: `/workspace/hyper/`)
  - MCP filter: `repo:^github.com/sg-evals/hyper--v0.14.0$`
  - Upstream: `hyperium/hyper@v0.14.0`
- **tonic** (local: `/workspace/tonic/`)
  - MCP filter: `repo:^github.com/sg-evals/tonic--v0.6.0$`
  - Upstream: `hyperium/tonic@v0.6.0`


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
