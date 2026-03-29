# API Contract Boundary Analysis — Mined Candidates

Task type: `api-contract-*`
Suite mapping: `dependency_management` (primary)
Mined: 2026-03-28

---

## grpc/grpc-go → etcd-io/etcd — 4 Candidates

### AC-1: Metadata Context Separation (HIGH confidence)

- **Producer repo:** `grpc/grpc-go`
- **Breaking change PR:** grpc/grpc-go#1157 — "Separate incoming and outgoing metadata in context"
- **Merged:** 2017-04-07
- **API contract type:** Go interface (metadata API)
- **What broke:** Prior to this change, gRPC metadata was shared in a single context. After, incoming and outgoing metadata were separated, requiring explicit copying. Consumers using `metadata.FromContext` and `metadata.NewContext` broke — these functions were split into `FromIncomingContext`/`NewOutgoingContext`.
- **Consumer fix PRs:**
  - etcd-io/etcd#7888 (issue tracking the breakage)
  - etcd-io/etcd#8160 — "vendor: upgrade grpc-go to 1.4.2" (included metadata API fixes)
- **Consumer impact:** etcd auth package and other gRPC interceptors broke because outgoing RPCs silently stopped forwarding metadata.
- **Files changed (producer):** 9
- **Difficulty:** medium
- **Notes:** Clean single-API breaking change with clear consumer fix. The metadata separation affected any gRPC middleware/interceptor that forwarded metadata between incoming and outgoing contexts. Good calibration task.

### AC-2: Balancer/Resolver Type Alias Removal (HIGH confidence)

- **Producer repo:** `grpc/grpc-go`
- **Breaking change PR:** grpc/grpc-go#3309 — "balancer/resolver: remove temporary backward-compatibility type aliases"
- **Merged:** 2020-01-22
- **API contract type:** Go interface (balancer/resolver API)
- **What broke:** Compile error. grpc-go removed backward-compatibility type aliases for balancer and resolver interfaces that had been moved to new packages. Any consumer directly referencing the old type paths got compile failures.
- **Consumer fix PRs:**
  - etcd-io/etcd#11564 — "clientv3: Fix grpc-go(v1.27.0) incompatible changes to balancer/resolver"
  - etcd-io/etcd#12671 — "clientv3: Replace balancer with upstream grpc solution" (larger follow-up)
- **Related upstream issue:** grpc/grpc-go#3180 — "Notice: Upcoming Experimental Balancer/Resolver API Changes"
- **Consumer impact:** etcd clientv3 could not compile against grpc-go v1.27.0+. Users pulling etcd via `go mod` got build failures.
- **Files changed (producer):** 2; (consumer fix): 3 then 21
- **Difficulty:** hard
- **Notes:** Excellent multi-phase candidate. Initial quick fix (PR 11564, 3 files) just updated type references, but the deeper fix (PR 12671, 21 files) replaced etcd's entire custom balancer with upstream grpc infrastructure. Shows how a small API removal cascades into architectural changes in consumers.

### AC-3: Transport Package Internalization (HIGH confidence)

