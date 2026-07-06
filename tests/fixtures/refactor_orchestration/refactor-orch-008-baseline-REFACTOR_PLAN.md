# Refactor Plan: go-grpc-middleware v1 Removal Cascade

## 1. Numbered List of Changes (Topological Order)

### Phase A — etcd: Migrate logging to middleware v2 (mirrors PR #20420)

**Step 1** — Add `github.com/grpc-ecosystem/go-grpc-middleware/v2` to etcd `tests/go.mod`
and replace the v1 `logging/settable` import with its v2 equivalent.

- **File**: `etcd/tests/integration/testing.go`
- **Change**: Replace `grpc_logsettable "github.com/grpc-ecosystem/go-grpc-middleware/logging/settable"` with the v2 logger API (`"github.com/grpc-ecosystem/go-grpc-middleware/v2/interceptors/logging"` or the v2 settable logger shim)
- **Why first**: The test-only logging dependency is simpler and self-contained; resolving it confirms v2 is compatible before touching production paths.

---

### Phase B — etcd: Replace v1 interceptor chaining with native gRPC (prerequisite to removing v1)

**Step 2** — Replace `grpc_middleware.ChainUnaryServer` / `ChainStreamServer` with native gRPC chaining in the main server.

- **File**: `etcd/server/etcdserver/api/v3rpc/grpc.go` (lines 25, 65–66)
- **Change**:
  ```go
  // Remove import:
  grpc_middleware "github.com/grpc-ecosystem/go-grpc-middleware"

  // Replace:
  opts = append(opts, grpc.UnaryInterceptor(grpc_middleware.ChainUnaryServer(chainUnaryInterceptors...)))
  opts = append(opts, grpc.StreamInterceptor(grpc_middleware.ChainStreamServer(chainStreamInterceptors...)))
  // With:
  opts = append(opts, grpc.ChainUnaryInterceptor(chainUnaryInterceptors...))
  opts = append(opts, grpc.ChainStreamInterceptor(chainStreamInterceptors...))
  ```
- **Precondition**: etcd already uses `google.golang.org/grpc v1.59.0`; native chaining was introduced in gRPC-Go v1.53.0, so no gRPC version bump is required.

---

### Phase C — etcd: Replace go-grpc-prometheus with a custom/reimplemented Prometheus interceptor

**Step 3** — Reimplement or substitute prometheus interceptors in the main gRPC server.

- **Files**:
  - `etcd/server/etcdserver/api/v3rpc/grpc.go` (lines 26, 48, 56, 86)
  - `etcd/server/embed/etcd.go` (line 50, 856)
  - `etcd/server/etcdmain/grpc_proxy.go` (lines 46, 460–461)
- **Change**: Remove `grpc_prometheus "github.com/grpc-ecosystem/go-grpc-prometheus"` imports and replace:
  - `grpc_prometheus.UnaryServerInterceptor` → custom `newPrometheusUnaryInterceptor()` backed by `prometheus/client_golang`
  - `grpc_prometheus.StreamServerInterceptor` → custom `newPrometheusStreamInterceptor()`
  - `grpc_prometheus.Register(grpcServer)` → manual registration of per-method counters via `prometheus.MustRegister`
  - `grpc_prometheus.EnableHandlingTimeHistogram()` → register a histogram manually
- **Note**: go-grpc-prometheus itself imports go-grpc-middleware v1 internally; removing it also removes the transitive v1 pull.

---

### Phase D — etcd: Remove archived dependencies entirely (mirrors PR #21295)

**Step 4** — Remove `go-grpc-middleware v1` and `go-grpc-prometheus v1` from all etcd go.mod files.

- **Files**:
  - `etcd/server/go.mod` (lines 17–18)
  - `etcd/tests/go.mod` (lines 24–25)
  - `etcd/client/v3/go.mod` (line 9 — go-grpc-prometheus)
  - `etcd/go.mod` (lines 55–56 — indirect entries)
- **Change**: Delete the `require` entries and run `go mod tidy` on each module.
- **Validation**: `go build ./...` and `go test ./...` across all etcd modules must pass.

---

### Phase E — Kubernetes: Update vendored etcd to post-removal version

**Step 5** — Bump kubernetes' vendored etcd to the version produced after Steps 1–4.

- **Files**:
  - `kubernetes/vendor/go.etcd.io/etcd/server/v3/etcdserver/api/v3rpc/grpc.go` (vendored copy)
  - `kubernetes/vendor/go.etcd.io/etcd/server/v3/embed/etcd.go` (vendored copy)
  - All other vendored etcd files that referenced the archived packages
