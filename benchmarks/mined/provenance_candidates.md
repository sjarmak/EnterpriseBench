# Error Message Provenance — Mined Candidates

Task type: `error-trace-*` (Type #6)
Mined: 2026-03-28
Suite mapping: `customer_escalation` (primary), `incident_response` (secondary)

## Summary

| # | Repo | Error String | Difficulty | Issue | Fix PR |
|---|------|-------------|------------|-------|--------|
| 1 | kubernetes/kubernetes | "startTime cannot be removed for unsuspended job" | medium | #136527 | #136585 |
| 2 | kubernetes/kubernetes | "Failed to list existing sets" / "nftables sync failed" | hard | #136786 | #136796 |
| 3 | kubernetes/kubernetes | "PostStartHook ... failed: unable to perform initial IP and Port allocation check" | expert | #136288 | #137147 |
| 4 | kubernetes/kubernetes | Container terminated with `Reason: Error` but never restarts | hard | #136910 | #137146 |
| 5 | kubernetes/kubernetes | "spec.SessionAffinity is ignored for headless services" | medium | #134040 | #134054 |
| 6 | kubernetes/kubernetes | Container fail to create — "invalid UTF-8" gRPC error with `$` + non-ASCII in env var | hard | #136323 | #136325 |
| 7 | hashicorp/terraform | `[ERROR] AttachSchemaTransformer: No provider config schema available` for builtin provider | medium | #34207 | #38183 |
| 8 | hashicorp/terraform | Nil pointer dereference panic during backend migration with permission errors | hard | #38027 | #38028 |
| 9 | hashicorp/terraform | Copy-paste error in backend migration error message | medium | N/A | #38116 |
| 10 | grafana/grafana | `runtime error: index out of range [0] with length 0` — Jaeger datasource crash on empty trace | hard | #119439 | #120266 |
| 11 | grafana/grafana | `Internal Server Error 500` when dashboard tag exceeds 50 characters | medium | #110848 | #116047 |
| 12 | hashicorp/vault | OCSP verification returns issuer serial number instead of subject serial number | hard | #27126 | #27696 |
| 13 | docker/cli + moby/moby | Blank warnings printed on stderr by `docker stack deploy --resolve-image always` | medium | docker/cli#6674 | moby/moby#51600 |

---

## Candidate Details

### 1. kubernetes/kubernetes — Job validation error message is misleading

- **Issue:** [#136527](https://github.com/kubernetes/kubernetes/issues/136527)
- **Fix PR:** [#136585](https://github.com/kubernetes/kubernetes/pull/136585) (MERGED)
- **Error message:** `Job.batch "job-c4nbt" is invalid: status.startTime: Required value: startTime cannot be removed for unsuspended job`
- **Actual problem:** Error triggers for any `startTime` change (not just removal). The validation at `pkg/apis/batch/validation/validation.go:740-746` checks for inequality but reports "cannot be removed".
- **Files changed in fix:**
  - `pkg/apis/batch/validation/validation.go`
  - `pkg/apis/batch/validation/validation_test.go`
  - `pkg/registry/batch/job/strategy_test.go`
- **Difficulty:** medium — single format string, single-repo, direct code path
- **Why good candidate:** Error string is in source code, user sees exact message, fix is in the validation file. Agent must trace from user-visible error to the validation function.

### 2. kubernetes/kubernetes — kube-proxy nftables sync failure

- **Issue:** [#136786](https://github.com/kubernetes/kubernetes/issues/136786)
- **Fix PR:** [#136796](https://github.com/kubernetes/kubernetes/pull/136796) (MERGED)
- **Error messages:**
  - `"Failed to list existing sets" err="failed to run nft: signal: segmentation fault (core dumped)"`
  - `"nftables sync failed" err="signal: segmentation fault (core dumped)"`
  - `"Sync failed" ipFamily="IPv4" retryingTime="30s"`
- **Actual problem:** kube-proxy crashes when newer nftables (1.1.3+) have created sets with udata in the same namespace. Fix bumps knftables dependency.
- **Files changed in fix:**
  - `pkg/proxy/nftables/proxier.go`
  - `vendor/sigs.k8s.io/knftables/*.go` (multiple)
  - `go.mod`, `go.sum`
- **Difficulty:** hard — error wrapping across proxy → vendor library, multi-layer
- **Why good candidate:** Error message is logged via structured logging with wrapping. Agent must trace "Failed to list existing sets" through proxier.go to the knftables library.

### 3. kubernetes/kubernetes — kube-apiserver PostStartHook failure

- **Issue:** [#136288](https://github.com/kubernetes/kubernetes/issues/136288)
- **Fix PR:** [#137147](https://github.com/kubernetes/kubernetes/pull/137147) (MERGED)
- **Error messages:**
  - `PostStartHook "start-service-ip-repair-controllers" failed: unable to perform initial IP and Port allocation check`
  - `ipaddresses.networking.k8s.io "10.211.95.185" is forbidden: not yet ready to handle request`
  - `informer-sync,poststarthook/start-service-ip-repair-controllers check failed: readyz`
- **Actual problem:** Race condition during v1.32→v1.33 upgrade. RepairIPAddress controller tries to create IPAddress objects before the API is ready. MultiCIDRServiceAllocator enabled by default in v1.33.
- **Files changed in fix:**
  - `pkg/registry/core/service/ipallocator/controller/repairip.go`
  - `pkg/registry/core/service/ipallocator/controller/repairip_test.go`
  - `test/integration/servicecidr/startup_race_test.go`
- **Difficulty:** expert — multi-layer error propagation (hooks → controller → API admission), race condition
- **Why good candidate:** Multiple interleaved error messages in logs. Agent must trace through PostStartHook registration, the repair controller, and API admission.

### 4. kubernetes/kubernetes — Containers fail to restart when sidecar keeps running

- **Issue:** [#136910](https://github.com/kubernetes/kubernetes/issues/136910)
- **Fix PR:** [#137146](https://github.com/kubernetes/kubernetes/pull/137146) (MERGED)
- **Error message:** Container shows `State: Terminated, Reason: Error, Exit Code: 2` but never restarts. No explicit error message in logs — the "error" is the absence of expected behavior.
- **Actual problem:** Kubelet prober worker doesn't properly restart crashed containers when a sidecar container is still running.
- **Files changed in fix:**
  - `pkg/kubelet/prober/worker.go`
  - `pkg/kubelet/prober/worker_test.go`
  - `test/e2e_node/container_lifecycle_test.go`
- **Difficulty:** hard — no visible error string to grep; agent must reason about the "Error" state and trace through prober logic
- **Why good candidate:** Tests understanding of implicit error conditions. The only clue is `Reason: Error` in pod status.

### 5. kubernetes/kubernetes — Spurious headless service SessionAffinity warning

- **Issue:** [#134040](https://github.com/kubernetes/kubernetes/issues/134040)
- **Fix PR:** [#134054](https://github.com/kubernetes/kubernetes/pull/134054) (MERGED)
- **Error message:** `Warning: spec.SessionAffinity is ignored for headless services`
- **Actual problem:** SessionAffinity defaults to `None` when unset, so the validation cannot distinguish between "user set it" vs "defaulted". Warning fires even when user didn't set it.
- **Files changed in fix:**
  - `pkg/api/service/warnings.go`
  - `pkg/api/service/warnings_test.go`
- **Difficulty:** medium — single format string, single file, straightforward tracing
- **Why good candidate:** Clear warning message with direct source. Agent must find the warning generation in `warnings.go`.

### 6. kubernetes/kubernetes — UTF-8 truncation in env var expansion

- **Issue:** [#136323](https://github.com/kubernetes/kubernetes/issues/136323)
- **Fix PR:** [#136325](https://github.com/kubernetes/kubernetes/pull/136325) (MERGED)
- **Error message:** Container fails to create with gRPC error when env var contains `$` followed by non-ASCII character (invalid UTF-8 produced by truncation).
- **Actual problem:** The expansion function in `third_party/forked/golang/expansion/expand.go` truncates multi-byte UTF-8 characters when processing `$`-prefixed variable names.
- **Files changed in fix:**
  - `third_party/forked/golang/expansion/expand.go`
  - `third_party/forked/golang/expansion/expand_test.go`
- **Difficulty:** hard — error crosses multiple layers (env expansion → kubelet → CRI → gRPC), and the user-visible error is "invalid UTF-8" which is far from the root cause.
- **Why good candidate:** The error message seen by users (gRPC invalid UTF-8) is completely different from the root cause (byte truncation in expansion). Multi-hop tracing required.

### 7. hashicorp/terraform — Spurious ERROR log for builtin provider

- **Issue:** [#34207](https://github.com/kubernetes/kubernetes/issues/34207)
- **Fix PR:** [#38183](https://github.com/hashicorp/terraform/pull/38183) (MERGED)
- **Error message:** `[ERROR] AttachSchemaTransformer: No provider config schema available for provider["terraform.io/builtin/terraform"]`
- **Actual problem:** The builtin terraform provider doesn't return a config schema, causing `AttachSchemaTransformer` to log an ERROR even though this is expected behavior. Should be DEBUG level or the provider should return an empty schema.
- **Files changed in fix:**
  - `internal/builtin/providers/terraform/provider.go`
  - `internal/builtin/providers/terraform/provider_test.go`
- **Difficulty:** medium — single-repo, one-hop from log line to provider, clear string match
- **Why good candidate:** Agent must trace `AttachSchemaTransformer` log through the transform pipeline to understand why the builtin provider triggers it, then find the provider implementation.

### 8. hashicorp/terraform — Nil pointer crash during backend migration

- **Issue:** [#38027](https://github.com/hashicorp/terraform/issues/38027)
- **Fix PR:** [#38028](https://github.com/hashicorp/terraform/pull/38028) (MERGED)
- **Error message:** `panic: runtime error: invalid memory address or nil pointer dereference` during `terraform init -migrate-state` with GCS backend when user lacks `storage.objects.get` permission.
- **Actual problem:** Backend migration code doesn't nil-check the state returned when GCS returns a permission error.
- **Files changed in fix:**
  - `internal/command/meta_backend_migrate.go`
- **Difficulty:** hard — error wrapping from GCS SDK → backend → migration command, nil pointer makes the original error invisible
- **Why good candidate:** The panic hides the real error (permission denied). Agent must trace through backend migration to find where nil is returned without error check.

### 9. hashicorp/terraform — Copy-paste error in backend migration message

- **Fix PR:** [#38116](https://github.com/hashicorp/terraform/pull/38116) (MERGED)
- **Error message:** Incorrect error message displayed during backend migration (copy-paste error from another context).
- **Files changed in fix:**
  - `internal/command/meta_backend_errors.go`
- **Difficulty:** medium — direct string in a single error file
- **Why good candidate:** Simple provenance trace: find the error string in `meta_backend_errors.go`.

### 10. grafana/grafana — Jaeger datasource panic on empty trace response

- **Issue:** [#119439](https://github.com/grafana/grafana/issues/119439)
- **Fix PR:** [#120266](https://github.com/grafana/grafana/pull/120266) (MERGED)
- **Error message:** `runtime error: index out of range [0] with length 0` at `pkg/tsdb/jaeger/client.go:248`
- **Actual problem:** Jaeger client code accesses first element of trace response slice without checking for empty response.
- **Files changed in fix:**
  - `pkg/tsdb/jaeger/client.go`
  - `pkg/tsdb/jaeger/client_test.go`
- **Difficulty:** hard — error propagates through datasource query pipeline (Jaeger client → querydata → handler), panic makes it look like an infra issue
- **Why good candidate:** The stack trace points to the file but not the condition. Agent must understand Jaeger response structure and empty-response handling.

### 11. grafana/grafana — Dashboard tag 50+ char causes 500 error

- **Issue:** [#110848](https://github.com/grafana/grafana/issues/110848)
- **Fix PR:** [#116047](https://github.com/grafana/grafana/pull/116047) (MERGED)
- **Error message:** `Internal Server Error 500` when a dashboard tag exceeds 50 characters.
- **Actual problem:** No length validation on dashboard tags. Database column limit causes an unhandled error.
- **Files changed in fix:**
  - `pkg/registry/apis/dashboard/register.go`
  - `pkg/services/dashboards/database/database.go`
  - `pkg/services/dashboards/errors.go`
  - `packages/grafana-ui/src/components/TagsInput/TagsInput.tsx`
  - `public/app/features/manage-dashboards/utils/validation.ts`
  - `public/locales/en-US/grafana.json`
  - `pkg/tests/apis/dashboard/integration/api_validation_test.go`
- **Difficulty:** hard — error crosses frontend → backend API → database layer, with no helpful error message
- **Why good candidate:** The 500 error gives no clue. Agent must trace through API layer to the database schema to find the column length constraint. Fix spans both frontend and backend.

### 12. hashicorp/vault — OCSP verification returns wrong serial number in error

- **Issue:** [#27126](https://github.com/hashicorp/vault/issues/27126)
- **Fix PR:** [#27696](https://github.com/hashicorp/vault/pull/27696) (MERGED)
- **Error message:** OCSP verification error messages at `sdk/helper/ocsp/client.go:695-714` reference the issuer's serial number instead of the subject's serial number.
- **Actual problem:** The error formatting functions pass `issuer.SerialNumber` where they should pass `subject.SerialNumber`.
- **Files changed in fix:**
  - `sdk/helper/ocsp/client.go`
  - `builtin/logical/pki/integration_test.go`
  - `changelog/27696.txt`
- **Difficulty:** hard — OCSP/PKI domain complexity, error is technically correct syntax but semantically wrong
- **Why good candidate:** The error message is produced but with wrong data. Agent must understand the OCSP verification flow and distinguish issuer vs subject certificate fields.

### 13. docker/cli + moby/moby — Blank warnings from docker stack deploy

- **Issue:** [docker/cli#6674](https://github.com/docker/cli/issues/6674)
- **Fix PR:** [moby/moby#51600](https://github.com/moby/moby/pull/51600) (MERGED)
- **Error message:** Blank lines printed on stderr by `docker stack deploy` when using `--resolve-image always`.
- **Actual problem:** `ServiceCreate` and `ServiceUpdate` in the Docker client add empty warning strings to the response even when no actual warnings exist.
- **Files changed in fix:**
  - `client/service_create.go` (moby/moby)
  - `client/service_update.go` (moby/moby)
  - `vendor/github.com/moby/moby/client/service_create.go` (docker/cli vendor)
  - `vendor/github.com/moby/moby/client/service_update.go` (docker/cli vendor)
- **Difficulty:** medium — cross-repo (CLI → daemon client library), but straightforward string tracing
- **Why good candidate:** Multi-repo pattern (docker/cli → moby/moby). Agent must trace blank stderr output from CLI through to the client library in moby.

---

## Repo Coverage

| Repo | Candidates | LoC |
|------|-----------|-----|
| kubernetes/kubernetes | 6 (#1-#6) | ~3.5M |
| hashicorp/terraform | 3 (#7-#9) | ~500K |
| grafana/grafana | 2 (#10-#11) | ~2M |
| hashicorp/vault | 1 (#12) | ~800K |
| docker/cli + moby/moby | 1 (#13) | ~200K + ~1M |

**Total:** 13 candidates across 5 repos (6 distinct repositories)

## Difficulty Distribution

- **Medium:** 5 (#1, #5, #7, #9, #13)
- **Hard:** 7 (#2, #4, #6, #8, #10, #11, #12)
- **Expert:** 1 (#3)

## Next Steps

- P1.2: Extract ground truth (source file + line, error chain, trigger conditions) for each candidate
- P1.3: Author task TOML files with checkpoint structure
