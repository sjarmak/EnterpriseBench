# Go 1.26 Toolchain Update — Kubernetes Monorepo Refactor Plan

Reference: kubernetes/kubernetes PR #137080 (merged 2026-03-05)
Current version: Go 1.24.0 (patch: 1.24.6)
Target version: Go 1.26.0 (patch: 1.26.x)

---

## 1. Numbered Execution Order

### Phase 1 — Build Infrastructure (Blockers for everything else)

**Step 1 — `.go-version`**
- File: `/workspace/kubernetes/.go-version`
- Change: `1.24.6` → `1.26.x` (patch TBD at release)
- Risk: LOW — single file, consumed by `hack/lib/golang.sh`

**Step 2 — `hack/lib/golang.sh` minimum version gate**
- File: `/workspace/kubernetes/hack/lib/golang.sh` (line ~571)
- Change: `minimum_go_version=go1.24` → `minimum_go_version=go1.26`
- Risk: LOW — guards against accidental old-toolchain builds; must match .go-version

**Step 3 — Cross-compile build image**
- File: `/workspace/kubernetes/build/build-image/cross/VERSION`
- Change: `v1.34.0-go1.24.6-bullseye.0` → `v1.34.0-go1.26.x-bullseye.0` (or newer base)
- Risk: MEDIUM — requires a corresponding upstream `gcr.io/k8s-staging-build-image/kube-cross` image to exist at the new tag; coordinate with `sig-k8s-infra`

---

### Phase 2 — Root Module and Workspace

**Step 4 — Root `go.mod`**
- File: `/workspace/kubernetes/go.mod`
- Changes:
  - Line 9: `go 1.24.0` → `go 1.26.0`
  - Line 11: `godebug default=go1.24` → `godebug default=go1.26`
  - Add/update `toolchain go1.26.x` directive if pinning patch
- Risk: MEDIUM — triggers re-evaluation of all module constraints; may expose new `godebug` defaults

**Step 5 — Root `go.work`**
- File: `/workspace/kubernetes/go.work`
- Changes:
  - Line 1: `go 1.24.0` → `go 1.26.0`
  - Line 2: `godebug default=go1.24` → `godebug default=go1.26`
- Risk: LOW — workspace file mirrors go.mod version

---

### Phase 3 — Staging Repos (Topologically Sorted)

Update each staging repo's `go.mod`: `go X.Y` line and `godebug default=goX.Y`.
Repos in each wave are **independent and can be updated in parallel**.

**Step 6 — Wave 1: Leaf modules (no k8s.io staging dependencies)**
| Repo | Path |
|------|------|
| `apimachinery` | `staging/src/k8s.io/apimachinery/go.mod` |
| `cri-api` | `staging/src/k8s.io/cri-api/go.mod` |
| `externaljwt` | `staging/src/k8s.io/externaljwt/go.mod` |
| `kms` | `staging/src/k8s.io/kms/go.mod` |
| `mount-utils` | `staging/src/k8s.io/mount-utils/go.mod` |

**Step 7 — Wave 2: Depend only on Wave 1**
| Repo | Dependencies |
|------|-------------|
| `api` | apimachinery |
| `code-generator` | apimachinery |

**Step 8 — Wave 3: Depend on Waves 1–2**
| Repo | Dependencies |
|------|-------------|
| `client-go` | api, apimachinery |
| `cluster-bootstrap` | api, apimachinery |
| `csi-translation-lib` | api, apimachinery |

**Step 9 — Wave 4: Depend on Waves 1–3**
| Repo | Dependencies |
|------|-------------|
| `cli-runtime` | api, apimachinery, client-go |
| `component-base` | api, apimachinery, client-go |
| `component-helpers` | api, apimachinery, client-go |

**Step 10 — Wave 5: Depend on Waves 1–4**
| Repo | Dependencies |
|------|-------------|
| `apiserver` | api, apimachinery, client-go, component-base, kms |
| `cri-client` | api, apimachinery, client-go, component-base, cri-api |
| `endpointslice` | api, apimachinery, client-go, component-base |
| `kube-proxy` | apimachinery, component-base |
| `kube-scheduler` | api, apimachinery, client-go, component-base |
| `metrics` | api, apimachinery, client-go, code-generator |

**Step 11 — Wave 6: Depend on Waves 1–5**
| Repo | Dependencies |
|------|-------------|
| `controller-manager` | api, apimachinery, apiserver, client-go, component-base |
| `kube-aggregator` | api, apimachinery, apiserver, client-go, code-generator, component-base |
| `kubelet` | api, apimachinery, apiserver, client-go, component-base, cri-api |
| `pod-security-admission` | api, apimachinery, apiserver, client-go, component-base |
| `sample-apiserver` | apimachinery, apiserver, client-go, code-generator, component-base |

