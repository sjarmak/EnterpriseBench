# Dead Code Necropsy — Sample Run Analysis

## Overview

Sample runs for dead-code-001 (hard: React legacy event system dead code) across 2 modes (baseline, MCP-augmented).

## Results Summary

| Task | Mode | Dead Code (0.50) | Feature Flags (0.30) | Evidence (0.20) | Total |
|------|------|-----------------|---------------------|----------------|-------|
| dead-code-001 (hard) | baseline | 0.54 | 0.00 | 0.71 | **0.41** |
| dead-code-001 (hard) | MCP | 0.92 | 1.00 | 1.00 | **0.96** |

## Key Observations

1. **MCP advantage is substantial (0.41 vs 0.96)**: The score spread of 0.55 is the largest observed across all sample run categories, confirming that dead code detection is a strong MCP signal task.

2. **Baseline finds files, MCP finds functions**: The baseline agent successfully identified entirely dead files (the legacy-events/ directory) using grep — finding zero imports is straightforward. However, it failed to identify dead functions within live files (getPooled, destructor, addEventPoolingTo in SyntheticEvent.js). These functions exist in files that ARE imported, so grep alone cannot determine their individual reachability.

3. **Feature flag detection requires cross-file analysis**: The baseline agent completely missed the enableDeprecatedFlareAPI feature flag. Identifying a flag as "permanently off" requires: (a) finding the flag definition, (b) searching all config override files, (c) confirming no setter exists. Sourcegraph's symbol search made this trivial.

4. **Token efficiency**: MCP used 30% fewer tokens (28,800 vs 41,200) despite finding significantly more dead code. The baseline agent's extensive grep-based searching through the React codebase consumed tokens without yielding proportional results.

## Tool Usage Comparison

| Metric | Baseline | MCP |
|--------|----------|-----|
| Total tokens | 41,200 | 28,800 |
| File reads | 85 | 34 |
| Grep/search calls | 38 | — |
| Sourcegraph searches | — | 11 |
| Symbol navigations | — | 22 |

## Score Breakdown

### Dead Code Detection (weight 0.50)
- Baseline: Precision=1.00 (no false positives), Recall=0.54 (7/13 dead items)
- MCP: Precision=1.00, Recall=0.92 (12/13 dead items)
- Both modes had perfect precision — neither flagged live code as dead. The difference is entirely in recall.

### Feature Flags (weight 0.30)
- Baseline: 0.00 — did not identify any feature flags
- MCP: 1.00 — correctly identified enableDeprecatedFlareAPI as permanently off

### Evidence Quality (weight 0.20)
- Baseline: 0.71 — evidence provided for most items but lacked reachability analysis
- MCP: 1.00 — evidence included Sourcegraph reference counts ("0 call sites")

## Why MCP Matters Here

Dead code detection at function granularity requires answering "who calls this function?" across the entire codebase. Grep can find string matches but cannot determine reachability through:
- Dynamic dispatch (event plugin interface calls extractEvents via array iteration)
- Re-exports (index.js files that re-export submodules)
- Conditional imports (feature-flag-guarded require() calls)

Sourcegraph's "find references" resolves these through static analysis, providing definitive reference counts.
