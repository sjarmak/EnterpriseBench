# Refactor Orchestration: grpc.Dial -> grpc.NewClient Migration

## Context

grpc-go deprecated `grpc.Dial` and `grpc.DialContext` in v1.64 (June 2024),
replacing them with `grpc.NewClient`. The new API is non-blocking by default,
changing connection semantics.

The cascade:
- grpc-go: deprecation and new API
- etcd: PR #21282 migrated to NewClient (merged 2026-02-26), preserving
  DialTimeout behavior via health endpoint checks
- kubernetes: consumes etcd client library

## Task

Given these repos, produce a topologically sorted execution plan for the
Dial -> NewClient migration.

## Repos in Workspace

- `/workspace/grpc-go/` — grpc-go v1.79.0 (upstream, has NewClient)
- `/workspace/etcd/` — etcd v3.5.17 (pre-migration, still uses Dial)
- `/workspace/kubernetes/` — Kubernetes v1.33.0 (consumer)

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. Numbered list of repos in migration order
2. Dependency graph
3. API migration details per repo
4. Behavioral differences (blocking vs non-blocking)
5. Parallelization annotations

## Reference

- grpc-go v1.64 deprecation notice
- etcd-io/etcd PR #21282: replace Dial APIs with NewClient
- kubernetes/kubernetes PR #128419: etcd 3.6 client update
