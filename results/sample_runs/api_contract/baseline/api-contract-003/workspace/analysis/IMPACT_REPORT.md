# Impact Analysis: gRPC-Go Transport Package Internalization

## Breaking Change

The `transport` package was moved to `internal/transport` in grpc-go, making the
`transport.go` types unexported. Key types like `ClientTransport` and `ServerTransport`
are no longer accessible to external consumers.

## Direct Consumers

### etcd
- etcd imports `google.golang.org/grpc/transport` directly in several files
- The `clientconn.go` reference chain affects etcd's gRPC client setup

## Kubernetes Impact

- kubernetes vendors grpc-go and etcd
- The apiserver component uses gRPC for etcd communication
- This would result in a compile error: import path not found

## Classification

This is a breaking change that would cause import errors for any package that
directly imported the transport package.
