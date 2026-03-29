# Impact Analysis: go-control-plane Module Split

## Context

We just hit a weird error running `go get -u` on our project that depends on `github.com/envoyproxy/go-control-plane`. The go-control-plane team restructured their repo into a multi-module layout (PR #714), creating separate Go modules for the generated Envoy protobuf bindings (`envoy/` and `contrib/` submodules).

Turns out this broke dependency resolution for multiple major projects. We need to understand what happened and whether we need to apply a workaround.

## What I Need

1. **Module structure**: What does the new multi-module layout look like? How do `go.mod` files in the root, `envoy/`, and `contrib/` directories relate to each other?

2. **Affected consumers**: Which projects reported breakage? I've heard istio, grpc-go, and google-cloud-go were all affected. What error did they see?

3. **Fix analysis**: The go-control-plane team landed PR #1075 to fix this. What backward-compatible imports did they add? Why do empty `.go` files solve a module resolution problem?

4. **grpc-go follow-up**: grpc-go also needed its own fix (PR #8067). What did it change in its go.mod?

## Output

Write your findings to `/workspace/analysis/IMPACT_REPORT.md`.