- **Producer repo:** `grpc/grpc-go`
- **Breaking change PR:** grpc/grpc-go#2212 — "transport: move to internal to make room for new, public transport API"
- **Merged:** 2018-07-11
- **API contract type:** Go package (transport API)
- **What broke:** Compile error. The entire `google.golang.org/grpc/transport` package was moved to `google.golang.org/grpc/internal/transport`, making it unexportable. Any consumer importing the transport package directly broke.
- **Consumer fix PRs:**
  - etcd-io/etcd — vendored grpc-go upgrade commits (etcd-io/etcd#8160 era)
  - kubernetes/kubernetes#57160 — "Version bump to etcd v3.2.11, grpc v1.7.5" (381 files, included grpc API adaptations)
- **Consumer impact:** Both etcd and kubernetes had to adapt. The k8s PR alone changed 381 files due to cascading vendor updates.
- **Files changed (producer):** 27
- **Difficulty:** expert
- **Notes:** Three-repo chain: grpc-go → etcd → kubernetes. The k8s PR explicitly references "Apply grpc API changes in 1.6.0 and 1.7.0 release notes" showing the cross-repo tracing required. The 381-file consumer change makes this an expert-level tracing task.

### AC-4: balancer.ClientConn Embedding Requirement (HIGH confidence)

- **Producer repo:** `grpc/grpc-go`
- **Breaking change PR:** grpc/grpc-go#8026 — "balancer: Enforce embedding requirement for balancer.ClientConn"
- **Merged:** 2025-02-06
- **API contract type:** Go interface (balancer.ClientConn)
- **What broke:** Compile error. All implementations of `balancer.ClientConn` must now embed a delegate implementation. An internal method was added to the interface, breaking any direct implementation.
- **Consumer fix PRs:**
  - etcd-io/etcd#19622 (closed/blocked — grpc 1.71 bump PR that couldn't merge due to this and related API changes)
  - etcd-io/etcd#15145 (tracking issue for removing dependency on grpc-go experimental APIs)
  - etcd-io/etcd#19780 and related PRs (mitigations)
- **Consumer impact:** etcd could not upgrade to grpc-go v1.71.0 because its custom balancer/resolver implementations needed the new embedding pattern.
- **Files changed (producer):** 7
- **Difficulty:** hard
- **Notes:** Active/recent breaking change (2025). Shows the ongoing tension between grpc-go's API evolution and etcd's deep coupling to experimental APIs. The etcd issue #15145 documents the full scope of experimental API dependencies that need removal.

---

## protocolbuffers/protobuf → grpc/grpc-go → consumers — 3 Candidates

### AC-5: Protobuf v2 API Migration (github.com/golang/protobuf → google.golang.org/protobuf) (HIGH confidence)

- **Producer repo:** `protocolbuffers/protobuf` (Go module: `google.golang.org/protobuf`)
- **Breaking change:** Migration from `github.com/golang/protobuf` to `google.golang.org/protobuf/proto` — new API surface with different type system (MessageV1 vs MessageV2)
- **Intermediate consumer PR:** grpc/grpc-go#6919 — "deps: move from github.com/golang/protobuf to google.golang.org/protobuf/proto" (68 files, merged 2024-01-30)
- **Breakage fix PR:** grpc/grpc-go#7724 — "status: Fix status incompatibility introduced by #6919" (21 files, merged 2024-10-22)
- **API contract type:** Go interface (protobuf message types, status.Details() return types)
- **What broke:** Runtime behavior change. `Status.Details()` started returning `MessageV2` types instead of `MessageV1` types after the migration. Users with code generated from protoc-gen-go < v1.4 (pre-2020) got type assertion failures.
- **Consumer impact chain:** protobuf API change → grpc-go migration → grpc-go status.Details() behavior change → all grpc-go consumers using error details
- **Difficulty:** expert
- **Notes:** Three-layer propagation: protobuf type system → grpc-go status package → all consumers. The subtlety is that this was a *runtime* behavior change (not compile error), making it harder to detect. Took 9 months between grpc-go migration (Jan 2024) and the fix (Oct 2024).

### AC-6: Protobuf FieldDescriptor::label() Removal (HIGH confidence)

- **Producer repo:** `protocolbuffers/protobuf`
- **Breaking change commit:** protocolbuffers/protobuf@b76faa9 — "Breaking Change: Remove deprecated FieldDescriptor::label() in OSS" (2025-12-16)
- **API contract type:** C++ API (protobuf descriptor interface)
- **What broke:** Compile error. `FieldDescriptor::label()` removed; consumers must use `is_repeated()` or `is_required()` instead.
- **Consumer fix PRs:**
  - envoyproxy/envoy#37066 — "feat: prepare for breaking change in Protobuf C++ API" (17 files, merged 2024-11-14)
  - grpc/grpc#37911 — export/adaptation PR (merged 2024-11-01)
- **Pre-announced:** https://protobuf.dev/news/2025-09-19/#cpp-remove-apis
- **Consumer impact:** Both Envoy (C++) and gRPC C++ core had to adapt. Envoy's PR changed 17 files across its codebase to handle the `absl::string_view` return type change from `Descriptor::name()` and related methods.
- **Difficulty:** hard
- **Notes:** Cross-language (C++) but within the CNCF proto ecosystem. Shows how a protobuf API change propagates to both Envoy and gRPC C++ simultaneously.

### AC-7: Protobuf Major Version Bump (C++/Python/PHP) (MEDIUM confidence)

- **Producer repo:** `protocolbuffers/protobuf`
- **Breaking change commit:** protocolbuffers/protobuf@789c7c5 — "Breaking change: Update major version numbers for C++ Python and PHP" (2026-01-19)
- **API contract type:** Package versioning / ABI (major version bump)
- **What broke:** Build system / dependency resolution errors. Major version number changes in C++, Python, and PHP protobuf libraries required coordinated updates across all consumers' build configurations.
- **Consumer fix PRs:**
  - envoyproxy/envoy#43225 — bump protobuf in Python tools (merged 2026-01-30)
  - envoyproxy/envoy#43670 — bump protobuf from 6.x to 7.x (closed/blocked, 2026-02-27)
  - Multiple `protocolbuffers/protobuf` self-fixes: protocolbuffers/protobuf@17983b2 (alias to undo unannounced breaking change), protocolbuffers/protobuf@80167003 (fix for `upb_proto_reflection_library`)
- **Difficulty:** medium
- **Notes:** Broad impact but relatively mechanical — mainly build file and dependency version updates. The self-fix commits in protobuf itself show that even the producer had to patch breakages from the version bump.

---

## envoyproxy/envoy → istio/istio — 3 Candidates

### AC-8: Envoy xDS v2 API Deprecation and Removal (HIGH confidence)

- **Producer repo:** `envoyproxy/envoy` (xDS proto definitions)
- **Breaking change PRs:**
  - envoyproxy/envoy#14223 — "config: v2 transport API fatal-by-default" (114 files, merged 2020-12-07)
  - envoyproxy/envoy#15481 — "config: disable v2 with no supported override" (merged 2021-03-14)
- **Intermediate repo:** `envoyproxy/go-control-plane`
  - envoyproxy/go-control-plane#415 — "Remove V2" (78 files, merged 2021-04-07)
- **API contract type:** Protobuf (xDS v2 → v3 proto definitions)
- **What broke:** Runtime error (fatal). Envoy began rejecting v2 xDS transport API requests by default, then removed override capability entirely. All control planes had to migrate to v3.
- **Consumer fix PRs:**
  - istio/istio#22919 — "Move Cluster and Endpoints to xds V3" (48 files, merged 2020-05-10)
  - istio/istio#23962 — "Move RDS/LDS to XDS v3" (107 files, merged 2020-05-22)
  - istio/istio#24588 — "Use xds v3 in more places" (merged)
- **Consumer impact:** Istio had to rewrite its entire xDS generation layer across 150+ files to emit v3 proto types instead of v2.
- **Difficulty:** expert
- **Notes:** Three-repo chain: envoy (proto definitions) → go-control-plane (Go bindings) → istio (control plane). The v2→v3 migration was the largest API contract change in the CNCF service mesh ecosystem. Istio's migration spanned multiple PRs totaling 155+ files.

### AC-9: Envoy go-control-plane Module Split (HIGH confidence)

- **Producer repo:** `envoyproxy/go-control-plane`
- **Breaking change PR:** envoyproxy/go-control-plane#714 — "Support multi-module releases in go-control-plane" (32 files, merged 2024-12-23)
- **API contract type:** Go module path (module restructure)
- **What broke:** Dependency resolution error. The module split into submodules (`envoy/`, `contrib/`) broke `go get -u` for consumers due to Go module proxy resolution issues.
- **Consumer fix PRs:**
  - envoyproxy/go-control-plane#1075 — "Add imports of previous root package in new subpackages" (6 files, merged 2025-01-03)
  - istio/istio — automated go-control-plane bump PRs (weekly cadence, e.g., istio/istio#58764, istio/istio#58825)
  - grpc/grpc-go#8067 — "deps: bump envoyproxy/go-control-plane/envoy and synchronize go.mods" (merged 2025-08-06)
- **Related issue:** envoyproxy/go-control-plane#1074 — "v0.13.2 broke dependency upgrades for cloud.google.com/go/storage"
- **Consumer impact:** Broke dependency upgrades for google-cloud-go, istio, grpc-go, and potentially any Go project depending on go-control-plane.
- **Difficulty:** hard
- **Notes:** Module-level breaking change (not proto/API level). The fix required adding backward-compatible import shims. Shows a different class of API contract breakage — Go module path changes. Consumer workaround was `go mod edit --exclude=github.com/envoyproxy/go-control-plane@v0.13.2`.

### AC-10: Envoy v1.37 Default HTTP Reset Code Change (MEDIUM confidence)

- **Producer repo:** `envoyproxy/envoy`
- **Breaking change:** v1.37.0 release (2026-01-13) — changed default HTTP reset code from `NO_ERROR` to `INTERNAL_ERROR` and changed reset behavior to ignore upstream protocol errors by default.
- **Release PR:** envoyproxy/envoy@6d9bb7d — v1.37.0 release notes documenting breaking changes
- **API contract type:** Protocol behavior (HTTP/2 reset semantics)
- **What broke:** Runtime behavior change. HTTP/2 connections started receiving `INTERNAL_ERROR` reset codes instead of `NO_ERROR`, which some clients interpret differently.
- **Consumer fix PRs:**
  - istio/istio#58764 — "[release-1.29] bump go-control-plane for 1.37" (merged 2026-01-13)
  - istio/istio#58666 — "fix global downstream max connections behaviour" (XXL, merged 2026-01-26, related to Envoy 1.37 behavioral changes)
- **Difficulty:** medium
- **Notes:** Runtime behavior change (not compile error) makes this harder to detect via static analysis. The agent must trace HTTP/2 reset handling through Envoy → go-control-plane → istio to understand the full impact.

---

## google/cel-go → grpc/grpc-go — 1 Candidate

### AC-11: cel-go Program Interface Breaking Change (MEDIUM confidence)

- **Producer repo:** `google/cel-go`
- **Breaking change:** cel-go v0.10.1 added a new method to `cel.Program` interface
- **API contract type:** Go interface (cel.Program)
- **What broke:** Compile error. The new method on `cel.Program` broke existing mock implementations in grpc-go's authorization module.
- **Consumer fix PR:**
  - grpc/grpc-go#5243 — "security/authorization: upgrade cel-v0.10.1 and fix breaking API change" (3 files, merged 2022-03-15)
- **Consumer impact:** grpc-go's authorization module mock tests failed to compile.
- **Difficulty:** medium
- **Notes:** Small but clean example of interface evolution breaking consumer mocks. Good calibration candidate. The fix was straightforward (3 files) but requires tracing the cel-go → grpc-go dependency.

---

## protocolbuffers/protobuf → Bazel consumers — 1 Candidate

### AC-12: Protobuf Bazel proto_toolchain Starlark Migration (MEDIUM confidence)

- **Producer repo:** `protocolbuffers/protobuf`
- **Breaking change commit:** protocolbuffers/protobuf@f9d8a56 — "Only respect the Starlark versions of --proto_toolchain_for*" (2026-02-24)
- **Also:** protocolbuffers/protobuf@f9f32d2 — "Breaking Change: Change @protobuf//bazel/flags:prefer_prebuilt_proto flag to True" (2026-02-18)
- **API contract type:** Bazel build rules (Starlark API)
- **What broke:** Build failure. The legacy CLI flags `--proto_toolchain_for_*` were replaced by Starlark-only versions. Any project using the old flags in `.bazelrc` or CI scripts got build failures.
- **Consumer fix PRs:** Pending/scattered across Bazel-based protobuf consumers (envoy, grpc, buf)
- **Pre-announced:** https://protobuf.dev/news/2025-09-19/
- **Difficulty:** hard
- **Notes:** Build-system-level breaking change. Impact spans any project using Bazel-based protobuf compilation (envoy, grpc, kubernetes build tooling). Different from code-level API changes — requires tracing through Bazel BUILD/WORKSPACE files rather than source code.

---

## Summary

| # | Candidate | Producer | Consumer(s) | Contract Type | Breakage Type | Difficulty |
|---|-----------|----------|-------------|---------------|---------------|------------|
| AC-1 | Metadata context separation | grpc-go | etcd | Go API | Compile + runtime | medium |
| AC-2 | Balancer/resolver alias removal | grpc-go | etcd | Go interface | Compile error | hard |
| AC-3 | Transport internalization | grpc-go | etcd, k8s | Go package | Compile error | expert |
| AC-4 | ClientConn embedding requirement | grpc-go | etcd | Go interface | Compile error | hard |
| AC-5 | Protobuf v2 API migration | protobuf | grpc-go, all grpc consumers | Go types | Runtime behavior | expert |
| AC-6 | FieldDescriptor::label() removal | protobuf | envoy, grpc C++ | C++ API | Compile error | hard |
| AC-7 | Protobuf major version bump | protobuf | envoy, grpc | Versioning/ABI | Build error | medium |
| AC-8 | xDS v2 deprecation/removal | envoy | go-control-plane, istio | Protobuf | Runtime fatal | expert |
| AC-9 | go-control-plane module split | go-control-plane | istio, grpc-go, google-cloud-go | Go module | Dep resolution | hard |
| AC-10 | HTTP reset code default change | envoy | istio | Protocol behavior | Runtime behavior | medium |
| AC-11 | cel.Program interface change | cel-go | grpc-go | Go interface | Compile error | medium |
| AC-12 | Bazel proto_toolchain migration | protobuf | envoy, grpc, buf consumers | Bazel rules | Build failure | hard |

### Difficulty Distribution
- **Medium:** AC-1, AC-7, AC-10, AC-11 (4 = 33%)
- **Hard:** AC-2, AC-4, AC-6, AC-9, AC-12 (5 = 42%)
- **Expert:** AC-3, AC-5, AC-8 (3 = 25%)

### Producer Repo Coverage (5 repos)
- `grpc/grpc-go` — 4 candidates (AC-1 through AC-4)
- `protocolbuffers/protobuf` — 3 candidates (AC-5, AC-6, AC-7, AC-12)
- `envoyproxy/envoy` — 2 candidates (AC-8, AC-10)
- `envoyproxy/go-control-plane` — 1 candidate (AC-9)
- `google/cel-go` — 1 candidate (AC-11)
