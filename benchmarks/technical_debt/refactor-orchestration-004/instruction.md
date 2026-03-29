# Refactor Orchestration: Protobuf v1 to v2 Import Migration

## Context

The Go protobuf ecosystem has migrated from `github.com/golang/protobuf` to
`google.golang.org/protobuf`. This requires coordinated import path changes
across the gRPC stack: protobuf-go -> grpc-go -> etcd.

grpc-go performed this migration in PR #6919 (merged 2024-01-30).

## Task

Given these repositories at their pre-migration state, produce a topologically
sorted execution plan for the import path migration.

## Repos in Workspace

- `/workspace/protobuf-go/` — google.golang.org/protobuf v1.32.0 (upstream)
- `/workspace/grpc-go/` — grpc-go v1.62.0 (intermediary, pre-migration)
- `/workspace/etcd/` — etcd v3.5.12 (consumer)

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. A numbered list of repos in the order they should be updated
2. Dependency graph
3. Import path changes required at each step
4. Parallelization annotations
5. Risk assessment

## Reference

- grpc/grpc-go PR #6919: move from github.com/golang/protobuf to google.golang.org/protobuf
