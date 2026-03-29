# P5.3 Score Distribution Analysis

## Overview

Analysis of score distributions across all 8 task types from sample runs, covering Phase 1 (provenance, support_mapping, monorepo_boundary), Phase 2 (dep_traversal, schema_evolution, api_contract), and Phase 3 (refactor_orchestration, dead_code). Total: 9 baseline runs + 9 MCP runs = 18 scored runs.

## Overall Distribution

| Metric | All Runs (N=18) | Baseline (N=9) | MCP (N=9) |
|--------|----------------|----------------|-----------|
| Mean | 0.802 | 0.608 | 0.996 |
| Median | 0.892 | 0.593 | 1.000 |
| Std Dev | **0.224** | 0.146 | 0.013 |
| Min | 0.410 | 0.410 | 0.960 |
| Max | 1.000 | 0.825 | 1.000 |

**Overall std dev = 0.224 (>0.15 threshold: PASS)**

## Per-Task-Type Scores

| Task Type | Phase | Baseline Scores | Baseline Mean | MCP Scores | MCP Mean | Gap |
|-----------|-------|----------------|---------------|------------|----------|-----|
| provenance | P1 | 0.500, 0.593 | 0.546 | 1.000, 1.000 | 1.000 | 0.454 |
| support_mapping | P1 | 0.500 | 0.500 | 1.000 | 1.000 | 0.500 |
| monorepo_boundary | P1 | 0.720 | 0.720 | 1.000 | 1.000 | 0.280 |
| dep_traversal | P2 | 0.825 | 0.825 | 1.000 | 1.000 | 0.175 |
| schema_evolution | P2 | 0.500 | 0.500 | 1.000 | 1.000 | 0.500 |
| api_contract | P2 | 0.800 | 0.800 | 1.000 | 1.000 | 0.200 |
| refactor_orchestration | P3 | 0.620 | 0.620 | 1.000 | 1.000 | 0.380 |
| dead_code | P3 | 0.410 | 0.410 | 0.960 | 0.960 | 0.550 |

## Baseline Score Distribution

```
dead_code            |####                  | 0.41
support_mapping      |#####                 | 0.50
schema_evolution     |#####                 | 0.50
provenance (01)      |#####                 | 0.50
provenance (06)      |######                | 0.59
refactor_orch        |######                | 0.62
monorepo_boundary    |#######               | 0.72
api_contract         |########              | 0.80
dep_traversal        |########              | 0.83
                     0.0          0.5          1.0
```

Baseline scores span 0.41 to 0.83 -- good spread across difficulty levels.

## MCP Score Distribution

```
dead_code            |####################  | 0.96
all others (8 runs)  |#####################| 1.00
                     0.0          0.5          1.0
```

MCP scores are near-ceiling. Only dead_code scored below 1.0 (0.96).

## Baseline vs MCP Gap Analysis

| Gap Range | Task Types | Count |
|-----------|-----------|-------|
| >0.50 | dead_code (0.55) | 1 |
| 0.40-0.50 | provenance (0.45), support_mapping (0.50), schema_evolution (0.50) | 3 |
| 0.20-0.40 | monorepo_boundary (0.28), refactor_orchestration (0.38) | 2 |
| <0.20 | dep_traversal (0.18), api_contract (0.20) | 2 |

Mean gap across all task types: **0.38**

## Degenerate Distribution Check

| Condition | Status | Detail |
|-----------|--------|--------|
| All baseline scores identical | **NO** | Range: 0.41 - 0.83 |
| All MCP scores identical | **NEAR-DEGENERATE** | 8/9 runs score 1.00, 1 scores 0.96 |
| Any task type with zero variance | **YES** | 6 of 8 types have only 1 sample per mode |
| Overall std dev > 0.15 | **PASS** | 0.224 |

### MCP Ceiling Effect (FLAG)

MCP scores are clustered at 1.00 (8/9 runs). This is a ceiling effect -- the MCP-augmented agent with full Sourcegraph access achieves near-perfect scores on all sample tasks. This means:

1. **MCP mode does not discriminate between task difficulties.** A medium dep-traversal task and an expert schema-evolution task both score 1.00.
2. **The benchmark's discriminating power comes entirely from baseline mode.** Score variance is 0.021 in baseline (useful) vs 0.0002 in MCP (not useful).
3. **Remediation**: To break the MCP ceiling, either (a) add harder checkpoints that require synthesis beyond retrieval, (b) include tasks where ground truth is ambiguous, or (c) introduce a "hybrid" mode with limited MCP access that creates intermediate scores.

### Small Sample Warning

Most task types have only 1 sample per mode (except provenance with 2). The per-task-type statistics are point estimates, not distributions. Full benchmark runs (10+ tasks per type) are needed to compute meaningful per-type variance.

## Phase Comparison

| Phase | Task Types | Avg Baseline | Avg MCP | Avg Gap |
|-------|-----------|-------------|---------|---------|
| Phase 1 | provenance, support_mapping, monorepo_boundary | 0.563 | 1.000 | 0.437 |
| Phase 2 | dep_traversal, schema_evolution, api_contract | 0.708 | 1.000 | 0.292 |
| Phase 3 | refactor_orchestration, dead_code | 0.515 | 0.980 | 0.465 |

Phase 3 tasks show the strongest discrimination overall. Phase 2 baseline scores are highest, suggesting those verifier checkpoints may need tightening.

## Discrimination Ranking (by baseline-MCP gap)

1. **dead_code** (0.55) -- function-level reachability requires symbol navigation
2. **schema_evolution** (0.50) -- indirect reference tracing through architectural layers
3. **support_mapping** (0.50) -- deep call chain tracing in large C++ codebase
4. **provenance** (0.45) -- error chain tracing across multiple source files
5. **refactor_orchestration** (0.38) -- cross-repo dependency graph discovery
6. **monorepo_boundary** (0.28) -- cross-package boundary violation detection
7. **api_contract** (0.20) -- multi-repo import chain tracing (partially greppable)
8. **dep_traversal** (0.18) -- function-level usage (but manifest scanning is easy)

## Recommendations

1. **Increase sample size**: Run at least 5 tasks per type per mode to compute meaningful variance.
2. **Break MCP ceiling**: Add checkpoints requiring reasoning/synthesis beyond pure retrieval (e.g., "propose a fix" or "rank severity with justification").
3. **Tighten easy checkpoints**: dep_traversal and api_contract have high baseline scores due to easy early checkpoints (CVE ID, direct consumers). Reduce weights on grep-equivalent checkpoints.
4. **Add intermediate mode**: A "hybrid" mode with rate-limited MCP access would create a third score band between baseline (0.41-0.83) and MCP (0.96-1.00).