- **Change**: Run `go get go.etcd.io/etcd/...@<new-tag>` and `go mod vendor` to refresh the vendor tree. The vendored copies should no longer contain references to either archived package.
- **Precondition**: Steps 1–4 must be merged and tagged in etcd.

---

### Phase F — Kubernetes: Remove direct go-grpc-prometheus dependency (mirrors PR #135538)

**Step 6** — Remove the Kubernetes-side direct use of `go-grpc-prometheus`.

- **File**: `kubernetes/staging/src/k8s.io/apiserver/pkg/storage/storagebackend/factory/etcd3.go` (lines 32, 83–87, 309–329)
- **Change**:
  - Remove `grpcprom "github.com/grpc-ecosystem/go-grpc-prometheus"` import
  - Replace `legacyregistry.RawMustRegister(grpcprom.DefaultClientMetrics)` in `init()` — since the new etcd client no longer exposes `DefaultClientMetrics`, remove the registration or replace with whatever metrics the new etcd client exposes
  - Replace `grpcprom.UnaryClientInterceptor` / `grpcprom.StreamClientInterceptor` in dial options with a custom or otelgrpc-based metrics interceptor (otelgrpc is already imported)
- **Files (go.mod)**:
  - `kubernetes/staging/src/k8s.io/apiserver/go.mod` (line 23)
  - `kubernetes/go.mod` (lines 165–166)

---

## 2. Dependency Graph

```
go-grpc-middleware v1 (archived)
│
├── [ChainUnaryServer/ChainStreamServer]
│   └── etcd/server/etcdserver/api/v3rpc/grpc.go
│
└── [logging/settable]
    └── etcd/tests/integration/testing.go

go-grpc-prometheus v1 (archived)
│   [internally imports go-grpc-middleware v1]
│
├── etcd/server/etcdserver/api/v3rpc/grpc.go
│   (UnaryServerInterceptor, StreamServerInterceptor, Register)
│
├── etcd/server/embed/etcd.go
│   (EnableHandlingTimeHistogram)
│
├── etcd/server/etcdmain/grpc_proxy.go
│   (UnaryServerInterceptor, StreamServerInterceptor)
│
├── etcd/tests/integration/clientv3/metrics_test.go
│   (grpcprom — test only)
│
└── kubernetes/staging/src/k8s.io/apiserver/.../etcd3.go
    (DefaultClientMetrics, UnaryClientInterceptor, StreamClientInterceptor)

etcd (v3.5.17)
└── kubernetes (v1.33.0)
    [via vendored copy at kubernetes/vendor/go.etcd.io/etcd/...]
```

**Topological order** (must be respected):

```
Step 1 (etcd: v2 logging) →
Step 2 (etcd: native chain) →
Step 3 (etcd: prometheus reimpl) →
Step 4 (etcd: remove deps) →
Step 5 (k8s: vendor etcd) →
Step 6 (k8s: remove grpcprom)
```

Steps 1 and 2 have no inter-dependency and **can be parallelised** (see §4).

---

## 3. Migration Strategy Per Component

### go-grpc-middleware v1 → gRPC-Go native

| Old API | Replacement | Notes |
|---|---|---|
| `grpc_middleware.ChainUnaryServer(...)` | `grpc.ChainUnaryInterceptor(...)` | Available since gRPC-Go v1.53.0 |
| `grpc_middleware.ChainStreamServer(...)` | `grpc.ChainStreamInterceptor(...)` | Same version gate |
| `logging/settable.ReplaceGrpcLoggerV2()` | `go-grpc-middleware/v2` settable logger or manual `grpclog.SetLoggerV2()` | Only used in integration tests |

### go-grpc-prometheus v1 → custom Prometheus interceptors

go-grpc-prometheus is itself archived and has no supported successor with identical API. The migration options are:

**Option A (chosen by etcd PR #21295)**: Inline minimal Prometheus instrumentation using `prometheus/client_golang` counters/histograms directly inside custom interceptors. This is the smallest-surface approach.

**Option B**: Adopt `go-grpc-middleware/v2` provider `providers/prometheus` — this is the v2 ecosystem equivalent but requires go-grpc-middleware/v2.

**Option C**: Use OpenTelemetry metrics (already partially present via `otelgrpc`) for a unified observability approach.

Regardless of option:
- Server-side: `grpc_prometheus.Register(server)` must be replaced by explicit per-service metric registration after server creation.
- `EnableHandlingTimeHistogram()` must become an explicit histogram `Register` call with the same bucket boundaries.
- Client-side (Kubernetes): `DefaultClientMetrics` auto-init must be removed or replaced with explicit registration of whatever metric struct the new interceptor exposes.

### etcd client/v3

`client/v3/retry_interceptor.go` is already a clean-room reimplementation (not a direct import); it only holds a comment reference to the old package. No code change needed — only the go.mod entry for `go-grpc-prometheus` must be removed (the client referenced it only transitively through the server module).

---

## 4. Parallelisation Annotations

```
┌─────────────────────────────────────────────────┐
│  CAN RUN IN PARALLEL                             │
│  Step 1: etcd logging/settable → v2              │
│  Step 2: etcd ChainUnary/Stream → native gRPC    │
└──────────────┬──────────────────────────────────┘
               │  both merged
               ▼
┌─────────────────────────────────────────────────┐
│  Step 3: etcd go-grpc-prometheus → custom impls  │
│  (depends on Step 2 landing cleanly)             │
└──────────────┬──────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────┐
│  Step 4: etcd go.mod cleanup & tidy              │
└──────────────┬──────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────┐
│  Step 5: kubernetes vendor etcd bump             │
│  Step 6: kubernetes remove grpcprom              │
│  (Steps 5 and 6 CAN be done in same PR)          │
└─────────────────────────────────────────────────┘
```

Steps 5 and 6 are effectively merged in a single Kubernetes PR because the vendor bump already eliminates the transitive need for go-grpc-prometheus; the direct usage in `etcd3.go` can be fixed in the same changeset.

---

## 5. Risk Assessment

### High Risk

| Risk | Description | Mitigation |
|---|---|---|
| **Prometheus metric name/label regression** | go-grpc-prometheus emits well-known metric names (`grpc_server_handled_total`, `grpc_server_started_total`, etc.) that dashboards and alerts depend on. A custom reimplementation must preserve these names or all existing Grafana/alertmanager configs break silently. | Audit existing metric names before removing; write a test that asserts exported metric names match the old set. |
| **etcd/kubernetes version skew** | Kubernetes vendors etcd at a specific SHA. Any delay between etcd tagging the removal and kubernetes updating the vendor tree leaves kubernetes building against the old code with a stale go.mod. | Coordinate release timing; keep the etcd removal PR behind a feature gate or experimental flag until kubernetes is ready. |

### Medium Risk

| Risk | Description | Mitigation |
|---|---|---|
| **gRPC interceptor ordering change** | The old code uses `grpc.UnaryInterceptor(grpc_middleware.ChainUnaryServer(...))` (single-interceptor wrapping). The new `grpc.ChainUnaryInterceptor(...)` is semantically equivalent but call ordering must be verified against panic-recovery and logging interceptors. | Integration tests that inject a panicking handler must still see the recovery interceptor fire. |
| **go-grpc-prometheus `Register()` side-effects** | `grpc_prometheus.Register(server)` initialises zero-value counters for all registered services, ensuring dashboards show 0 before any traffic. A naive replacement that only registers on first call will produce gaps. | The replacement must eagerly register all per-method metrics immediately after `grpc.NewServer`. |
| **`DefaultClientMetrics` auto-init in kubernetes** | `go-grpc-prometheus` registers `DefaultClientMetrics` via `init()`. Kubernetes works around this by calling `legacyregistry.RawMustRegister(grpcprom.DefaultClientMetrics)`. Removing the import removes the `init()` side-effect too; the new interceptor must perform equivalent registration. | Confirm that the replacement interceptor registers its metrics before the first dial. |
| **logging/settable test coverage** | `grpc_logsettable.ReplaceGrpcLoggerV2()` redirects internal gRPC log output in integration tests, suppressing noise. Losing this in migration can flood CI logs and obscure real failures. | Implement equivalent redirect using `grpclog.SetLoggerV2()` with a test-scoped zap logger before removing the v1 dependency. |

### Low Risk

| Risk | Description | Mitigation |
|---|---|---|
| **go.sum / vendor inconsistency** | Running `go mod tidy` across etcd's multi-module workspace may leave stale indirect entries if done out of order. | Run tidy in dependency order: api → client/pkg → client/v3 → server → tests. |
| **etcd grpc_proxy single-interceptor pattern** | `etcd/server/etcdmain/grpc_proxy.go` uses `grpc.StreamInterceptor` + `grpc.UnaryInterceptor` directly (not chained), so only one interceptor is registered. Replacing it is straightforward but must not accidentally introduce a chain wrapper. | Keep the single-interceptor pattern; only change the interceptor function value itself. |
