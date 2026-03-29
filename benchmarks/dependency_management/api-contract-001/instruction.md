# Impact Analysis: gRPC-Go Metadata Context Separation

## Context

Hey — the gRPC-Go team just landed a significant change to how metadata is handled in contexts (grpc-go PR #1157). Previously, there was a single `metadata.FromContext` / `metadata.NewContext` pair for all metadata operations. Now they've split it into separate functions for incoming vs outgoing metadata:

- `metadata.FromContext` → `metadata.FromIncomingContext` / `metadata.FromOutgoingContext`
- `metadata.NewContext` → `metadata.NewOutgoingContext`

This is a breaking change for any consumer that uses the old API. We need to assess the impact on our etcd codebase before we can upgrade grpc-go.

## What I Need

1. **Source identification**: Show me exactly what changed in `grpc-go/metadata/metadata.go` — which functions were removed/renamed and what replaced them.

2. **Consumer file list**: Find every file in the etcd codebase that imports `google.golang.org/grpc/metadata` and uses the old API functions. I need the full list — don't miss any.

3. **Transitive impact**: Some of our code forwards metadata from incoming RPCs to outgoing RPCs (interceptors, auth proxies). These are the most dangerous because they silently stop working if metadata isn't explicitly copied between contexts. Flag these specifically.

4. **Breakage classification**: For each affected file, tell me if it's a compile error (function not found), a runtime behavior change (metadata silently dropped), or just a deprecation warning.

## Output

Write your findings to `/workspace/analysis/IMPACT_REPORT.md` with:
- The breaking API changes section
- A table of affected etcd files with breakage type
- A "Critical: metadata forwarding" section highlighting interceptors