**Step 12 — Wave 7: Depend on Waves 1–6**
| Repo | Dependencies |
|------|-------------|
| `apiextensions-apiserver` | api, apimachinery, apiserver, client-go, code-generator, component-base, kms |
| `cloud-provider` | api, apimachinery, apiserver, client-go, component-base, component-helpers, controller-manager |
| `kubectl` | api, apimachinery, cli-runtime, client-go, component-base, component-helpers, metrics |
| `sample-cli-plugin` | cli-runtime, client-go |
| `sample-controller` | api, apimachinery, client-go, code-generator |

**Step 13 — Wave 8: Deepest transitive dependencies**
| Repo | Dependencies |
|------|-------------|
| `dynamic-resource-allocation` | api, apimachinery, apiserver, client-go, component-helpers, kubelet |
| `kube-controller-manager` | apimachinery, cloud-provider, controller-manager |

---

### Phase 4 — Hack Tools Workspaces

**Step 14 — `hack/tools/go.mod` and `hack/tools/go.work`**
- Files: `/workspace/kubernetes/hack/tools/go.mod`, `hack/tools/go.work`
- Change: `go 1.24.0` → `go 1.26.0`
- Risk: LOW — isolated workspace for build tools (golangci-lint, etc.)

**Step 15 — `hack/tools/golangci-lint/go.mod` and its `go.work`**
- Files: `/workspace/kubernetes/hack/tools/golangci-lint/go.mod`, `go.work`
- Change: `go 1.24.0` → `go 1.26.0`
- Risk: LOW-MEDIUM — golangci-lint must support Go 1.26; verify linter compatibility

---

### Phase 5 — Vendor and Dependency Update

**Step 16 — Re-vendor**
- Run: `hack/update-vendor.sh`
- Effect: Regenerates `vendor/` and `go.sum` / `go.work.sum` for all modules
- Risk: HIGH — most time-consuming step; any dependency that pins a maximum Go version will surface here

**Step 17 — Re-pin dependencies (if needed)**
- Run: `hack/pin-dependency.sh` for any deps with version constraints
- Risk: MEDIUM — external dependencies may need upgrades to support Go 1.26

---

### Phase 6 — Verification

**Step 18 — Format and lint checks**
- Run: `hack/verify-gofmt.sh`, `hack/verify-golangci-lint.sh`
- Risk: LOW-MEDIUM — Go 1.26 gofmt may reformat some files; new lint rules may fire

**Step 19 — Build verification**
- Run: `make all` or `make quick-release`
- Risk: MEDIUM — compiler behavior changes in Go 1.26 may break builds (new `godebug` defaults, removed deprecated APIs)

**Step 20 — Unit and integration tests**
- Run: `make test`, `make test-integration`
- Risk: MEDIUM — runtime behavior changes under new `godebug default=go1.26`

**Step 21 — E2E tests**
- Run: `hack/ginkgo-e2e.sh` (builds `test/e2e/e2e.test` and `test/conformance/image/go-runner`)
- Risk: MEDIUM — conformance image Go version is implicit from host toolchain

---

## 2. Staging Repo Dependency Graph

```
(no k8s.io deps)
  apimachinery   cri-api   externaljwt   kms   mount-utils
       │               │
       ▼               │
      api   code-generator
       │
       ▼
   client-go   cluster-bootstrap   csi-translation-lib
       │
       ▼
  cli-runtime   component-base   component-helpers
                     │
                     ▼
 apiserver─────────────────────────┐
 cri-client (also ←cri-api)       │
 endpointslice                     │
 kube-proxy                        │
 kube-scheduler                    │
 metrics (also ←code-generator)   │
                     │             │
                     ▼             │
  controller-manager               │
  kube-aggregator (←code-gen)     │
  kubelet (←cri-api)              │
  pod-security-admission           │
  sample-apiserver (←code-gen)    │
                     │             │
                     ▼             ▼
  apiextensions-apiserver (←kms, code-gen)
  cloud-provider (←controller-manager, component-helpers)
  kubectl (←cli-runtime, metrics, component-helpers)
  sample-cli-plugin (←cli-runtime)
  sample-controller (←code-gen)
                     │
                     ▼
  dynamic-resource-allocation (←kubelet, component-helpers)
  kube-controller-manager (←cloud-provider, controller-manager)
```

**Dependency levels summary:**
| Level | Repos |
|-------|-------|
| L0 (leaves) | apimachinery, cri-api, externaljwt, kms, mount-utils |
| L1 | api, code-generator |
| L2 | client-go, cluster-bootstrap, csi-translation-lib |
| L3 | cli-runtime, component-base, component-helpers |
| L4 | apiserver, cri-client, endpointslice, kube-proxy, kube-scheduler, metrics |
| L5 | controller-manager, kube-aggregator, kubelet, pod-security-admission, sample-apiserver |
| L6 | apiextensions-apiserver, cloud-provider, kubectl, sample-cli-plugin, sample-controller |
| L7 | dynamic-resource-allocation, kube-controller-manager |

