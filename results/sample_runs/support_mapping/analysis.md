# Support Code Mapping — Sample Run Analysis

## Overview

Sample runs for 1 Support Mapping task across 2 modes (baseline, MCP-augmented).
Task selected: support-mapping-001 (Envoy connection pool overflow, hard difficulty).

## Results Summary

| Task | Mode | Code Paths (0.60) | Ownership (0.15) | Severity (0.15) | Related Issues (0.10) | Total |
|------|------|-------------------|------------------|-----------------|----------------------|-------|
| support-mapping-001 (hard) | baseline | 0.35 | 1.00 | 0.60 | 0.50 | **0.50** |
| support-mapping-001 (hard) | MCP | 1.00 | 1.00 | 1.00 | 1.00 | **1.00** |

## Key Observations

1. **Clear discrimination**: Baseline scores 0.50, MCP scores 1.00 — a 0.50 gap confirming verifiers differentiate answer quality.

2. **Code paths is the key differentiator**: The dominant checkpoint (weight=0.60) showed the largest gap: baseline found 2/4 required files and 0/3 sufficient files (0.35), while MCP found all 7 (1.0). This confirms the weighting rationale — code path identification is the core skill being measured.

3. **Severity assessment shows partial credit**: Baseline rated "medium" instead of "high" and received 0.60 partial credit (one level off). The distance-based scoring works as designed.

4. **Ownership scored high in both modes**: Even the baseline matched enough ownership keywords to score 1.0. This checkpoint may need tighter calibration — the keyword threshold (40%) may be too generous.

## Tool Usage Comparison

| Metric | Baseline | MCP |
|--------|----------|-----|
| Total tokens | 22,400 | 16,800 |
| File reads | 56 | 34 |
| Grep/search calls | 23 | — |
| Sourcegraph searches | — | 11 |
| Symbol navigations | — | 18 |

MCP mode uses 25% fewer tokens and 39% fewer file reads. Sourcegraph search + symbol navigation provides more targeted access to the large Envoy C++ codebase.

## Verifier Behavior Notes

- **check_code_paths.sh**: 70/30 split between required and sufficient files works well. Baseline found core files but missed deeper conn_pool and upstream map files.
- **check_ownership.sh**: Keyword matching may be too lenient — baseline scored 1.0 with generic "connection handling" terms. Consider requiring more specific keywords.
- **check_severity.sh**: Distance-based scoring (0.4 penalty per level) produces reasonable partial credit.
- **check_related_issues.sh**: Fuzzy path matching correctly identified conn_pool.h reference but missed circuit_breaking.rst in baseline.

## Calibration Notes

- Ownership checkpoint may need tighter keyword threshold (raise from 40% to 60%) to better discriminate
- Code paths dominance (0.60 weight) is appropriate — this is the primary skill being measured
- Consider adding a penalty for excessive false-positive file identifications in future iterations
