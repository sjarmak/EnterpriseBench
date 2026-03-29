# Refactor Orchestration: go-grpc-middleware v1 Removal Cascade

## Context

grpc-ecosystem/go-grpc-middleware v1 has been archived. The removal requires
a multi-step cascade:

1. etcd migrates logging to middleware v2 (PR #20420, merged 2025-08-07)
2. etcd removes v1 dependency entirely (PR #21295, merged 2026-02-12)
3. k8s drops go-grpc-prometheus which depended on middleware v1
   (PR #135538, merged 2025-12-18)

Complications:
- v1 and v2 have incompatible APIs
- go-grpc-prometheus is a separate archived dependency
- Some functionality must be reimplemented, not just version-bumped

## Task

Given these repos at their pre-removal state, produce a topologically sorted
execution plan.

## Repos in Workspace

- `/workspace/go-grpc-middleware/` — go-grpc-middleware v1.4.0 (archived)
- `/workspace/etcd/` — etcd v3.5.17 (still depends on v1)
- `/workspace/kubernetes/` — Kubernetes v1.33.0 (depends on go-grpc-prometheus)

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. Numbered list of changes in order
2. Dependency graph
3. Migration strategy per component
4. Parallelization annotations
5. Risk assessment

## Reference

- etcd-io/etcd PR #20420: Migrate grpc-logging to grpc-middleware v2
- etcd-io/etcd PR #21295: Remove go-grpc-middleware dependency
- kubernetes/kubernetes PR #135538: Drop go-grpc-prometheus
