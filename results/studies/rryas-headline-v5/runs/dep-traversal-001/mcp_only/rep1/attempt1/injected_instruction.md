**IMPORTANT: The repositories exist in /workspace but you do not have permission to read them — every local read will fail with Permission denied. Do not try to work around this; it is enforced by the filesystem, not by instruction. You MUST use Sourcegraph MCP tools for all code access.**

## Sourcegraph Repository Scoping

These repos are indexed on Sourcegraph under `sg-evals/` mirrors. **Always scope your MCP searches to these repos:**

- **lodash** (local: `/workspace/lodash/`)
  - MCP filter: `repo:^github.com/sg-evals/lodash--4.17.20$`
  - Upstream: `lodash/lodash@4.17.20`
- **webpack** (local: `/workspace/webpack/`)
  - MCP filter: `repo:^github.com/sg-evals/webpack--v5.64.0$`
  - Upstream: `webpack/webpack@v5.64.0`
- **jest** (local: `/workspace/jest/`)
  - MCP filter: `repo:^github.com/sg-evals/jest--v29.0.0$`
  - Upstream: `jestjs/jest@v29.0.0`


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
