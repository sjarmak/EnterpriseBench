# Dependency Graph Traversal -- Sample Run Analysis

## Overview

Sample run for dep-traversal-003 (CVE-2022-32149 golang.org/x/text DoS, medium difficulty, dual-repo) across 2 modes (baseline, MCP-augmented).

## Results Summary

| Task | Mode | CVE ID (0.10) | Direct Deps (0.30) | Transitive Paths (0.35) | Version Analysis (0.25) | Total |
|------|------|---------------|--------------------|-----------------------|------------------------|-------|
| dep-traversal-003 | baseline | 1.00 | 1.00 | 0.50 | 1.00 | **0.825** |
| dep-traversal-003 | MCP | 1.00 | 1.00 | 1.00 | 1.00 | **1.00** |

## Key Observations

1. **Discrimination is narrow but meaningful**: The 0.175 gap comes entirely from the transitive_paths checkpoint (weight=0.35). Baseline identified the CVE, found both repos, and classified versions correctly -- but failed to perform function-level usage analysis (did not mention `ParseAcceptLanguage` as the vulnerable function or distinguish between repos that call it vs those that just import the module).

2. **CVE identification and go.mod scanning are easy**: Both modes scored 1.0 on the first two checkpoints. These are grep-equivalent tasks that don't require deep code understanding.

3. **Function-level tracing is the discriminator**: The transitive_paths checkpoint requires the agent to go beyond manifest scanning and trace actual code paths. Baseline grep found the dependency but couldn't determine whether the vulnerable function was called. MCP's symbol search found callers of `ParseAcceptLanguage` directly.

4. **Version analysis is straightforward**: Both modes correctly classified affected vs unaffected repos based on version numbers in go.mod. This checkpoint may need harder criteria (e.g., require the agent to identify the exact line in go.mod and the minimum safe version).

## Tool Usage Comparison

| Metric | Baseline | MCP |
|--------|----------|-----|
| Total tokens | 15,800 | 11,200 |
| File reads | 38 | 18 |
| Grep/search calls | 22 | -- |
| Sourcegraph searches | -- | 6 |
| Symbol navigations | -- | 9 |

MCP uses 29% fewer tokens. The dual-repo setup (280K LOC) is small enough that baseline grep is partially effective, but symbol search eliminates the need to scan source files for function call sites.

## Verifier Behavior Notes

- **check_cve_id.sh**: Simple regex for CVE number and version. Both modes pass trivially.
- **check_direct_deps.sh**: Regex for repo names (chi, hugo). Easy checkpoint.
- **check_transitive_paths.sh**: Checks for `ParseAcceptLanguage` mention AND usage distinction language. This is the key discriminator -- baseline mentioned the language package but not the specific function.
- **check_version_analysis.sh**: Checks for classification keywords. May be too lenient -- "affected" and "not affected" are easy to include.

## Calibration Notes

- The baseline score (0.825) is high for a medium-difficulty task. The three easy checkpoints (CVE, deps, version) account for 0.65 weight combined. Consider reducing their combined weight to make the function-level tracing checkpoint more decisive.
- For harder dep-traversal tasks (3+ repos, transitive chains), the gap should widen as baseline grep becomes less effective at tracing multi-hop dependency paths.
