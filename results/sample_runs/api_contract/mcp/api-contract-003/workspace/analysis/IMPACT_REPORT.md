# Impact Analysis: gRPC-Go Transport Package Internalization

## 1. Source Change Identification

The gRPC-Go team moved the entire `transport` package to `internal/transport`
(PR #2212, 27 files). Key types that moved:

- `transport.go` → `internal/transport/transport.go` — core interfaces
- `ClientTransport` — client-side transport abstraction
- `ServerTransport` — server-side transport abstraction
- `Stream` — bidirectional stream type used in all gRPC calls

Internal references in grpc-go updated:
- `clientconn.go` — updated import to internal/transport
- `server.go` — updated import to internal/transport
- `stream.go` — updated import to internal/transport

## 2. Direct Consumers

### etcd (v3.3.10)
- etcd imports `google.golang.org/grpc/transport` directly in its transport layer
- Files affected: proxy, gateway, and integration test code
- etcd wraps gRPC transport types for its own connection management

### kubernetes (v1.13.0)
- kubernetes vendors grpc-go in `vendor/google.golang.org/grpc/`
- The apiserver component communicates with etcd via gRPC
- The api-server's etcd client depends on the transport package transitively
- `clientconn.go` and `server.go` in the vendor directory still reference the old path

## 3. Three-Repo Dependency Chain

The impact propagates: **grpc-go → etcd → kubernetes**

1. grpc-go moves transport to internal (source of break)
2. etcd directly imports `grpc/transport` — compile error when upgrading grpc-go
3. kubernetes vendors both grpc-go and etcd — must update vendor directory

Propagation mechanism: Go **vendoring** (pre-modules era). kubernetes copies dependencies
into `vendor/`, so updating grpc-go requires updating the vendor tree, which cascades
through etcd's vendor references too. This is tracked in the `go.mod` once modules are adopted.

Affected kubernetes subsystems:
- **apiserver** — primary etcd client, uses gRPC for all storage operations
- **kubelet** — uses gRPC for CRI (container runtime interface)
- Components in **staging/** that import the gRPC transport package

## 4. Breakage Classification

This change causes a **compile error** — `package not found` for any code importing
`google.golang.org/grpc/transport`. The transport types are unexported/internal.

Scale of impact: etcd alone has hundreds of transitive importers. The kubernetes
vendor tree has a large number of references. A vendor update affecting this many
files is a massive undertaking requiring coordinated release across all 3 repos.
