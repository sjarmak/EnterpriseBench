# CVE Blast Radius Analysis: Protobuf JSON Unmarshal Infinite Loop

## Context

CVE-2024-24786 is a denial-of-service in google.golang.org/protobuf. When unmarshaling JSON input that contains `google.protobuf.Any` types, the decoder can enter an infinite loop. This is particularly dangerous because protobuf is the serialization layer for our entire service mesh.

Our Istio mesh, gRPC infrastructure, and Envoy control plane all depend on protobuf. I need to know which services are actually exposed — not just which import the module.

## What I Need

1. **CVE Identification**: CVE, module, version range.

2. **Direct Dependents**: Check go.mod in each workspace repo.

3. **Transitive Paths**: Map the full dependency DAG. grpc-go uses protobuf for message marshaling. go-control-plane uses protobuf for xDS configuration. Istio depends on both.

4. **Code Path Analysis**: The vulnerability only triggers on JSON unmarshal of `Any` types. Search each repo for actual usage of `protojson.Unmarshal` or `jsonpb.Unmarshal` with messages containing `Any` fields. This distinguishes truly affected services from those that just import protobuf.

## Output

Write findings to `/workspace/BLAST_RADIUS.md`.
