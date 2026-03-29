# CVE Blast Radius Analysis: protobufjs Prototype Pollution

## Context

CVE-2022-25878 is a prototype pollution vulnerability in the `protobufjs` npm package. The affected versions are 6.10.0-6.10.2 and 6.11.0-6.11.2. This is the JavaScript protobuf implementation used by gRPC-JS.

Our Node.js services use gRPC for inter-service communication, and the Kubernetes JavaScript client uses gRPC to talk to the API server. I need to understand how deep this goes.

## What I Need

1. **CVE Identification**: CVE, package, affected version ranges (there are two affected ranges).

2. **Direct Dependents**: Which workspace repos depend on protobufjs?

3. **Transitive Paths**: Map the chain: protobufjs -> @grpc/grpc-js -> downstream consumers. The grpc-node repo is a monorepo — find the @grpc/grpc-js package manifest within it.

4. **Version Analysis**: Check lock files for resolved protobufjs versions.

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
