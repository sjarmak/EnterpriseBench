# CVE Blast Radius Analysis: HTTP/2 Rapid Reset in golang.org/x/net

## Context

CVE-2023-39325 is an HTTP/2 Rapid Reset denial-of-service vulnerability in golang.org/x/net. This is the Go-specific advisory for the industry-wide HTTP/2 Rapid Reset attack (CVE-2023-44487) that affected nearly every HTTP/2 implementation.

Our CNCF infrastructure is built on Go — Kubernetes, etcd, and gRPC are all potentially affected. I need a complete blast radius assessment before we can coordinate patching.

## What I Need

1. **CVE Identification**: Confirm the CVE, module, and version range.

2. **Direct Dependents**: Check go.mod in each workspace repo. All three likely depend on golang.org/x/net, but the dependency may be direct or transitive.

3. **Transitive Paths**: This is complex. grpc-go uses x/net's HTTP/2 transport. etcd uses grpc-go for its client/server communication. Kubernetes uses both x/net directly (API server) and grpc-go transitively. Map the full dependency DAG.

4. **Version Analysis**: Check go.sum files for the actual resolved x/net version. Determine if each repo pins a version before or after 0.17.0.

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
