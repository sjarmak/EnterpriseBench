# Monorepo Package Boundary — Sample Run Analysis

## Overview

Sample runs for 1 Monorepo Boundary task across 2 modes (baseline, MCP-augmented).
Task selected: monorepo-boundary-003 (Babel decorator metadata + TS tuple labels, hard difficulty).

## Results Summary

| Task | Mode | Affected Pkgs (0.25) | Impact Class (0.45) | Boundary Violations (0.30) | Total |
|------|------|---------------------|--------------------|-----------------------------|-------|
| monorepo-boundary-003 (hard) | baseline | 0.67 | 1.00 | 0.33 | **0.72** |
| monorepo-boundary-003 (hard) | MCP | 1.00 | 1.00 | 1.00 | **1.00** |

## Key Observations

1. **Meaningful discrimination**: Baseline scores 0.72, MCP scores 1.00 — a 0.28 gap. The baseline gap is smaller than Support Mapping (0.50) because the impact classification checkpoint (weight=0.45) is binary and the baseline got it right.

2. **Boundary violations is the hardest checkpoint**: Baseline only found 1/3 boundary violation locations (0.33) — it traced `applyDecs2305.js` but missed `transformer-2023-05.ts` and `typescript/index.ts`. MCP's cross-package search found all three.

3. **Impact classification is easy**: Both modes correctly identified "minor" — this is a keyword match that doesn't require deep code tracing. Consider whether this checkpoint's weight (0.45) is too high for its difficulty.

4. **Affected package identification**: Baseline found 2/3 packages (@babel/helpers, @babel/plugin-proposal-decorators) but missed @babel/parser. The TypeScript tuple change requires following a separate dependency chain that baseline grep couldn't trace.

## Tool Usage Comparison

| Metric | Baseline | MCP |
|--------|----------|-----|
| Total tokens | 26,100 | 19,500 |
| File reads | 68 | 41 |
| Grep/search calls | 31 | — |
| Sourcegraph searches | — | 9 |
| Symbol navigations | — | 14 |

MCP mode uses 25% fewer tokens and 40% fewer file reads. The Babel monorepo has ~450K LOC — Sourcegraph search is particularly effective for cross-package dependency tracing.

## Verifier Behavior Notes

- **check_affected_packages.sh**: Simple regex matching for package names in IMPACT_REPORT.md. Clean and reliable.
- **check_impact_classification.sh**: Binary check for "minor" keyword — too lenient. Both modes pass trivially.
- **check_boundary_violations.sh**: Checks for specific file identifiers (applyDecs2305, transformer-2023-05, typescript/index). Effective but rigid — wouldn't catch equivalent descriptions without exact file names.

## Calibration Notes

- Impact classification weight (0.45) may be too high for a simple keyword match — consider splitting into per-package classification
- Boundary violations (0.30) is the most discriminating checkpoint and may deserve higher weight
- Consider adding a "dependency chain" checkpoint that verifies the agent traced the actual import/require paths between packages
- The baseline score (0.72) is higher than Support Mapping baseline (0.50), suggesting monorepo tasks may need harder checkpoints to achieve good discrimination

## Cross-Task Type Comparison

| Task Type | Baseline | MCP | Gap | Primary Discriminator |
|-----------|----------|-----|-----|----------------------|
| Error Provenance (P1.5) | 0.50-0.59 | 1.00 | 0.41-0.50 | Error source files |
| Support Mapping | 0.50 | 1.00 | 0.50 | Code path identification |
| Monorepo Boundary | 0.72 | 1.00 | 0.28 | Boundary violation files |

Support Mapping shows the strongest discrimination, likely because the Envoy codebase is large enough that grep-based exploration misses deep call chains. Monorepo Boundary's weaker discrimination suggests the checkpoints need refinement.
