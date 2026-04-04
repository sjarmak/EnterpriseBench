# 4-Repo PoC Results: Kill-or-Proceed Gate

**Date**: 2026-04-03
**Verdict**: **PROCEED** — all constraints met with wide margins.

## Configuration

| Repo                  | Tag     | Shallow Size |
| --------------------- | ------- | ------------ |
| opencontainers/runc   | v1.1.11 | 18 MB        |
| containerd/containerd | v1.7.11 | 71 MB        |
| moby/moby             | v25.0.0 | 111 MB       |
| kubernetes/kubernetes | v1.29.0 | 384 MB       |

**Total workspace**: 584 MB across 4 repos
**Dependency chain**: kubernetes -> containerd -> runc; moby -> containerd -> runc

## Measurements

| Metric                | Constraint   | Actual      | Headroom                         |
| --------------------- | ------------ | ----------- | -------------------------------- |
| Docker image size     | —            | 1,306 MB    | Comparable to 2-repo Go template |
| Build time (no cache) | < 3,000s     | **29s**     | 99% margin                       |
| Build time (cached)   | < 3,000s     | **17s**     | 99% margin                       |
| Peak runtime memory   | < 8 GB       | **192 MiB** | 97.7% margin                     |
| Health check          | All repos OK | 4/4 OK      | —                                |

### Workload details (peak memory test)

Concurrent operations during peak measurement:

- `go mod download` in kubernetes, moby, containerd (3 parallel)
- 5x recursive `grep -r "func " kubernetes/ --include="*.go"` (parallel)
- Cross-repo greps (moby->containerd refs, containerd->runc refs)

Peak observed: **192 MiB** (2.3% of 8 GB limit)

### Why memory is so low

The workspace is just source code on disk — shallow clones with no build artifacts.
Agent workloads (grep, file reads, `go list`) are IO-bound, not memory-bound.
Memory would spike significantly only if tasks required `go build` of full repos
(kubernetes alone would need ~4 GB for a full build), but EB tasks test
**context retrieval**, not compilation.

## Cross-repo grep performance

| Query                           | Repos              | Matches     | Wall time |
| ------------------------------- | ------------------ | ----------- | --------- |
| `containerd` in moby/\*.go      | moby -> containerd | 1,147 files | 45ms      |
| `runc` in containerd/\*.go      | containerd -> runc | 314 files   | 35ms      |
| `container` in kubernetes/\*.go | kubernetes (broad) | 1,595 files | 122ms     |

All sub-200ms — well within interactive agent response times.

## Dockerfile

`scripts/sandbox/templates/go_4repo_poc.Dockerfile` — extends the existing
`go_multi_repo.Dockerfile` pattern with 4 repos instead of 2.

## Recommendation

The 4-repo tier is viable. The PRD's concern about "workspace sizes for 4-5 large
repos stressing the 8GB memory limit" does not materialize because:

1. Shallow clones are compact (584 MB total for 4 repos including K8s)
2. Agent workloads are IO/search-bound, not memory-bound
3. No full compilation is needed for retrieval-focused tasks

**Next steps**:

- Author first real 4-repo task using this sandbox (incident_investigation: containerd/runc/moby is the natural candidate)
- Consider 5-repo PoC if needed, though diminishing returns likely (K8s alone is 384 MB)
- Keep the `multi_repo` stratum in the PRD task mix targets