---

## 3. Parallelization Annotations

| Wave | Steps | Parallelizable? | Notes |
|------|-------|-----------------|-------|
| Phase 1 | Steps 1–3 | Steps 1–2 parallel; Step 3 independent | Step 3 needs external image availability |
| Phase 2 | Steps 4–5 | Parallel | go.mod and go.work are independent files |
| Phase 3, Wave 1 | Step 6 (5 repos) | **Fully parallel** | No inter-dependencies |
| Phase 3, Wave 2 | Step 7 (2 repos) | **Fully parallel** | Only need Wave 1 done |
| Phase 3, Wave 3 | Step 8 (3 repos) | **Fully parallel** | Only need Waves 1–2 done |
| Phase 3, Wave 4 | Step 9 (3 repos) | **Fully parallel** | Only need Waves 1–3 done |
| Phase 3, Wave 5 | Step 10 (6 repos) | **Fully parallel** | Only need Waves 1–4 done |
| Phase 3, Wave 6 | Step 11 (5 repos) | **Fully parallel** | Only need Waves 1–5 done |
| Phase 3, Wave 7 | Step 12 (5 repos) | **Fully parallel** | Only need Waves 1–6 done |
| Phase 3, Wave 8 | Step 13 (2 repos) | **Fully parallel** | Only need Waves 1–7 done |
| Phase 4 | Steps 14–15 | Parallel with each other; serial after Phase 3 | |
| Phase 5 | Steps 16–17 | Step 17 after Step 16 | Single-threaded vendor update |
| Phase 6 | Steps 18–21 | Steps 18–19 parallel; 20 after 19; 21 last | |

**Estimated critical path:** Phase 1 → Phase 2 → Phase 3 (8 waves sequential) → Phase 4 → Phase 5 → Phase 6

**Maximum parallelism:** Phase 3 Wave 1 can fan out to 5 concurrent PRs/jobs; subsequent waves are gated by prior waves completing.

> Note: In the actual Kubernetes release process, staging repo go.mod files are auto-generated and updated together via `hack/update-vendor.sh` and associated scripts rather than manually per-repo. The wave ordering matters for script correctness and CI dependency checks.

---

## 4. Risk Assessment Per Step

| Step | Component | Risk Level | Rationale | Mitigation |
|------|-----------|------------|-----------|------------|
| 1 | `.go-version` | LOW | Single file, well-understood | Verify patch version exists for download |
| 2 | `golang.sh` min version | LOW | Numeric string change only | Run `make verify` immediately after |
| 3 | Cross build image `VERSION` | MEDIUM | External image must be published by `sig-k8s-infra` | Coordinate with infra team; do not merge before image exists |
| 4 | Root `go.mod` | MEDIUM | Triggers godebug behavior changes; may expose new stdlib defaults | Review Go 1.26 release notes for godebug changes |
| 5 | Root `go.work` | LOW | Mirrors go.mod; no independent behavior | Auto-validated by `go work sync` |
| 6–13 | Staging repo `go.mod` files | LOW per repo | Uniform version bump; replace directives unchanged | Automated via `hack/update-vendor.sh` |
| 14–15 | `hack/tools` workspaces | LOW-MEDIUM | golangci-lint must support Go 1.26 | Pin compatible golangci-lint version before updating |
| 16 | Re-vendor (`update-vendor.sh`) | HIGH | Any of the 225 external dependencies may not support Go 1.26 yet; go.sum invalidation | Run in CI with full dependency audit; expect several dependency bumps |
| 17 | Re-pin deps | MEDIUM | Version constraint solving may pull in breaking changes | Review changelogs of bumped external deps |
| 18 | Lint/format | LOW-MEDIUM | gofmt behavior changes may produce large diffs; new lint rules | Run `hack/verify-gofmt.sh` early; add `// nolint` sparingly |
| 19 | Build verification | MEDIUM | Removed deprecated APIs in Go 1.26 stdlib; changed compiler errors | Audit use of deprecated packages (`io/ioutil`, etc.) |
| 20 | Unit/integration tests | MEDIUM | Runtime `godebug` changes may alter behavior | Run full test suite; watch for flaky tests tied to timing/crypto |
| 21 | E2E tests | MEDIUM | Conformance image and go-runner pick up toolchain implicitly | Run full conformance suite; coordinate with SIG-Testing |

**Overall risk: MEDIUM** — Go minor version bumps in Kubernetes are well-rehearsed (done each release cycle), but Go 1.26 may introduce new `godebug` defaults or stdlib changes that require code fixes beyond mechanical version string updates. The highest single-point risk is the external build image availability (Step 3) and vendor re-solve (Step 16).
