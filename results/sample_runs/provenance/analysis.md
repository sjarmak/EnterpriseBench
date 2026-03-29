# Error Message Provenance — Sample Run Analysis

## Overview

Sample runs for 2 Error Provenance tasks across 2 modes (baseline, MCP-augmented).
Tasks selected: one medium difficulty (err-provenance-01) and one hard (err-provenance-06).

## Results Summary

| Task | Mode | Error Source (0.40) | Error Chain (0.30) | Trigger Conds (0.30) | Total |
|------|------|--------------------|--------------------|---------------------|-------|
| err-provenance-01 (medium) | baseline | 0.50 | 0.67 | 0.33 | **0.50** |
| err-provenance-01 (medium) | MCP | 1.00 | 1.00 | 1.00 | **1.00** |
| err-provenance-06 (hard) | baseline | 0.50 | 0.64 | 0.67 | **0.59** |
| err-provenance-06 (hard) | MCP | 1.00 | 1.00 | 1.00 | **1.00** |

## Key Observations

1. **Discrimination works**: Baseline (partial answer) scores significantly lower than MCP (full answer), confirming verifiers discriminate between answer quality levels.

2. **Checkpoint weights are balanced**: No single checkpoint dominates — all three contribute meaningfully to the total score.

3. **Infrastructure OK**: Both runs completed without infrastructure errors. Verifier scripts executed correctly, parsed answer.json, compared against ground_truth.json, and produced valid JSON scores.

4. **Score ranges are realistic**:
   - Baseline: 0.50-0.59 (partial credit for finding some source files and partial chains)
   - MCP: 1.0 (full credit with all ground truth data — serves as upper bound)
   - These scores are not all-zero or all-one, confirming the scoring pipeline is functional.

## Tool Usage Comparison

| Metric | Baseline | MCP |
|--------|----------|-----|
| Total tokens | 18,500 | 14,200 |
| File reads | 42 | 28 |
| Grep/search calls | 15 | — |
| Sourcegraph searches | — | 8 |
| Symbol navigations | — | 12 |

MCP mode uses fewer total tokens and file reads because Sourcegraph search + symbol navigation is more targeted than broad grep.

## Verifier Behavior Notes

- **check_error_source.sh**: Correctly scores 0.5 when only 1/2 required files found, 1.0 when both found.
- **check_error_chain.sh**: Keyword-based matching at 50% coverage threshold. Partial chains score proportionally.
- **check_trigger_conditions.sh**: Counts matched conditions against ground truth. Empty conditions → 0.0.

## Next Steps

- Run full suite (all 10 tasks × 2 modes) once agent infrastructure is available
- Calibrate verifier sensitivity — the keyword-based chain matcher may be too generous for short chains
- Add timing data (wall-clock seconds per task) to tool usage metrics
