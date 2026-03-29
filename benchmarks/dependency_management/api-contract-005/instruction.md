# Impact Analysis: Protobuf v2 Migration Runtime Behavior Change

## Context

We recently migrated gRPC-Go from `github.com/golang/protobuf` to `google.golang.org/protobuf/proto` (PR #6919). After deploying, we started getting reports of type assertion failures in error handling code. The issue is subtle: `Status.Details()` used to return `MessageV1` types, but now returns `MessageV2` types.

This is a *runtime* behavior change — everything compiles fine but type assertions against concrete protobuf types fail at runtime. We need a thorough investigation.

## What I Need

1. **Root cause**: Trace the exact code path change in `internal/status/status.go`. What function was `ptypes.UnmarshalAny` replaced with, and why does the return type differ?

2. **Blast radius within grpc-go**: Find every file that calls `Status.Details()` or `Status.WithDetails()`. Each one could be affected by the type change.

3. **Fix analysis**: PR #7724 fixed this. What approach did it take? Did it restore MessageV1 compatibility or did callers need to change?

4. **External consumer impact**: Any gRPC-Go user with code generated from `protoc-gen-go` < v1.4 (released 2020) is potentially affected. What's the failure mode and what should we tell them?

## Output

Write your findings to `/workspace/analysis/IMPACT_REPORT.md`. Include the root cause, the list of affected files, the fix approach, and consumer guidance.
