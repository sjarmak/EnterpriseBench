# Impact Analysis: gRPC-Go Transport Package Internalization

## Context

The gRPC-Go maintainers are moving the `transport` package to `internal/transport` (PR #2212). Their rationale: "This is a breaking change, but the transport package was never intended for use outside of grpc."

The problem is that some of our downstream dependencies *do* import it directly. We need to understand the blast radius before upgrading, particularly the chain: grpc-go → etcd → kubernetes.

## What I Need

1. **Moved API surface**: What key types and functions moved from `google.golang.org/grpc/transport` to `internal/transport`? Focus on the exported types that external consumers could have been using.

2. **Direct etcd impact**: Find every file in the etcd codebase that imports or references `google.golang.org/grpc/transport` directly.

3. **Kubernetes transitive impact**: Kubernetes vendors both grpc-go and etcd. Trace which kubernetes components are transitively affected — apiserver, kubelet, or other subsystems.

4. **Dependency chain map**: Draw the three-repo dependency chain. How does the breakage propagate from grpc-go through etcd into kubernetes? How many files are affected at each level?

## Output

Write your findings to `/workspace/analysis/IMPACT_REPORT.md`. Include a dependency chain diagram, per-repo file counts, and specific kubernetes subsystems affected.
