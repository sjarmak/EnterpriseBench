# API Contract Boundary -- Sample Run Analysis

## Overview

Sample run for api-contract-003 (gRPC-Go transport internalization, expert difficulty, multi-repo 3-way chain) across 2 modes (baseline, MCP-augmented).

## Results Summary

| Task | Mode | Source ID (0.15) | Direct Consumers (0.35) | Transitive Impact (0.30) | Classification (0.20) | Total |
|------|------|-----------------|------------------------|-----------------------|----------------------|-------|
| api-contract-003 | baseline | 1.00 | 1.00 | 0.67 | 0.50 | **0.80** |
| api-contract-003 | MCP | 1.00 | 1.00 | 1.00 | 1.00 | **1.00** |

## Key Observations

1. **Moderate discrimination**: 0.20 gap between baseline (0.80) and MCP (1.00). The gap is narrower than schema evolution (0.50) because the gRPC transport package move is a well-known breaking change with clear import path signatures that grep can partially trace.

2. **Source identification and direct consumers are easy**: Both modes scored 1.0. The `internal/transport` path, `ClientTransport`/`ServerTransport` types, and `clientconn.go`/`server.go` references are straightforward to find via import-path grep.

3. **Transitive impact is the primary discriminator**: Baseline scored 0.67 (2/3) on the three-repo chain. It identified vendoring as the propagation mechanism and mentioned the apiserver, but failed to identify the full `grpc-go -> etcd -> kubernetes` chain explicitly or mention specific k8s subsystems like kubelet.

4. **Classification requires quantitative reasoning**: Baseline scored 0.50 on classification -- it identified the compile error aspect but failed to convey the scale of impact (hundreds of transitive importers, massive vendor update). MCP's broader codebase search revealed the actual scope.

## Tool Usage Comparison

| Metric | Baseline | MCP |
|--------|----------|-----|
| Total tokens | 41,200 | 28,500 |
| File reads | 112 | 54 |
| Grep/search calls | 56 | -- |
| Sourcegraph searches | -- | 14 |
| Symbol navigations | -- | 22 |

MCP uses 31% fewer tokens and 52% fewer file reads. The 3-repo setup (2.5M LOC) amplifies the benefit of semantic search -- baseline had to grep across all three repos' vendor directories, while MCP could directly query cross-repo import graphs.

## Verifier Behavior Notes

- **check_source_identification.sh**: Checks for internal/transport path, transport.go, and key type names. Clear and reliable.
- **check_direct_consumers.sh**: Checks for etcd+transport, k8s vendor, apiserver, and key grpc-go files. The 4-criterion threshold is appropriate.
- **check_transitive_impact.sh**: Checks for three-repo chain mention, vendoring mechanism, and specific k8s subsystems. The chain pattern matching is somewhat rigid but functional.
- **check_classification.sh**: Checks for compile error language and scale/magnitude indicators. The scale criterion may be too sensitive to specific word choices.

## Calibration Notes

- The baseline score (0.80) is high for an expert-difficulty task. The first two checkpoints (source + consumers, combined weight 0.50) are too easy for a task at this difficulty. Consider adding a checkpoint that requires identifying specific etcd files that import the transport package, or specific kubernetes staging/ packages that are affected.
- The three-repo chain is the core value proposition of this task type. The transitive_impact checkpoint should have higher weight (perhaps 0.40) and harder criteria.
- For API contract tasks, the discrimination mainly comes from depth of analysis (quantitative impact assessment) rather than breadth of discovery. This contrasts with schema evolution where breadth is the discriminator.

## Cross-Task Type Comparison (Batch 2)

| Task Type | Task | Difficulty | Baseline | MCP | Gap | Primary Discriminator |
|-----------|------|-----------|----------|-----|-----|----------------------|
| Dep Traversal | dep-traversal-003 | medium | 0.825 | 1.00 | 0.175 | Function-level usage analysis |
| Schema Evolution | schema-evolution-005 | expert | 0.50 | 1.00 | 0.50 | Indirect refs (serializers, guardian, frontend) |
| API Contract | api-contract-003 | expert | 0.80 | 1.00 | 0.20 | Transitive chain + impact scale |

Schema evolution shows the strongest discrimination, consistent with Phase 1 findings that single-repo breadth tasks (tracing a change through many architectural layers) benefit most from semantic code navigation. The dep-traversal gap is narrow because the medium-difficulty dual-repo task has simpler dependency chains. API contract is in between -- the multi-repo chain is hard to fully trace but the key file names are greppable.

## Phase 1 vs Phase 2 Comparison

| Phase | Task Types | Avg Baseline | Avg MCP | Avg Gap |
|-------|-----------|-------------|---------|---------|
| Phase 1 | Provenance, Support Mapping, Monorepo Boundary | 0.57 | 1.00 | 0.43 |
| Phase 2 | Dep Traversal, Schema Evolution, API Contract | 0.71 | 1.00 | 0.30 |

Phase 2 baseline scores are higher on average, suggesting the verifier checkpoints may need tightening for the new task types. However, this comparison is confounded by difficulty (Phase 2 sample includes a medium task).
