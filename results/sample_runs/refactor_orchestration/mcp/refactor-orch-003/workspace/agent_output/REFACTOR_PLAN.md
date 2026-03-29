# Refactor Plan

## Dependency Graph
- etcd-io/etcd depends on grpc/grpc-go (via go.mod: google.golang.org/grpc)
- kubernetes/kubernetes depends on grpc/grpc-go (direct) and etcd-io/etcd (via go.etcd.io/etcd/client/v3)

## Ordering
1. grpc/grpc-go
2. etcd-io/etcd
3. kubernetes/kubernetes

## Parallelization
No parallelizable steps — strict linear dependency chain.

## Risk Assessment
- grpc/grpc-go: Breaking interface change in ServiceRegistrar (PR #8155). Mock
  server implementations that embed grpc.ServiceRegistrar will fail to compile.
  Risk: HIGH for downstream consumers.
- etcd-io/etcd: Must update go.mod to grpc v1.72.x and fix any mock gRPC servers
  in test files. The clientv3 package wraps grpc.NewClient, so the update also
  affects etcd's client library API surface. Risk: MEDIUM.
- kubernetes/kubernetes: Dual dependency — both direct grpc import and transitive
  via etcd client. Must update vendor tree, fix test mocks in
  pkg/probe/grpc/grpc_test.go (errorNotServeServerMock), and ensure etcd client
  compatibility. Risk: MEDIUM-HIGH.

## Evidence
- Sourcegraph dependency graph: grpc-go -> etcd (go.mod), etcd -> k8s (go.mod)
- Cross-repo references to grpc.ServiceRegistrar: found in etcd/client/v3 and
  k8s/pkg/probe/grpc
- Historical PR: kubernetes/kubernetes#131838 (merged 2025-05-20) confirms this
  exact cascade ordering
