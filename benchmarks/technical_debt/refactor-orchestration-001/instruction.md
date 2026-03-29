# Refactor Orchestration: etcd 3.6 Client Update Cascade

## Context

The etcd project has released v3.6 client libraries with significant dependency
reduction (365 -> 247 total packages). Kubernetes consumes etcd client libraries
for its API server storage backend.

## Task

Given these repositories at their pre-refactor state, produce a topologically
sorted execution plan for updating the etcd client library across the dependency
chain.

## Repos in Workspace

- `/workspace/etcd/` — etcd v3.6.0 (the upstream library)
- `/workspace/kubernetes/` — Kubernetes v1.32.0 (the consumer)

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. A numbered list of repos in the order they should be updated
2. Dependency graph (which repo depends on which)
3. Parallelization annotations (which steps can run concurrently)
4. Risk assessment per step

## Reference

- etcd-io/etcd 3.6 release notes
- kubernetes/kubernetes PR #128419: etcd 3.6 client update
