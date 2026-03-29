# Incident Investigation Candidates

Mined: 2026-03-28

## Selection Criteria
- Cross-service error chain (symptom in service A, root cause in service B)
- Public bug report or postmortem with clear error log/alert
- Fix commit identifies root cause file(s)
- Codebase available at buggy commit via git tag/hash
- Estimated authoring time <6 hours per task

---

## Candidate 1: K8s Watch Cache Missing Events (etcd interaction)

- **Repos:** `kubernetes/kubernetes` (apiserver watch cache + etcd3 storage)
- **Issue:** [#49956](https://github.com/kubernetes/kubernetes/issues/49956)
- **Fix PR:** [#49992](https://github.com/kubernetes/kubernetes/pull/49992)
- **Merged:** 2017-08-02
- **Buggy rev:** `v1.7.3` (before fix)
- **Error symptom:** Controllers miss watch events after establishing watches; CRD/TPR watches silently drop events
- **Root cause:** `watch_cache.go` — empty watch event cache allowed establishing watches at a resourceVersion it couldn't serve, causing off-by-one error. The watch cache should have returned "410 Gone" to force relist, but instead silently skipped events.
- **Error chain:** Controller -> API Server watch handler -> Watch Cache (cacher.go) -> etcd3 storage layer
- **Fix files:** `staging/src/k8s.io/apiserver/pkg/storage/watch_cache.go`, `staging/src/k8s.io/apiserver/pkg/storage/tests/cacher_test.go`
- **Difficulty:** hard (2-service error chain, clear error log)
- **Viability:** HIGH -- excellent cross-component trace, well-documented scenario
- **Estimated authoring:** 4 hours

## Candidate 2: K8s Watch Cache Delete Event Wrong ResourceVersion

- **Repos:** `kubernetes/kubernetes` (apiserver watch cache + etcd3 watcher)
- **Issue:** [#58545](https://github.com/kubernetes/kubernetes/issues/58545), [kubernetes/client-go#338](https://github.com/kubernetes/client-go/issues/338)
- **Fix PR:** [#58547](https://github.com/kubernetes/kubernetes/pull/58547)
- **Merged:** 2018-01-23
- **Buggy rev:** `v1.9.1` (before fix)
- **Error symptom:** Clients receive DELETE watch events with stale resourceVersion, causing watch re-establishment to miss subsequent events
- **Root cause:** `cacher.go` — when watch cache filtering converts a Modified event to a Deleted event (object moves out of namespace filter), it sends PrevObject with the old resourceVersion instead of the event's current resourceVersion. Corresponding logic existed correctly in `etcd_watcher.go` and `etcd3/watcher.go` but was missing in the cache layer.
- **Error chain:** client-go informer -> API Server watch cache (cacher.go) -> etcd3/watcher.go -> etcd
- **Fix files:** `staging/src/k8s.io/apiserver/pkg/storage/cacher.go`, `staging/src/k8s.io/apiserver/pkg/storage/cacher_whitebox_test.go`
- **Difficulty:** hard (cross-component resourceVersion tracking, subtle filtering logic)
- **Viability:** HIGH -- clear error chain across watch cache and etcd storage layers
- **Estimated authoring:** 4 hours

## Candidate 3: K8s API Server etcd Metrics Data Race

- **Repos:** `kubernetes/kubernetes` (apiserver config + etcd3 metrics)
- **Issue:** [#120174](https://github.com/kubernetes/kubernetes/pull/120174) (PR description contains full race trace)
- **Fix PR:** [#120174](https://github.com/kubernetes/kubernetes/pull/120174)
- **Merged:** 2023-08-28
- **Buggy rev:** `v1.28.0` (before fix)
- **Error symptom:** `WARNING: DATA RACE` in CI -- Write at `SetStorageMonitorGetter()` in `metrics.go` by multiple goroutines during integration tests
- **Root cause:** `staging/src/k8s.io/apiserver/pkg/storage/etcd3/metrics/metrics.go` -- global variable `storageMonitorGetter` set by `SetStorageMonitorGetter()` without synchronization, called from `EtcdOptions.ApplyWithStorageFactoryTo()` during apiserver config setup
- **Error chain:** kube-apiserver app config -> controlplane apiserver config -> etcd options -> etcd3 metrics (global state)
- **Fix files:** `staging/src/k8s.io/apiserver/pkg/storage/etcd3/metrics/metrics.go`
- **Difficulty:** hard (data race across config, storage, and metrics packages)
- **Viability:** HIGH -- clear stack trace, single fix file, well-scoped
- **Estimated authoring:** 3 hours

## Candidate 4: Grafana Prometheus JSON Response Parsing Silent Failure

- **Repos:** `grafana/grafana` (datasource proxy + converter) + `prometheus/prometheus` (API response format)
- **Issue:** [grafana#73747](https://github.com/grafana/grafana/issues/73747)
- **Fix PR:** [grafana#73788](https://github.com/grafana/grafana/pull/73788)
- **Merged:** 2023-08-28
- **Buggy rev:** Grafana `v10.1.0` (before fix)
- **Error symptom:** Prometheus queries return partial/empty data with no error when `response_limit` is hit or JSON is malformed. Users see incomplete dashboards with no indication of failure.
- **Root cause:** `pkg/util/converter/prom.go` -- the Prometheus response JSON parser (using jsoniter) never checked `iter.Error` after parsing operations. When response_limit truncated the body, jsoniter silently stopped parsing mid-stream.
- **Error chain:** Grafana dashboard -> Prometheus datasource plugin -> dataproxy (response_limit) -> converter/prom.go (jsoniter) -> Prometheus HTTP API
- **Fix files:** `pkg/util/converter/prom.go`, `pkg/util/converter/prom_test.go`, `pkg/util/converter/jsonitere/jsonitere.go`
- **Difficulty:** hard (cross-service data flow, silent failure mode)
- **Viability:** HIGH -- real user-facing incident, clear error chain between Grafana and Prometheus
- **Estimated authoring:** 5 hours

## Candidate 5: Docker Daemon Spurious Restart Warnings on Shutdown (containerd interaction)

- **Repos:** `moby/moby` (daemon + restart manager) + `containerd/containerd` (shim lifecycle)
- **Issue:** Described in PR body
- **Fix PR:** [moby#52079](https://github.com/moby/moby/pull/52079)
- **Merged:** 2026-02-23
- **Buggy rev:** moby `v28.0.0` (before fix)
- **Error symptom:** `WARN ShouldRestart failed, container will not be restarted error="restart canceled"` during graceful daemon shutdown. Confusing "ignoring event" messages for containerd task-delete events.
- **Root cause:** `daemon/monitor.go` -- `handleContainerExit` calls `RestartManager().ShouldRestart` which returns `ErrRestartCanceled` when restart manager was already stopped by `ExitOnNext()`. The warning is spurious because the daemon is shutting down intentionally.
- **Error chain:** SIGINT -> daemon shutdown -> container.ExitOnNext() -> containerd shim TaskDelete event -> daemon/monitor.go handleContainerExit -> RestartManager.ShouldRestart -> ErrRestartCanceled (logged as warning)
- **Fix files:** `daemon/monitor.go`, `daemon/container/container.go`, `daemon/internal/libcontainerd/remote/client.go`
- **Difficulty:** hard (cross-component lifecycle: daemon, containerd shim, restart manager)
- **Viability:** HIGH -- clear error chain, real log output in PR, recent fix
- **Estimated authoring:** 4 hours

## Candidate 6: Istio Envoy WASM Module Crash Under Load During Upgrade

- **Repos:** `istio/istio` (EnvoyFilter config push) + `envoyproxy/envoy` (WASM runtime)
- **Issue:** [istio#33091](https://github.com/istio/istio/issues/33091)
- **Error symptom:** Segfault in `Envoy::Extensions::Common::Wasm::Context::decodeData()` when WASM module URI is updated in EnvoyFilter while cluster is under load. All proxies crash in unison.
- **Root cause:** During WASM module hot-reload, Envoy deletes the old plugin context while in-flight requests still hold references to it. The config push from Istiod triggers simultaneous reload across all sidecars.
- **Error chain:** Istiod config push (EnvoyFilter change) -> Envoy xDS update -> WASM module reload -> context deletion -> in-flight request accesses freed context -> SIGSEGV
- **Difficulty:** expert (3+ services: Istiod, Envoy proxy, WASM runtime; misleading crash location)
- **Viability:** MEDIUM -- complex multi-service chain but fix may span envoy upstream; authoring harder
- **Estimated authoring:** 6 hours

## Candidate 7: Prometheus Scrape Loop Goroutine Leak

- **Repos:** `prometheus/prometheus` (scrape package)
- **Issue:** [#17553](https://github.com/prometheus/prometheus/issues/17553)
- **Fix PR:** [#17554](https://github.com/prometheus/prometheus/pull/17554)
- **Merged:** 2025-12-12
- **Buggy rev:** Before fix (late 2025)
- **Error symptom:** Goroutine leak in scrape loop -- scraping goroutines block indefinitely on unbuffered error channel when receiver stops listening
- **Root cause:** `scrape/scrape.go` -- `scrapeAndReport` sends errors to unbuffered `errc` channel without checking context cancellation; if receiver returns early (timeout), sender blocks forever
- **Difficulty:** hard (goroutine lifecycle, context propagation)
- **Viability:** MEDIUM -- single-repo (no cross-service chain), better as calibration task
- **Estimated authoring:** 3 hours

---

## Go/No-Go Assessment

**Viable candidates: 6** (candidates 1-5 are strong, candidate 6 is stretch)

All 6 viable candidates have:
- Clear error log or alert as starting point
- Identifiable buggy commit (via git tag)
- Fix commit identifying root cause file(s)
- Cross-component error chains suitable for investigation tasks
- Estimated authoring <6 hours each

**Recommendation:** Author tasks for candidates 1, 2, 4, and 5 (best mix of difficulty levels and repo diversity). Drop candidate 7 (single-repo). Candidate 6 as stretch if time permits.

**GO** -- proceed to P4.2 authoring.
