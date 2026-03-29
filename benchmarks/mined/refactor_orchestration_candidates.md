# Refactor Orchestration Candidates

Mined 2026-03-28. Each candidate has multi-PR chronology across >=2 repos with clear dependency ordering.

## Candidate 1: grpc-go v1.72 bump cascade (grpc-go -> etcd -> k8s)
- **Repos:** grpc/grpc-go, etcd-io/etcd, kubernetes/kubernetes
- **Event:** grpc-go v1.72.1 released 2025-05-14; etcd needed grpc compat update; k8s PR #131838 bumped grpc to v1.72.1 (merged 2025-05-20)
- **Ordering:** grpc-go release -> etcd compatibility -> k8s vendor bump
- **PRs:** grpc-go v1.72.1 release, k8s#131838
- **Difficulty:** hard (3 repos, linear chain)
- **Confidence:** 0.95

## Candidate 2: grpc Dial->NewClient API migration (grpc-go -> etcd -> k8s)
- **Repos:** grpc/grpc-go, etcd-io/etcd, kubernetes/kubernetes
- **Event:** grpc-go deprecated grpc.Dial in v1.64 (2024-06), etcd PR #21282 migrated to NewClient (merged 2026-02-26), k8s consumes etcd client
- **Ordering:** grpc-go deprecation -> etcd migration -> k8s client update
- **PRs:** grpc-go deprecation, etcd#21282, k8s#128419 (etcd 3.6 client update, merged 2025-05-16)
- **Difficulty:** expert (3 repos, API migration not just version bump)
- **Confidence:** 0.90

## Candidate 3: go-grpc-middleware removal cascade (grpc-ecosystem -> etcd -> k8s)
- **Repos:** grpc-ecosystem/go-grpc-middleware, etcd-io/etcd, kubernetes/kubernetes
- **Event:** go-grpc-middleware v1 archived, etcd PR #20420 migrated to v2 (2025-08-07), etcd PR #21295 removed dependency entirely (2026-02-12), k8s PR #135538 dropped go-grpc-prometheus (2025-12-18)
- **Ordering:** middleware v2 migration -> etcd removes v1 dep -> k8s drops prometheus middleware
- **PRs:** etcd#20420, etcd#21295, k8s#135538
- **Difficulty:** expert (3 repos, multi-step removal)
- **Confidence:** 0.90

## Candidate 4: protobuf v1->v2 migration in grpc-go (protobuf -> grpc-go -> etcd)
- **Repos:** google/go-genproto (protobuf), grpc/grpc-go, etcd-io/etcd
- **Event:** grpc-go PR #6919 moved from github.com/golang/protobuf to google.golang.org/protobuf (merged 2024-01-30), downstream consumers needed updates
- **Ordering:** protobuf v2 release -> grpc-go migration -> etcd/k8s adapt
- **PRs:** grpc-go#6919
- **Difficulty:** hard (3 repos, import path change)
- **Confidence:** 0.92

## Candidate 5: etcd 3.6 client + dependency reduction cascade
- **Repos:** etcd-io/etcd, kubernetes/kubernetes
- **Event:** etcd 3.6 dropped cloud library deps; k8s PR #128419 updated to etcd 3.6 client (merged 2025-05-16), reducing total deps from 365 to 247
- **Ordering:** etcd 3.6 release -> k8s client library update -> k8s vendor tree cleanup
- **PRs:** k8s#128419
- **Difficulty:** medium (2 repos, linear chain)
- **Confidence:** 0.95

## Candidate 6: cobra v1.10 bump cascade (cobra -> k8s)
- **Repos:** spf13/cobra, kubernetes/kubernetes
- **Event:** cobra v1.10.2 released; k8s PR #137843 bumped cobra (merged 2026-03-18)
- **Ordering:** cobra release -> k8s vendor bump
- **Difficulty:** medium (2 repos, linear chain)
- **Confidence:** 0.95

## Candidate 7: Babel 8 plugin-transform removal cascade (babel monorepo internal)
- **Repos:** babel/babel (monorepo: @babel/core, @babel/preset-env, @babel/plugin-transform-*)
- **Event:** Babel 8 removed plugin-transform-react-compat/source/self (PR #17620, 2025-12-16), then removed plugin-transform-property-mutators (PR #17882, 2026-03-19)
- **Ordering:** core breaking change -> preset-env update -> plugin removal -> consumer adaptation
- **PRs:** babel#17620, babel#17882, babel#17670
- **Difficulty:** hard (monorepo, 4+ packages, diamond deps)
- **Confidence:** 0.88

## Candidate 8: Go 1.26 + distroless update cascade in k8s
- **Repos:** golang/go, kubernetes/kubernetes, multiple staging repos
- **Event:** k8s PR #137080 bumped Go to 1.26.0, updated distroless iptables images (merged 2026-03-05)
- **Ordering:** Go release -> k8s build infra -> staging repos -> e2e image rebuild
- **PRs:** k8s#137080
- **Difficulty:** hard (monorepo cross-package, build system + runtime)
- **Confidence:** 0.90

## Candidate 9: OpenTelemetry collector dependency cascade (otel-go -> prometheus -> k8s)
- **Repos:** open-telemetry/opentelemetry-go, prometheus/prometheus, kubernetes/kubernetes
- **Event:** OTel collector updates required coordinated bumps; k8s PR #136820 updated OTel deps (merged 2026-02-10)
- **Ordering:** otel-go release -> prometheus client adaptation -> k8s instrumentation update
- **PRs:** k8s#136820
- **Difficulty:** expert (3+ repos, cross-language observability stack)
- **Confidence:** 0.85

## Selected for Task Authoring (8 tasks)

| # | Candidate | Difficulty | Repos |
|---|-----------|-----------|-------|
| 1 | C5: etcd 3.6 client cascade | medium | 2 |
| 2 | C6: cobra v1.10 bump | medium | 2 |
| 3 | C1: grpc-go v1.72 bump | hard | 3 |
| 4 | C4: protobuf v1->v2 migration | hard | 3 |
| 5 | C7: Babel 8 plugin removal | hard | 1 (monorepo) |
| 6 | C8: Go 1.26 update cascade | hard | 1 (monorepo cross-pkg) |
| 7 | C2: grpc Dial->NewClient migration | expert | 3 |
| 8 | C3: go-grpc-middleware removal | expert | 3 |

Distribution: 2 medium (25%), 4 hard (50%), 2 expert (25%) — close to target 20/50/30.
