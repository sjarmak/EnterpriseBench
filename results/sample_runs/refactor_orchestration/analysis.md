# Refactor Orchestration — Sample Run Analysis

## Overview

Sample runs for refactor-orch-003 (hard: grpc-go v1.72 bump cascade, 3 repos) across 2 modes (baseline, MCP-augmented).

## Results Summary

| Task | Mode | Repo Set (0.25) | Topo Order (0.45) | Parallelism (0.30) | Total |
|------|------|----------------|-------------------|-------------------|-------|
| refactor-orch-003 (hard) | baseline | 0.67 | 0.33 | 1.00 | **0.62** |
| refactor-orch-003 (hard) | MCP | 1.00 | 1.00 | 1.00 | **1.00** |

## Key Observations

1. **MCP advantage is clear on multi-repo tasks**: The baseline agent failed to discover etcd as an intermediary between grpc-go and Kubernetes. Without cross-repo dependency graph traversal, the agent proposed a 2-repo plan (grpc-go -> k8s) instead of the correct 3-repo cascade (grpc-go -> etcd -> k8s). MCP's Sourcegraph dependency graph immediately revealed the intermediary.

2. **Topological ordering is the discriminating checkpoint**: Both modes scored 1.0 on parallelism (no parallelism expected — easy to get right). The repo set checkpoint provided partial credit (0.67 vs 1.0). But topological ordering was the strongest differentiator (0.33 vs 1.0), because a missing intermediary repo fundamentally breaks the ordering.

3. **Token efficiency**: MCP mode used 33% fewer tokens (21,600 vs 32,400) and 74% fewer file reads (18 vs 68). The baseline agent performed extensive grep-based searching through go.mod files across all 3 repos but still missed the transitive dependency path through etcd's client library.

## Tool Usage Comparison

| Metric | Baseline | MCP |
|--------|----------|-----|
| Total tokens | 32,400 | 21,600 |
| File reads | 68 | 18 |
| Grep/search calls | 24 | — |
| Sourcegraph searches | — | 6 |
| Symbol navigations | — | 9 |

## Verifier Behavior Notes

- **check_repo_set.sh**: Correctly scored 0.67 when baseline found 2/3 repos. The grep-based approach correctly detected "grpc-go" and "kubernetes" mentions.
- **check_topo_order.sh**: The topological verifier correctly penalized the incomplete ordering. With 2/3 repos and only 1/3 constraints satisfied (k8s after grpc-go, but missing etcd constraints), score was 0.33.
- **check_parallelism.sh**: Both modes correctly identified no parallelizable steps in this linear chain.

## Why MCP Matters Here

The grpc-go -> etcd -> k8s cascade is invisible to text search. The dependency is encoded in etcd's go.mod as `google.golang.org/grpc v1.x.x` and in k8s's go.mod as `go.etcd.io/etcd/client/v3 v3.x.x`. A grep for "grpc" in k8s's go.mod finds the direct grpc dependency but does not reveal that etcd's client library is the actual intermediary that requires updating first. Sourcegraph's dependency graph resolves this transitively.
