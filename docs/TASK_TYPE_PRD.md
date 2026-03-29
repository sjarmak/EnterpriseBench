# EnterpriseBench: Task Type PRD

**Status:** Phase 1 Ready
**Date:** 2026-03-29
**Source:** Convergence debate (3 advocates, 2 rounds) on 30 brainstorm ideas
**Inputs:** PRD.md, CONVERGENCE_REPORT.md, CodeScaleBench analysis

## Executive Summary

This PRD defines the **10 task types** selected for EnterpriseBench through a structured debate optimizing for Sourcegraph MCP signal strength, enterprise workflow realism, and implementation feasibility. The suite targets 79 tasks (range: 71-97) across all 7 PRD workflow suites, with 54 agent-executable implementation tasks organized in 6 phases.

### Selected Task Types (Priority Order)

| # | Task Type | MCP Signal | Tasks | PRD Suite | Phase |
|---|-----------|-----------|-------|-----------|-------|
| 1 | API Contract Boundary Analysis | ★★★★★ | 8-10 | dependency_management | Batch 2 |
| 2 | Multi-Repo Refactor Orchestration | ★★★★★ | 5-8 | technical_debt | Batch 3 |
| 3 | Dependency Graph Traversal Races | ★★★★½ | 10-12 | dependency_management | Batch 2 |
| 4 | Monorepo Package Boundary Referee | ★★★★½ | 8-10 | feature_delivery | Batch 1 |
| 5 | DB Schema Evolution Impact Analysis | ★★★★ | 8-10 | feature_delivery | Batch 2 |
| 6 | Error Message Provenance Tracing | ★★★★ | 10-12 | customer_escalation | Batch 1 |
| 7 | Support Code Mapping | ★★★½ | 10-15 | customer_escalation | Batch 1 |
| 8 | Dead Code / Feature Flag Necropsy | ★★★★ | 3-5 | technical_debt | Batch 3 |
| 9 | Incident Investigation (simplified) | ★★★ | 3-5 | incident_response | Batch 4 (stretch) |
| 10 | Configuration Drift Forensics | ★★★ | 3-5 | platform_engineering | Batch 4 (stretch) |

### Key Decisions from Debate

- **5 unanimous locks** (#1, #5, #12, #23, #25) — all three advocates selected these
- **#18 reframed** from "Support Triage" to "Support Code Mapping" — navigation-weighted scoring
- **#22 scoped** to deterministic topological ordering (no fuzzy plan quality)
- **#14 FFI Bridge rejected** 2-to-1 — niche despite strong MCP signal
- **#30 Observability dropped** — subjective verification problem
- **Conditional slot:** #10 Permission Audit OR #24 Adversarial Sabotage (mining-dependent)

---

# Task Type Definitions and Architecture

This section defines the 10 task types selected through the structured convergence debate (see `convergence_debate_report.md`). Each type is designed to produce measurable signal on codebase understanding and context gathering, with Sourcegraph MCP as a first-class showcase tool.

---

## 1. API Contract Boundary Analysis

**ID prefix:** `api-contract-*`
**MCP Signal:** ★★★★★ | **Priority:** 1 | **Task count target:** 8–10

### Description

Given a proposed or actual breaking change to a protobuf/OpenAPI/GraphQL schema, the agent must identify all downstream consumers that break across multiple repositories. The agent traces API surface through proto definitions, generated code stubs, client libraries, and integration tests to produce a complete impact assessment.

### MCP Signal Mechanism

Sourcegraph MCP provides **cross-repo reference search** and **symbol navigation** that follow generated code bindings across repository boundaries. A proto field rename in `grpc-go` generates Go stubs consumed by `etcd`, `kubernetes`, and `istio` — Sourcegraph resolves these cross-repo references structurally. Grep/find fails because: (1) generated code uses transformed names (e.g., `snake_case` proto → `CamelCase` Go), (2) consumer repos import generated packages under different module paths, (3) transitive consumers re-export types under new names. Without semantic cross-repo indexing, an agent must guess import paths and hope for string matches.

### Target OSS Codebases

| Repo | Rationale |
|------|-----------|
| `grpc/grpc-go` (v1.59.0) | Core gRPC Go implementation, proto-generated API surface |
| `etcd-io/etcd` (v3.5.10) | Heavy grpc-go consumer with custom wrappers |
| `kubernetes/kubernetes` (v1.29.0) | Massive grpc consumer, 2M+ LoC, deep import chains |
| `istio/istio` (v1.20.0) | Multi-layer proto contracts (Envoy xDS + Istio APIs) |
| `envoyproxy/envoy` (v1.28.0) | C++ with proto definitions consumed by Go/Python control planes |
| `bufbuild/buf` (v1.28.0) | Proto toolchain — tests schema evolution tooling itself |

Chains: `grpc-go` → `etcd` (direct), `envoy` xDS protos → `istio` control plane → `kubernetes` API server.

### Multi-repo Pattern

**Propagate** — change in API definition repo requires coordinated changes in 2–4 consumer repos.

### Artifact Types

- **Required:** `answer` (list of affected files/symbols per repo with breakage classification)
- **Optional:** `migration_guide` (step-by-step consumer update plan)

### Verification Approach

**Plugin:** `eb_verify.plugins.file_set_match` + `eb_verify.plugins.symbol_match`

- **Deterministic:** Compare agent's affected-file list against ground truth file set. Precision/recall scoring on `{repo, file_path, symbol}` tuples.
- **Deterministic:** Verify that every claimed breaking consumer actually imports the changed API (AST-level import graph check).
- **LLM curator (Tier 2):** Validate breakage classification reasoning (compile error vs runtime behavior change vs deprecation warning).

### Ground Truth Source

Real breaking-change PRs in CNCF ecosystem. Sources:
- gRPC release notes with "BREAKING:" labels
- etcd/kubernetes CHANGELOG entries referencing upstream API changes
- GitHub issues cross-linked between repos during API migrations
- `buf breaking` output on historical proto diffs

### Checkpoint Structure

| # | Checkpoint | Weight | Verifier |
|---|-----------|--------|----------|
| 1 | Identify the breaking change in the source proto/API definition | 0.15 | `check_source_identification.sh` — exact file + field match |
| 2 | Find all directly affected consumers (first-hop repos) | 0.35 | `check_direct_consumers.sh` — file-set precision/recall ≥ 0.8 |
| 3 | Trace transitive impact through generated code / re-exports | 0.30 | `check_transitive_impact.sh` — symbol-level match |
| 4 | Classify breakage severity per consumer (compile error / runtime / deprecation) | 0.20 | `check_classification.sh` — category match against GT labels |

### Difficulty Distribution

- 20% medium (single proto field rename, 2 repos)
- 50% hard (multi-field change with generated code, 3 repos)
- 30% expert (cross-language proto change affecting Go + Python + TypeScript consumers, 4–5 repos)

### PRD Suite Mapping

- **Primary:** `dependency_management`
- **Secondary:** `feature_delivery`

---

## 2. Multi-Repo Refactor Orchestration

**ID prefix:** `refactor-orch-*`
**MCP Signal:** ★★★★★ | **Priority:** 2 | **Task count target:** 5–8

### Description

Given multiple repositories at a pre-refactor state, the agent must produce a topologically sorted execution plan: which repos change first, what ordering avoids broken intermediate states, and which changes can be parallelized. The agent must understand cross-repo dependency constraints to plan safe, incremental migration.

### MCP Signal Mechanism

Sourcegraph's **cross-repo dependency graph** and **find references** reveal the true dependency topology that determines safe ordering. Grep/find fails because: (1) dependency relationships are encoded in heterogeneous manifest files (go.mod, package.json, pom.xml) with version range semantics, (2) transitive dependencies create ordering constraints invisible to text search, (3) some repos consume others via generated code or vendored copies that don't appear in manifest files. Sourcegraph resolves "who actually imports what at which version" across the entire corpus.

### Target OSS Codebases

| Repo | Rationale |
|------|-----------|
| `grpc/grpc-go` → `etcd-io/etcd` → `kubernetes/kubernetes` | 3-deep Go dependency chain with real historical refactors |
| `protocolbuffers/protobuf` → `grpc/grpc-java` → `google/guava` consumers | Java serialization chain with version coupling |
| `babel/babel` monorepo packages (internal refactors) | Internal package dependency ordering within a monorepo |
| `vercel/next.js` → `vercel/turbo` → `vercel/turborepo` | Build toolchain dependency chain |

### Multi-repo Pattern

**Orchestrate** — coordinated build/deploy/test across repos in dependency order.

### Artifact Types

- **Required:** `answer` (ordered list of repos + changes, with parallelization annotations)
- **Optional:** `migration_guide` (detailed step-by-step plan)

### Verification Approach

**Plugin:** `eb_verify.plugins.topological_order`

- **Deterministic:** Validate topological correctness — no repo is modified before its dependencies are updated. Binary pass/fail per ordering constraint.
- **Deterministic:** Verify that the plan covers all repos that actually need changes (completeness check against GT repo set).
- **Deterministic:** Check that claimed parallelizable steps have no mutual dependency (DAG validation).

No LLM judge needed — ordering correctness is fully deterministic.

### Ground Truth Source

Actual chronological PR merge order from real multi-repo refactors:
- gRPC version bump cascades (grpc-go release → etcd update → k8s vendor bump)
- Protobuf major version migrations across CNCF
- Babel plugin API changes requiring coordinated package updates
- GitHub PR timestamps + merge order provide exact sequencing

### Checkpoint Structure

| # | Checkpoint | Weight | Verifier |
|---|-----------|--------|----------|
| 1 | Identify all repos requiring changes | 0.25 | `check_repo_set.sh` — set equality against GT |
| 2 | Produce valid topological ordering (no broken intermediate states) | 0.45 | `check_topo_order.sh` — DAG constraint validation |
| 3 | Identify parallelizable steps correctly | 0.30 | `check_parallelism.sh` — verify independence claims |

### Difficulty Distribution

- 20% medium (2 repos, linear dependency chain)
- 50% hard (3 repos, diamond dependency with ordering constraint)
- 30% expert (4–5 repos, cross-language with vendored copies)

### PRD Suite Mapping

- **Primary:** `technical_debt`
- **Secondary:** `dependency_management`

---

## 3. Dependency Graph Traversal Races

**ID prefix:** `dep-graph-*`
**MCP Signal:** ★★★★½ | **Priority:** 3 | **Task count target:** 10–12

### Description

Given a CVE injected at a leaf dependency, the agent must trace the blast radius through the full transitive dependency graph to identify all affected consumers. Scoring is graph coverage — what percentage of the actual affected path did the agent discover? Pure codebase traversal, no code generation.

### MCP Signal Mechanism

Sourcegraph's **dependency graph indexing** and **cross-repo symbol search** traverse package manifests (go.mod, package.json, requirements.txt, pom.xml) and lock files to resolve transitive dependency trees. Grep/find fails because: (1) transitive dependencies don't appear in a repo's own manifest — they're pulled in by intermediaries, (2) version range resolution (semver, Maven ranges, pip constraints) determines whether a vulnerable version is actually reachable, (3) optional/platform-specific dependencies create conditional paths invisible to text search, (4) vendored or forked copies may pin different versions.

### Target OSS Codebases

| Repo | Rationale |
|------|-----------|
| `lodash` → npm consumers (e.g., `webpack`, `babel`, `jest`) | Deep JS transitive tree, CVE-2021-23337 as template |
| `protobuf` → `grpc-*` → CNCF projects | Cross-language protobuf dependency chain |
| `requests` (Python) → `boto3` → `awscli` | Python HTTP library chain with real CVEs |
| `jackson-databind` → Spring Boot → enterprise Java | Java serialization CVEs with deep blast radius |
| `openssl` → `curl` → `git` → `kubernetes` | System library chain with C/Go/Python consumers |

### Multi-repo Pattern

**Investigate** — symptom (CVE) in leaf repo, blast radius across consumer repos.

### Artifact Types

- **Required:** `answer` (affected package list with dependency paths) + `security_assessment` (CVE impact classification per consumer)
- **Optional:** `code_patch` (version bump fixes)

### Verification Approach

**Plugin:** `eb_verify.plugins.graph_coverage` + `eb_verify.plugins.file_set_match`

- **Deterministic:** Compare agent's affected-package list against OSV/NVD known-affected lists. Precision/recall on `{package, version_range}` tuples.
- **Deterministic:** Verify dependency paths are valid (each hop exists in the manifest/lock file of the importing repo).
- **Deterministic:** For `security_assessment` artifact, validate CVE IDs exist and map to the correct packages.

### Ground Truth Source

- **OSV database** (osv.dev): Machine-readable affected version ranges per CVE
- **NVD** (nvd.nist.gov): CPE-based affected product lists
- **GitHub Security Advisories**: Repository-specific advisory data with affected version ranges
- **Lock file analysis**: `package-lock.json`, `go.sum`, `Cargo.lock` parsed at pinned revisions to determine exact resolved versions

### Checkpoint Structure

| # | Checkpoint | Weight | Verifier |
|---|-----------|--------|----------|
| 1 | Identify the vulnerable package and CVE correctly | 0.10 | `check_cve_id.sh` — exact match |
| 2 | Find all direct dependents of the vulnerable package | 0.30 | `check_direct_deps.sh` — set precision/recall |
| 3 | Trace transitive dependency paths (2+ hops) | 0.35 | `check_transitive_paths.sh` — path validation |
| 4 | Classify affected vs unaffected (version range analysis) | 0.25 | `check_version_analysis.sh` — per-consumer correct/incorrect |

### Difficulty Distribution

- 30% medium (single language, 2 hops, well-documented CVE)
- 50% hard (cross-language, 3–4 hops, version range ambiguity)
- 20% expert (5+ repos, conditional dependencies, vendored forks)

### PRD Suite Mapping

- **Primary:** `dependency_management`
- **Secondary:** `security_operations`

---

## 4. Monorepo Package Boundary Referee

**ID prefix:** `monorepo-boundary-*`
**MCP Signal:** ★★★★½ | **Priority:** 4 | **Task count target:** 8–10

### Description

Given a change in one package of a monorepo, the agent must determine whether it violates package boundaries and classify the change impact (none/patch/minor/major) for each affected sibling package. The agent must understand workspace configs, public vs internal API surfaces, re-exports, and the implicit contracts between sibling packages.

### MCP Signal Mechanism

Sourcegraph's **workspace-aware symbol search** and **find references** within monorepos resolve cross-package imports that respect workspace boundaries. Grep/find fails because: (1) monorepo packages reference each other via workspace protocol (`workspace:*` in pnpm, path dependencies in Cargo.toml) which grep can't resolve, (2) re-exported types create indirect public API surface invisible to text search, (3) barrel files (`index.ts`) aggregate exports making the true public API a computed property of multiple files, (4) internal packages (prefixed `@internal/` or marked `"private": true`) have different boundary rules.

### Target OSS Codebases

| Repo | Rationale |
|------|-----------|
| `babel/babel` (v7.23.0) | 140+ packages, complex inter-package dependencies, frequent semver decisions |
| `vercel/next.js` (v14.0.0) | Monorepo with turbopack, mixed public/internal packages |
| `microsoft/TypeScript` (v5.3.0) | Large single-package but with internal module boundaries |
| `rust-lang/rust` workspace crates | Cargo workspace with strict crate boundary enforcement |
| `pnpm/pnpm` (v8.10.0) | Monorepo managing monorepo tooling — meta-level boundary complexity |

### Multi-repo Pattern

**Enforce** — consistent boundary policy across N packages within a monorepo.

### Artifact Types

- **Required:** `answer` (per-package impact classification: none/patch/minor/major with reasoning)
- **Optional:** `code_patch` (fix boundary violations)

### Verification Approach

**Plugin:** `eb_verify.plugins.classification_match`

- **Deterministic:** Compare agent's per-package impact classification against actual semver bump in the historical release. Exact category match per package.
- **Deterministic:** Verify that claimed boundary violations reference actual cross-package imports (AST-level check).
- **LLM curator (Tier 2):** Validate reasoning quality for edge cases where semver decision was debatable.

### Ground Truth Source

- **CHANGELOG.md entries** in monorepo packages at tagged releases
- **package.json version bumps** between consecutive releases (diff `lerna.json` or `pnpm-workspace.yaml` versioning)
- **Release PR descriptions** explaining semver decisions
- **`lerna changed` / `changeset status` output** at historical commits

### Checkpoint Structure

| # | Checkpoint | Weight | Verifier |
|---|-----------|--------|----------|
| 1 | Identify all affected sibling packages | 0.25 | `check_affected_packages.sh` — set match |
| 2 | Classify change impact per package (none/patch/minor/major) | 0.45 | `check_semver_classification.sh` — category match |
| 3 | Identify specific boundary violations (if any) | 0.30 | `check_boundary_violations.sh` — file+symbol match |

### Difficulty Distribution

- 30% medium (single cross-package type change, clear public API)
- 50% hard (re-export chain affecting 3+ packages, ambiguous internal vs public)
- 20% expert (workspace-wide refactor with cascading semver implications)

### PRD Suite Mapping

- **Primary:** `feature_delivery` (monorepo stratum)
- **Secondary:** `dependency_management`

---

## 5. Database Schema Evolution Impact Analysis

**ID prefix:** `db-schema-*`
**MCP Signal:** ★★★★ | **Priority:** 5 | **Task count target:** 8–10

### Description

Given a proposed or historical database schema migration, the agent must identify all code paths affected — not just direct ORM queries, but views, serializers, API responses, cached values, background jobs, and data migrations that reference the affected tables/columns. The understanding must bridge declarative schema definitions and imperative access patterns scattered across the codebase.

### MCP Signal Mechanism

Sourcegraph's **semantic search** and **cross-file symbol navigation** trace ORM model field references through serializers, views, templates, and API handlers. Grep/find fails because: (1) ORM field access uses dynamic attribute names (`user.email` in Python, `user.getEmail()` in Java) that don't appear as string literals, (2) serializers and API schemas reference model fields by mapped names that differ from column names, (3) raw SQL queries use column names while ORM code uses model attributes, (4) cached values and background jobs reference stale field names indirectly through serialized data structures.

### Target OSS Codebases

| Repo | Rationale |
|------|-----------|
| `django/django` (v4.2) + `wagtail/wagtail` | Django ORM with complex model inheritance, real migration history |
| `sentry-io/sentry` (latest) | Large Django app with 500+ models, heavy migration history |
| `mastodon/mastodon` (v4.2.0) | Rails app with ActiveRecord, real schema evolution |
| `supabase/supabase` (latest) | PostgreSQL-native with raw SQL + API auto-generation |
| `hasura/graphql-engine` (v2.36.0) | Schema → GraphQL API auto-generation, metadata-driven |

### Multi-repo Pattern

**Propagate** — schema change in database layer propagates to application code, API layer, and background workers.

### Artifact Types

- **Required:** `answer` (list of all affected files with categorization: direct query / serializer / API response / cache / background job / test)
- **Optional:** `code_patch` (migration-safe code changes), `migration_guide`

### Verification Approach

**Plugin:** `eb_verify.plugins.file_set_match` + `eb_verify.plugins.category_match`

- **Deterministic:** Compare agent's affected-file list against files changed in the actual migration PR. Precision/recall scoring.
- **Deterministic:** Verify that each claimed affected file actually references the changed table/column (grep for column name + ORM field name).
- **LLM curator (Tier 2):** Validate categorization of impact type (direct query vs cache invalidation vs background job).

### Ground Truth Source

- **Migration PRs** in Django/Rails projects that include both the migration file AND all accompanying code changes
- **Sentry's migration review process** (well-documented, includes impact analysis in PR description)
- **Alembic/Django migration files** cross-referenced with the same commit's code changes
- Filter for PRs where migration + code changes were shipped atomically (not split across PRs)

### Checkpoint Structure

| # | Checkpoint | Weight | Verifier |
|---|-----------|--------|----------|
| 1 | Identify the schema change (table, column, type change) | 0.10 | `check_schema_change.sh` — exact match |
| 2 | Find all direct ORM/SQL references to affected columns | 0.35 | `check_direct_refs.sh` — file-set precision/recall |
| 3 | Find indirect references (serializers, API schemas, caches, jobs) | 0.35 | `check_indirect_refs.sh` — file-set with category labels |
| 4 | Identify affected test files | 0.20 | `check_test_impact.sh` — file-set match |

### Difficulty Distribution

- 30% medium (single column rename, Django app with clear ORM usage)
- 50% hard (table restructuring affecting serializers + API + background jobs)
- 20% expert (cross-service schema change with cached data invalidation and migration ordering)

### PRD Suite Mapping

- **Primary:** `feature_delivery`
- **Secondary:** `technical_debt`

---

## 6. Error Message Provenance Tracing

**ID prefix:** `error-trace-*`
**MCP Signal:** ★★★★ | **Priority:** 6 | **Task count target:** 10–12

### Description

Given only an error message or error code from a bug report (no stack trace, no file paths), the agent must find the exact code location that generates the message, the conditions that trigger it, and the error handling chain that produces the user-visible output. This is backward-tracing from a string to its source through string construction, i18n, error wrapping, and exception propagation.

### MCP Signal Mechanism

Sourcegraph's **literal string search** combined with **symbol navigation** traces error strings through construction chains. Grep/find fails because: (1) error messages are constructed from format strings with interpolated values (`fmt.Errorf("connection to %s failed: %w", host, err)`) — the user sees "connection to db.prod failed: timeout" but grep for that exact string returns nothing, (2) i18n systems map error codes to localized strings in separate resource files, (3) error wrapping chains (`errors.Wrap`, `raise ... from ...`) transform messages at each layer, (4) HTTP error responses may construct messages from multiple sources (status code + body + headers).

### Target OSS Codebases

| Repo | Rationale |
|------|-----------|
| `kubernetes/kubernetes` (v1.29.0) | Massive error surface, complex error wrapping with `k8s.io/apimachinery/pkg/util/errors` |
| `hashicorp/terraform` (v1.6.0) | User-facing CLI errors from deep plugin/provider chains |
| `docker/cli` + `moby/moby` (v24.0) | Error messages cross container boundary (CLI → daemon → containerd) |
| `grafana/grafana` (v10.2.0) | Web UI error messages from backend API through frontend rendering |
| `golang/go` standard library | Canonical Go error patterns, well-documented error paths |

### Multi-repo Pattern

**Investigate** — error symptom in user-facing layer, root cause in backend/library layer.

### Artifact Types

- **Required:** `answer` (source file + line producing the error, trigger conditions, error propagation chain)
- **Optional:** `code_patch` (fix for the underlying bug)

### Verification Approach

**Plugin:** `eb_verify.plugins.file_line_match` + `eb_verify.plugins.chain_match`

- **Deterministic:** Verify that the identified source location contains a string literal or format pattern that can produce the given error message (regex match of format string against error text).
- **Deterministic:** Verify that the error propagation chain is a valid call path (each function in the chain calls the next, verified via AST).
- **Deterministic:** Compare identified file against the actual fix PR's changed files.

### Ground Truth Source

- **GitHub issues** with error message in title/body + linked fix PR
- **Fix PR diffs** showing which file was changed to resolve the error
- Filter: issues where the error message is the *only* clue (exclude issues with stack traces or file paths)
- Repos: kubernetes, terraform, docker — all have rich issue → fix PR linkage

### Checkpoint Structure

| # | Checkpoint | Weight | Verifier |
|---|-----------|--------|----------|
| 1 | Locate the exact source file + function that generates the error | 0.40 | `check_error_source.sh` — file + function match |
| 2 | Trace the error propagation chain (wrapper layers) | 0.30 | `check_error_chain.sh` — ordered call-path validation |
| 3 | Identify trigger conditions (what input/state causes this error) | 0.30 | `check_trigger_conditions.sh` — keyword/concept match against GT |

### Difficulty Distribution

- 30% medium (simple format string, single-repo, 1-hop error chain)
- 50% hard (multi-layer error wrapping, 2 repos, format string with interpolation)
- 20% expert (cross-service error propagation, i18n layer, error code → message lookup)

### PRD Suite Mapping

- **Primary:** `customer_escalation`
- **Secondary:** `incident_response`

---

## 7. Support Code Mapping

**ID prefix:** `support-map-*`
**MCP Signal:** ★★★½ | **Priority:** 7 | **Task count target:** 10–15

### Description

Given a vague GitHub issue describing user-visible behavior (e.g., "app crashes when I click export"), the agent must identify the code paths that produce the reported behavior, classify severity, and identify the owning module. The primary challenge is bridging the semantic gap between natural-language behavior descriptions and codebase internals. Reframed from "Support Ticket Triage" to emphasize codebase navigation over NL classification.

### MCP Signal Mechanism

Sourcegraph's **semantic search** bridges natural-language behavior descriptions to code symbols — searching for "export" finds `ExportController`, `handleExport`, `exportToPDF`, and related symbols even when the user's description doesn't use technical terms. Grep/find fails because: (1) user descriptions use product terminology ("the export button"), not code terminology (`ExportService.generateReport()`), (2) behavior descriptions span multiple code paths (click handler → API call → backend service → file generation), (3) the relevant code may be in a completely different part of the codebase from where the user perceives the problem.

### Target OSS Codebases

| Repo | Rationale |
|------|-----------|
| `grafana/grafana` (v10.2.0) | Rich issue tracker, large codebase, clear module ownership |
| `mattermost/mattermost` (v9.0) | Enterprise messaging with well-labeled issues |
| `gitlabhq/gitlabhq` (v16.6) | Large Rails monolith with team-owned modules |
| `sentry-io/sentry` (latest) | Issue tracker with linked fix PRs, Django backend |
| `nextcloud/server` (v28.0) | PHP monolith with clear module boundaries |

### Multi-repo Pattern

**Investigate** — user symptom in UI layer, root cause in backend service or library.

### Artifact Types

- **Required:** `answer` (identified code paths + severity classification + owning module)
- **Optional:** `kb_article` (customer-facing explanation), `reproduction_script`

### Verification Approach

**Plugin:** `eb_verify.plugins.file_set_match` + `eb_verify.plugins.label_match`

- **Deterministic:** Compare agent's identified code paths against files changed in the linked fix PR. Precision/recall on file set.
- **Deterministic:** Compare module/ownership classification against the actual PR reviewer/team label.
- **Weighted scoring:** Severity classification at 0.15 weight (subjective, LLM curator). Code path identification at 0.60 weight (deterministic file match).

### Ground Truth Source

- **GitHub issues** with labels (severity, module, team) + linked fix PRs — highest CSB reuse potential (30–50 adaptable tasks from CSB's existing corpus)
- **Issue labels** provide severity and module ownership ground truth
- **Fix PR file lists** provide code path ground truth
- Filter for issues with: vague user description (not developer-filed), linked fix PR, at least 3 files changed

### Checkpoint Structure

| # | Checkpoint | Weight | Verifier |
|---|-----------|--------|----------|
| 1 | Identify the code paths producing the reported behavior | 0.60 | `check_code_paths.sh` — file-set precision/recall against fix PR |
| 2 | Identify the owning module/team | 0.15 | `check_ownership.sh` — label match |
| 3 | Classify severity correctly | 0.15 | `check_severity.sh` — category match |
| 4 | Find related past issues (if any) | 0.10 | `check_related_issues.sh` — issue ID set match |

### Difficulty Distribution

- 40% medium (clear behavior description, single module, small codebase)
- 40% hard (vague description, cross-module, large codebase)
- 20% expert (multi-service, misleading symptoms, requires deep domain knowledge)

### PRD Suite Mapping

- **Primary:** `customer_escalation`
- **Secondary:** `incident_response`

---

## 8. Dead Code / Feature Flag Necropsy

**ID prefix:** `dead-code-*`
**MCP Signal:** ★★★★ | **Priority:** 8 | **Task count target:** 3–5

### Description

Given a codebase before a known cleanup PR, the agent must identify dead code, abandoned feature flags, and unreachable branches. This is an **absence detection task** — the agent must prove that code is NOT reachable, which requires complete call graph understanding. Feature flags add another dimension: code that's syntactically reachable but semantically dead because the flag is permanently off.

### MCP Signal Mechanism

Sourcegraph's **exhaustive find-references** proves absence by confirming zero callers across the entire indexed corpus. This is the "prove absence" argument: MCP's value is definitively answering "nothing calls this." Grep/find fails because: (1) proving absence requires searching the *entire* codebase and confirming zero matches — grep can find matches but can't confirm completeness, (2) dynamic dispatch (interfaces, virtual methods, reflection) means grep for a function name misses indirect callers, (3) feature flags may be evaluated at runtime from config files, environment variables, or remote feature flag services — text search can't determine if a flag is "permanently off."

### Target OSS Codebases

| Repo | Rationale |
|------|-----------|
| `facebook/react` (pre-cleanup commits) | Known dead code cleanup PRs in React 18 → 19 transition |
| `angular/angular` (pre-cleanup commits) | Ivy renderer cleanup removed large dead code sections |
| `microsoft/vscode` (pre-cleanup commits) | Regular dead code sweeps documented in release notes |
| `chromium/chromium` (feature flag cleanup PRs) | Massive feature flag surface with documented cleanup cycles |

### Multi-repo Pattern

**Enforce** — consistent dead-code identification policy across modules within a codebase (single-repo, but cross-package within monorepo).

### Artifact Types

- **Required:** `answer` (list of dead code locations with confidence scores and evidence)
- **Optional:** `code_patch` (cleanup diff)

### Verification Approach

**Plugin:** `eb_verify.plugins.file_set_match` (precision/recall mode)

- **Deterministic:** Compare agent's dead-code list against files/functions removed in the actual cleanup PR. Precision (avoiding false positives) and recall (finding everything that was actually dead).
- **Deterministic:** Verify that claimed dead functions have zero callers by running a reference search on the pinned revision.
- **Note:** False positives are heavily penalized (precision weight > recall weight) because incorrectly flagging live code as dead is worse than missing some dead code.

### Ground Truth Source

- **Cleanup PRs** in React, Angular, VS Code that removed dead code
- **Git log filtering** for commits with messages matching "remove dead", "remove unused", "cleanup", "delete deprecated"
- **Feature flag removal PRs** that delete both the flag check and the gated code
- Each task uses the commit *before* the cleanup PR as the starting state

### Checkpoint Structure

| # | Checkpoint | Weight | Verifier |
|---|-----------|--------|----------|
| 1 | Identify dead functions/classes (precision-weighted) | 0.50 | `check_dead_code.sh` — precision ≥ 0.9, recall ≥ 0.6 |
| 2 | Identify permanently-off feature flags | 0.30 | `check_feature_flags.sh` — flag name match against GT |
| 3 | Provide evidence of unreachability per item | 0.20 | `check_evidence.sh` — LLM curator validates reasoning |

### Difficulty Distribution

- 20% medium (obvious unused exports in a small package)
- 50% hard (dead code behind dynamic dispatch or conditional compilation)
- 30% expert (feature flags with runtime evaluation, cross-package dead code in monorepo)

### PRD Suite Mapping

- **Primary:** `technical_debt`
- **Secondary:** `feature_delivery`

---

## 9. Incident Investigation (Simplified)

**ID prefix:** `incident-inv-*`
**MCP Signal:** ★★★ | **Priority:** 9 (Tier 2 — stretch) | **Task count target:** 3–5

### Description

Given a codebase at a buggy commit plus an error log or alert, the agent must perform cross-service root cause tracing to identify the failing component, the code path that caused the failure, and the remediation. This is simplified from full event-replay: no telemetry stream, no timeline reconstruction — just codebase + error context → root cause identification.

### MCP Signal Mechanism

Sourcegraph's **cross-repo code navigation** traces error paths across service boundaries — an error in service A may originate from a breaking change in shared library B consumed by service C. Grep/find fails because: (1) service-to-service communication uses RPC/HTTP with serialized payloads — the error string in the caller doesn't match the error construction in the callee, (2) shared library changes affect multiple services in non-obvious ways, (3) the root cause service may not be the one producing the user-visible error.

### Target OSS Codebases

| Repo | Rationale |
|------|-----------|
| `kubernetes/kubernetes` + `etcd-io/etcd` | K8s API server errors caused by etcd backend issues |
| `istio/istio` + `envoyproxy/envoy` | Service mesh errors from proxy-level failures |
| `grafana/grafana` + `prometheus/prometheus` | Monitoring stack cross-service failures |
| `docker/cli` + `moby/moby` + `containerd/containerd` | Container runtime error chain |

### Multi-repo Pattern

**Investigate** — symptom in service A, root cause in service B.

### Artifact Types

- **Required:** `incident_report` (structured: root cause, affected components, error chain, remediation)
- **Optional:** `code_patch` (fix), `runbook` (prevention steps)

### Verification Approach

**Plugin:** `eb_verify.plugins.incident_report` + `eb_verify.plugins.file_set_match`

- **Deterministic:** Verify root cause file matches the file changed in the actual fix commit.
- **Deterministic:** Verify affected components list against repos/services touched in the fix PR.
- **Structural completeness:** `incident_report` artifact must contain required fields (root_cause, affected_services, error_chain, remediation).
- **LLM curator (Tier 2):** Validate remediation quality and error chain reasoning.

### Ground Truth Source

- **Public postmortems** from Kubernetes, GitLab, Cloudflare (mapped to OSS code at the relevant commit)
- **Fix commits** linked to incident reports in issue trackers
- **GitHub issues** tagged "bug" + "critical" with cross-repo references in the fix
- Authoring cost estimated 4–6 hrs/task using postmortem templates

### Checkpoint Structure

| # | Checkpoint | Weight | Verifier |
|---|-----------|--------|----------|
| 1 | Identify the root cause file/function | 0.35 | `check_root_cause.sh` — file match against fix commit |
| 2 | Trace the error chain across services | 0.30 | `check_error_chain.sh` — ordered service list match |
| 3 | List all affected components/services | 0.15 | `check_affected_services.sh` — set match |
| 4 | Propose correct remediation | 0.20 | `check_remediation.sh` — LLM curator with keyword anchors |

### Difficulty Distribution

- 0% medium (minimum hard for multi-service investigation)
- 60% hard (2-service error chain, clear error log)
- 40% expert (3+ services, misleading error messages, configuration-induced failures)

### PRD Suite Mapping

- **Primary:** `incident_response`
- **Secondary:** `customer_escalation`

---

## 10. Configuration Drift Forensics

**ID prefix:** `config-drift-*`
**MCP Signal:** ★★★ | **Priority:** 10 (Tier 2 — lowest priority, first to cut) | **Task count target:** 3–5

### Description

Given a multi-layer deployment configuration hierarchy (Helm charts with value overrides, Terraform modules with variable chains, Kustomize overlays), the agent must identify all configuration drift points — places where values diverge from the template or base in unintended ways. Scoped to COMPLEX drift only: multi-layer hierarchies with inheritance/override chains, NOT simple "find the different config value" tasks.

### MCP Signal Mechanism

Sourcegraph's **cross-file search** with structural awareness navigates YAML/HCL/JSON inheritance chains where values are defined in one file, overridden in another, and consumed in a third. Grep/find fails because: (1) Helm value resolution follows a multi-layer precedence chain (defaults → chart values → subchart values → CLI overrides) — grep finds all definitions but can't determine effective values, (2) Terraform variable inheritance flows through `module` → `variable` → `local` → `output` chains across files, (3) Kustomize overlays apply strategic merge patches that grep can't interpret, (4) environment-specific overrides (dev/staging/prod) create parallel configuration trees.

### Target OSS Codebases

| Repo | Rationale |
|------|-----------|
| `helm/charts` (deprecated but rich historical data) | Complex multi-chart deployments with value override chains |
| `argoproj/argo-cd` (v2.9.0) | GitOps tool with Helm + Kustomize configuration |
| `hashicorp/terraform` + community modules | Terraform variable chain complexity |
| `kubernetes/kubernetes` deployment configs | Multi-env K8s manifests with Kustomize |
| `pulumi/examples` | Multi-language IaC with complex variable passing |

### Multi-repo Pattern

**Enforce** — consistent configuration policy across environments/services.

### Artifact Types

- **Required:** `answer` (list of drift points with: file, key, expected value, actual value, override chain)
- **Optional:** `config` (corrected configuration files)

### Verification Approach

**Plugin:** `eb_verify.plugins.config_diff` + `eb_verify.plugins.key_value_match`

- **Deterministic:** Compare agent's drift-point list against the actual config-fix PR diff. Each drift point is a `{file, key, expected, actual}` tuple — exact match scoring.
- **Deterministic:** Verify override chain correctness by tracing value precedence through the configuration hierarchy.
- **Artifact validation:** If `config` artifact provided, run `helm template`, `terraform validate`, or `kustomize build` to verify syntactic correctness.

### Ground Truth Source

- **Config-fix PRs** in Helm chart repos and Terraform module repos
- **ArgoCD sync-diff outputs** captured from real deployments
- **Terraform plan outputs** showing drift between state and desired configuration
- Filter for PRs fixing multi-layer drift (not simple typo fixes)

### Checkpoint Structure

| # | Checkpoint | Weight | Verifier |
|---|-----------|--------|----------|
| 1 | Identify all drift points (file + key) | 0.40 | `check_drift_points.sh` — set precision/recall |
| 2 | Determine correct expected values (trace override chain) | 0.35 | `check_expected_values.sh` — value match per key |
| 3 | Validate corrected configuration (if provided) | 0.25 | `check_config_valid.sh` — `helm template` / `terraform validate` |

### Difficulty Distribution

- 30% medium (2-layer Helm values, single chart)
- 50% hard (3-layer override chain, Terraform module variable threading)
- 20% expert (Kustomize strategic merge + Helm subchart values + env-specific overlays)

### PRD Suite Mapping

- **Primary:** `platform_engineering`
- **Secondary:** `security_operations`

---

## Cross-Cutting Sections

### Task Mix Gradient Mapping

The PRD requires: 15% calibration, 25% large single-repo, 30% dual-repo, 20% 3–5 repo, 10% monorepo cross-package.

Using midpoint estimates (total ~80 tasks):

| Stratum | Target % | Target Count | Task Types | Allocation |
|---------|----------|-------------|------------|------------|
| **Calibration** (single-repo, small, MCP bias check) | 15% | 12 | `error-trace-*` (4), `support-map-*` (4), `dead-code-*` (2), `config-drift-*` (2) | Simple variants of each type in single, small repo |
| **Large single-repo** | 25% | 20 | `error-trace-*` (5), `support-map-*` (6), `dead-code-*` (3), `db-schema-*` (3), `monorepo-boundary-*` (3) | kubernetes, grafana, sentry-sized repos |
| **Dual-repo** | 30% | 24 | `api-contract-*` (5), `dep-graph-*` (6), `db-schema-*` (5), `error-trace-*` (3), `incident-inv-*` (2), `support-map-*` (3) | Real dependency pairs |
| **3–5 repo** | 20% | 16 | `api-contract-*` (5), `refactor-orch-*` (5), `dep-graph-*` (4), `incident-inv-*` (2) | CNCF ecosystem chains |
| **Monorepo cross-package** | 10% | 8 | `monorepo-boundary-*` (7), `dead-code-*` (1) | Babel, Next.js, Rust workspace |
| **Total** | 100% | **80** | | |

### Difficulty Distribution Across the Full Suite

| Difficulty | Target % | Count | Distribution by Type |
|-----------|----------|-------|---------------------|
| **Medium** | 30% | 24 | Calibration tasks (12) + simple single-repo variants (12) |
| **Hard** | 50% | 40 | Core dual-repo and large single-repo tasks |
| **Expert** | 20% | 16 | Multi-repo chains (3–5 repos) + complex monorepo boundary tasks |

Difficulty correlates with but is not identical to stratum:
- All calibration tasks are medium difficulty
- Large single-repo spans medium–hard
- Dual-repo is predominantly hard
- 3–5 repo is hard–expert
- Monorepo cross-package spans hard–expert

### Session Type Mapping

| Session Type | Task Types | Count | Rationale |
|-------------|-----------|-------|-----------|
| **single** | All 10 types (default) | ~65 | Standard one-shot evaluation |
| **chain** | `refactor-orch-*` (2), `incident-inv-*` (2), `api-contract-*` (1) | ~5 | Multi-session needed for large refactors and incident response arcs |
| **resume** | `support-map-*` (3), `db-schema-*` (2) | ~5 | Agent picks up partially completed investigation/migration |
| **event_replay** | Deferred to Phase 2 | 0 | Authoring cost too high for Phase 1; incident-inv tasks use simplified format |
| **Total** | | **~75–80** | |

**Note:** `chain` and `resume` session types are Phase 1 stretch goals (S1, S3 in PRD). If not shipped in Phase 1, all tasks default to `single`.

### Total Task Count Budget

| # | Task Type | ID Prefix | Min | Max | Target | Phase |
|---|-----------|-----------|-----|-----|--------|-------|
| 1 | API Contract Boundary Analysis | `api-contract-*` | 8 | 10 | 9 | Phase 1 |
| 2 | Multi-Repo Refactor Orchestration | `refactor-orch-*` | 5 | 8 | 6 | Phase 1 |
| 3 | Dependency Graph Traversal Races | `dep-graph-*` | 10 | 12 | 10 | Phase 1 |
| 4 | Monorepo Package Boundary Referee | `monorepo-boundary-*` | 8 | 10 | 8 | Phase 1 |
| 5 | DB Schema Evolution Impact Analysis | `db-schema-*` | 8 | 10 | 8 | Phase 1 |
| 6 | Error Message Provenance Tracing | `error-trace-*` | 10 | 12 | 10 | Phase 1 |
| 7 | Support Code Mapping | `support-map-*` | 10 | 15 | 12 | Phase 1 |
| 8 | Dead Code / Feature Flag Necropsy | `dead-code-*` | 3 | 5 | 4 | Phase 1 |
| 9 | Incident Investigation (simplified) | `incident-inv-*` | 3 | 5 | 4 | Phase 1 (stretch) |
| 10 | Configuration Drift Forensics | `config-drift-*` | 3 | 5 | 4 | Phase 1 (stretch) |
| | **Conditional:** Permission/Access Audit or Adversarial Sabotage | `sec-audit-*` | 3 | 5 | 4 | Conditional |
| | **TOTAL** | | **71** | **97** | **79** | |

Target of **79 tasks** (75 core + 4 conditional) fits within the PRD's 80–100 range. If both stretch types ship and the conditional slot is filled, total reaches **87 tasks**.

### Implementation Batch Order

Aligned with the convergence debate's implementation order (feasibility-first):

| Batch | Task Types | Infrastructure Needed | Estimated Task Yield |
|-------|-----------|----------------------|---------------------|
| **Batch 1** — Zero new infra | #6 Error Trace, #7 Support Map, #4 Monorepo Boundary | Answer verifier only | 30 tasks |
| **Batch 2** — Multi-repo sandbox | #3 Dep Graph, #5 DB Schema, #1 API Contract | Multi-repo Dockerfile + cross-repo test runner | 27 tasks |
| **Batch 3** — Deeper authoring | #2 Refactor Orch, #8 Dead Code | Topological order verifier + cleanup PR mining | 10 tasks |
| **Batch 4** — Stretch/conditional | #9 Incident Inv, #10 Config Drift, conditional slot | Incident report verifier + config validation | 8–12 tasks |

### Verifier Plugin Summary

| Plugin | Used By | Verification Type |
|--------|---------|------------------|
| `eb_verify.plugins.file_set_match` | #1, #3, #5, #6, #7, #8, #9 | Precision/recall on file path sets |
| `eb_verify.plugins.symbol_match` | #1 | Symbol-level cross-repo reference matching |
| `eb_verify.plugins.topological_order` | #2 | DAG constraint validation for ordering |
| `eb_verify.plugins.classification_match` | #4 | Category match (none/patch/minor/major) |
| `eb_verify.plugins.graph_coverage` | #3 | Dependency graph path coverage |
| `eb_verify.plugins.file_line_match` | #6 | File + line range matching |
| `eb_verify.plugins.chain_match` | #6, #9 | Ordered call-path / service-chain validation |
| `eb_verify.plugins.label_match` | #7 | Label/category match against issue metadata |
| `eb_verify.plugins.incident_report` | #9 | Structural completeness of incident reports |
| `eb_verify.plugins.config_diff` | #10 | Configuration key-value drift matching |
| `eb_verify.plugins.key_value_match` | #10 | Override chain value resolution |
| `eb_verify.plugins.category_match` | #5 | Impact type categorization |

---

# Implementation Plan: Agent Task Breakdown

This section breaks all implementation work into discrete, agent-executable tasks organized by phase. Each task is self-contained — one Claude Code agent session can complete it with clear inputs, outputs, and success criteria.

**Naming convention:** `P{phase}.{seq}` (e.g., P0.1, P1.3)

---

## Phase 0: Infrastructure Validation

Validate that existing prototypes (eb_verify, sandbox, schema, mining) are functional and ready to support task authoring at scale. All Phase 0 tasks are independent and can run in parallel.

### Task P0.1: eb_verify Smoke Test
- **Phase**: 0
- **Dependencies**: None
- **Agent type**: tdd-guide
- **Inputs**: `lib/eb_verify/` (all modules), `benchmarks/EXAMPLE_TASK.toml`, `schemas/task.schema.json`
- **Outputs**: `tests/test_eb_verify_smoke.py` — end-to-end test that parses a task, runs checkpoint verifiers, produces a scored result; any bug fixes to `lib/eb_verify/`
- **Success criteria**: `python -m pytest tests/test_eb_verify_smoke.py` passes. Test covers: task parsing → checkpoint execution → score aggregation → JSON output. Covers at least 3 plugin types (answer, code_patch, config_validator).
- **Scope**: medium (~5-8 files)

### Task P0.2: Multi-Repo Sandbox Validation
- **Phase**: 0
- **Dependencies**: None
- **Agent type**: general-purpose
- **Inputs**: `scripts/sandbox/` (dockerfile_generator.py, sandbox_builder.py, health_check.sh), `benchmarks/mined/dep-mgmt-grpc-go-balancer-001.toml` (multi-repo task)
- **Outputs**: Validated Dockerfile that clones 2 repos into `/workspace/`, passing `health_check.sh`; documented disk/time measurements in `docs/sandbox_measurements.md`
- **Success criteria**: `docker build` succeeds, `health_check.sh` passes inside container, both repos accessible at `/workspace/{path}/`, total workspace <100MB for 2-repo case.
- **Scope**: small (~3-4 files)

### Task P0.3: Task Schema Validation for All 10 Types
- **Phase**: 0
- **Dependencies**: None
- **Agent type**: tdd-guide
- **Inputs**: `schemas/task.schema.json`, convergence debate report (10 task types)
- **Outputs**: `tests/test_schema_coverage.py` — one synthetic minimal task.toml fixture per task type, validated against schema; schema patches if gaps found (e.g., missing fields for dead-code tasks or refactor ordering)
- **Success criteria**: All 10 task types can be represented by the schema. Any required schema extensions are backward-compatible. Tests pass.
- **Scope**: medium (~4-6 files)

### Task P0.4: Task Mining Tooling Validation
- **Phase**: 0
- **Dependencies**: None
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/` (mine_breaking_changes.py, extract_task.py, validate_candidate.py), `scripts/mining/MINING_LOG.md`
- **Outputs**: Run mining pipeline against 1 known dependency chain (e.g., urllib3→requests), document success/failure and conversion rate; fix any broken scripts
- **Success criteria**: Pipeline produces at least 1 validated candidate task from a real OSS dependency chain. `validate_candidate.py` correctly accepts good candidates and rejects invalid ones.
- **Scope**: small (~3-4 files)

### Task P0.5: Cross-Repo Test Runner Validation
- **Phase**: 0
- **Dependencies**: P0.2
- **Agent type**: general-purpose
- **Inputs**: `scripts/sandbox/test_runner.sh`, a 2-repo sandbox from P0.2
- **Outputs**: Working `test.sh` template that can `cd` between repos, run commands in each, and report pass/fail with structured output
- **Success criteria**: `test.sh` executes inside the Docker sandbox, runs at least one command per repo, exits with correct status code, produces JSON-parseable output.
- **Scope**: small (~2-3 files)

---

## Phase 1: Batch 1 — Quick Wins (Answer Verifier Only)

Task types: **#23 Error Message Provenance**, **#18 Support Code Mapping**, **#12 Monorepo Package Boundary Referee**. These require only the answer verifier plugin (no multi-repo sandbox). Each task type follows a 5-step pipeline: mine → extract GT → author → verify → sample run.

### Task P1.1: Mine #23 Error Message Provenance Candidates
- **Phase**: 1
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/mine_breaking_changes.py` (adapted), GitHub search API
- **Outputs**: `benchmarks/mined/provenance_candidates.md` — 10-15 candidate error-to-fix mappings from large OSS repos (e.g., VS Code, Django, Flask, FastAPI). Each entry: repo, error string, fix PR, files changed.
- **Success criteria**: ≥10 candidates with: (a) error message traceable in source, (b) linked fix PR, (c) repo ≥50K LoC. Candidates span ≥3 different repos.
- **Scope**: medium (~3-5 files)

### Task P1.2: Extract Ground Truth for #23 Candidates
- **Phase**: 1
- **Dependencies**: P1.1
- **Agent type**: general-purpose
- **Inputs**: Candidate list from P1.1, actual repos (cloned)
- **Outputs**: For top 10 candidates: `benchmarks/customer_escalation/err-provenance-{NNN}/ground_truth.json` with required_files (code paths that produce the error) and sufficient_files (related config, tests)
- **Success criteria**: Each ground truth has ≥2 required files identified deterministically (grep for error string, trace call chain). Confidence scores assigned. At least 8 of 10 candidates survive validation.
- **Scope**: large (~10-15 files)

### Task P1.3: Author #23 Error Message Provenance Tasks
- **Phase**: 1
- **Dependencies**: P1.2
- **Agent type**: general-purpose
- **Inputs**: Ground truth from P1.2, `schemas/task.schema.json`, `benchmarks/EXAMPLE_TASK.toml`
- **Outputs**: 8-10 complete task definitions under `benchmarks/customer_escalation/err-provenance-{NNN}/`: `task.toml`, `instruction.md`, checkpoint verifier scripts
- **Success criteria**: All task.toml files validate against schema. Each task has 2-3 checkpoints (identify error source → trace propagation path → identify fix location). Instruction.md is realistic (written as a support ticket, not a test prompt). `difficulty_stratum` assigned.
- **Scope**: large (~25-30 files)

### Task P1.4: Verify #23 Tasks (Known-Good/Known-Bad)
- **Phase**: 1
- **Dependencies**: P1.3, P0.1
- **Agent type**: tdd-guide
- **Inputs**: Authored tasks from P1.3, `lib/eb_verify/`
- **Outputs**: `tests/test_provenance_verifiers.py` — for each task, verifier correctly scores: (a) ground truth answer → score ≥0.85, (b) empty answer → score ≤0.10, (c) partial answer → score between 0.3-0.7
- **Success criteria**: All verifiers discriminate correctly across 3 answer quality levels. No false positives (wrong answer scoring >0.5).
- **Scope**: medium (~8-10 files)

### Task P1.5: Sample Run #23 (Baseline + MCP)
- **Phase**: 1
- **Dependencies**: P1.4
- **Agent type**: general-purpose
- **Inputs**: 2 authored tasks from P1.3, sandbox infrastructure
- **Outputs**: `results/sample_runs/provenance/` — run logs, scores, token counts for 2 tasks × 2 modes (baseline, MCP). `results/sample_runs/provenance/analysis.md` with score comparison.
- **Success criteria**: Both runs complete without infrastructure errors. Scores are in the expected range (not all-zero or all-one). MCP and baseline scores are captured with tool-usage metadata.
- **Scope**: medium (~5-6 files)

### Task P1.6: Mine #18 Support Code Mapping Candidates
- **Phase**: 1
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/`, CSB task inventory (for reuse candidates from ~/CodeScaleBench)
- **Outputs**: `benchmarks/mined/support_mapping_candidates.md` — 15-20 candidates. Prioritize CSB Org tasks adaptable to "given issue description, find relevant code paths" format. Supplement with GitHub Issues from large repos that have linked fix PRs.
- **Success criteria**: ≥10 candidates from CSB adaptation + ≥5 fresh-mined. Each has: issue description, linked code paths, fix PR reference.
- **Scope**: medium (~3-5 files)

### Task P1.7: Extract Ground Truth for #18 Candidates
- **Phase**: 1
- **Dependencies**: P1.6
- **Agent type**: general-purpose
- **Inputs**: Candidate list from P1.6
- **Outputs**: Ground truth files for top 12 candidates under `benchmarks/customer_escalation/support-mapping-{NNN}/ground_truth.json`
- **Success criteria**: Each ground truth identifies code paths that produce reported behavior. Required files confirmed via deterministic tracing. CSB-migrated tasks include `csb_lineage` in task.toml.
- **Scope**: large (~12-15 files)

### Task P1.8: Author #18 Support Code Mapping Tasks
- **Phase**: 1
- **Dependencies**: P1.7
- **Agent type**: general-purpose
- **Inputs**: Ground truth from P1.7, schema, examples
- **Outputs**: 10-12 complete task definitions under `benchmarks/customer_escalation/support-mapping-{NNN}/`
- **Success criteria**: Schema-valid. Each task has 2-4 checkpoints: identify relevant module (0.20) → find specific code paths (0.60) → suggest severity (0.15) → identify related tests (0.05). Instructions framed as realistic support tickets.
- **Scope**: large (~30-35 files)

### Task P1.9: Verify #18 Tasks
- **Phase**: 1
- **Dependencies**: P1.8, P0.1
- **Agent type**: tdd-guide
- **Inputs**: Authored tasks from P1.8, `lib/eb_verify/`
- **Outputs**: `tests/test_support_mapping_verifiers.py`
- **Success criteria**: Same 3-tier discrimination as P1.4. Additionally: CSB-migrated tasks score ≥0.80 when given original CSB ground truth answer.
- **Scope**: medium (~8-10 files)

### Task P1.10: Mine #12 Monorepo Package Boundary Candidates
- **Phase**: 1
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/`, target monorepos: Nx, Turborepo, Lerna-managed repos, Rush-managed repos, PNPM workspaces
- **Outputs**: `benchmarks/mined/monorepo_boundary_candidates.md` — 10-15 candidates where a change in one package should have triggered semver bumps or CHANGELOG entries in dependent packages.
- **Success criteria**: ≥10 candidates from ≥3 different monorepos. Each has: commit/PR that changed a package, list of dependent packages that needed (or got) semver bumps.
- **Scope**: medium (~3-5 files)

### Task P1.11: Extract Ground Truth for #12 Candidates
- **Phase**: 1
- **Dependencies**: P1.10
- **Agent type**: general-purpose
- **Inputs**: Candidate list from P1.10
- **Outputs**: Ground truth for top 10 candidates under `benchmarks/feature_delivery/monorepo-boundary-{NNN}/ground_truth.json`
- **Success criteria**: Each GT deterministically identifies: changed package, affected dependent packages, expected semver bump type (major/minor/patch), CHANGELOG entries. Verified against actual PR outcomes.
- **Scope**: large (~10-12 files)

### Task P1.12: Author #12 Monorepo Package Boundary Tasks
- **Phase**: 1
- **Dependencies**: P1.11
- **Agent type**: general-purpose
- **Inputs**: Ground truth from P1.11, schema
- **Outputs**: 8-10 complete task definitions under `benchmarks/feature_delivery/monorepo-boundary-{NNN}/`
- **Success criteria**: Schema-valid. Checkpoints: identify changed package (0.15) → list affected dependents (0.40) → determine correct semver bumps (0.30) → verify CHANGELOG consistency (0.15). `difficulty_stratum = "monorepo_cross_package"`.
- **Scope**: large (~25-30 files)

### Task P1.13: Verify #12 Tasks
- **Phase**: 1
- **Dependencies**: P1.12, P0.1
- **Agent type**: tdd-guide
- **Inputs**: Authored tasks from P1.12, `lib/eb_verify/`
- **Outputs**: `tests/test_monorepo_boundary_verifiers.py`
- **Success criteria**: 3-tier discrimination. Partial credit correctly awarded for finding some-but-not-all affected packages.
- **Scope**: medium (~8-10 files)

### Task P1.14: Sample Runs for #18 and #12
- **Phase**: 1
- **Dependencies**: P1.9, P1.13
- **Agent type**: general-purpose
- **Inputs**: 1 task each from #18 and #12
- **Outputs**: `results/sample_runs/support_mapping/` and `results/sample_runs/monorepo_boundary/` — run logs, scores, token counts (baseline + MCP)
- **Success criteria**: All 4 runs complete. Meaningful score spread across modes. No infrastructure failures.
- **Scope**: medium (~6-8 files)

---

## Phase 2: Batch 2 — Multi-Repo Tasks

Task types: **#1 Dependency Graph Traversal**, **#25 DB Schema Evolution**, **#5 API Contract Boundary**. These require multi-repo sandbox infrastructure (2-3 repos per task).

### Task P2.1: Multi-Repo Sandbox Templates
- **Phase**: 2
- **Dependencies**: P0.2, P0.5
- **Agent type**: general-purpose
- **Inputs**: `scripts/sandbox/`, prototype measurements from P0.2
- **Outputs**: `scripts/sandbox/templates/` — Dockerfile templates for: Go multi-repo (grpc-go + etcd), Python multi-repo (urllib3 + requests + boto3), Java multi-repo (protobuf-java + grpc-java); `scripts/sandbox/build_all.sh`
- **Success criteria**: Each template builds in <5 min, produces working sandbox with all repos at pinned revisions, passes health check. Combined workspace <200MB per task.
- **Scope**: medium (~6-8 files)

### Task P2.2: Mine #1 Dependency Graph Traversal Candidates
- **Phase**: 2
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/`, OSV/NVD databases, CNCF ecosystem repos
- **Outputs**: `benchmarks/mined/dep_traversal_candidates.md` — 12-15 candidates. Each: CVE ID, affected package, dependency chain (2-3 repos), known affected versions.
- **Success criteria**: ≥12 candidates with: (a) real CVE in OSV/NVD, (b) traceable dependency chain via import graphs, (c) fix PR exists. Mix of Go, Python, and Java chains.
- **Scope**: medium (~3-5 files)

### Task P2.3: Extract Ground Truth for #1 Candidates
- **Phase**: 2
- **Dependencies**: P2.2
- **Agent type**: general-purpose
- **Inputs**: Candidates from P2.2, actual repos
- **Outputs**: Ground truth for top 10 under `benchmarks/dependency_management/dep-traversal-{NNN}/ground_truth.json` — required files include: vulnerable dependency declaration, import chain files, consumer code using affected API
- **Success criteria**: Each GT has deterministic tier (import graph parsing confirms dependency chain). Required files span ≥2 repos. Confidence ≥0.9 for deterministic-source files.
- **Scope**: large (~12-15 files)

### Task P2.4: Author #1 Dependency Graph Traversal Tasks
- **Phase**: 2
- **Dependencies**: P2.3, P2.1
- **Agent type**: general-purpose
- **Inputs**: Ground truth from P2.3, sandbox templates from P2.1, schema
- **Outputs**: 10-12 tasks under `benchmarks/dependency_management/dep-traversal-{NNN}/`: task.toml, instruction.md, Dockerfile, test.sh, checkpoint verifiers
- **Success criteria**: Schema-valid with `difficulty_stratum ∈ {dual_repo, multi_repo}`. Checkpoints: identify vulnerable dependency (0.20) → trace propagation path (0.35) → identify all affected consumers (0.30) → propose fix strategy (0.15). `multi_repo_pattern = "investigate"` or `"propagate"`.
- **Scope**: large (~35-40 files)

### Task P2.5: Verify #1 Tasks
- **Phase**: 2
- **Dependencies**: P2.4, P0.1
- **Agent type**: tdd-guide
- **Inputs**: Tasks from P2.4, `lib/eb_verify/`
- **Outputs**: `tests/test_dep_traversal_verifiers.py`; Docker-based integration test that runs verifier inside sandbox
- **Success criteria**: 3-tier discrimination. Cross-repo test.sh runs successfully. Verifier works both inside Docker and with local paths.
- **Scope**: medium (~8-10 files)

### Task P2.6: Mine #25 DB Schema Evolution Candidates
- **Phase**: 2
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/`, target repos with migrations: Django projects (Sentry, Zulip), Rails projects (GitLab CE, Discourse), Go projects (Mattermost)
- **Outputs**: `benchmarks/mined/schema_evolution_candidates.md` — 10-12 candidates. Each: migration PR, affected models, downstream query changes, application code changes.
- **Success criteria**: ≥10 candidates with: (a) schema migration file, (b) corresponding application code changes in same or different repo, (c) clear before/after states.
- **Scope**: medium (~3-5 files)

### Task P2.7: Extract GT and Author #25 DB Schema Tasks
- **Phase**: 2
- **Dependencies**: P2.6, P2.1
- **Agent type**: general-purpose
- **Inputs**: Candidates from P2.6, sandbox templates
- **Outputs**: 8-10 tasks under `benchmarks/feature_delivery/schema-evolution-{NNN}/`: full task package (task.toml, instruction.md, ground_truth.json, checkpoints, Dockerfile)
- **Success criteria**: Schema-valid. Checkpoints: identify schema change impact (0.25) → trace affected queries/models (0.35) → identify application code requiring updates (0.25) → validate migration ordering (0.15). Mix of `dual_repo` and `large_single` strata.
- **Scope**: large (~30-35 files)

### Task P2.8: Verify #25 Tasks
- **Phase**: 2
- **Dependencies**: P2.7, P0.1
- **Agent type**: tdd-guide
- **Inputs**: Tasks from P2.7
- **Outputs**: `tests/test_schema_evolution_verifiers.py`
- **Success criteria**: 3-tier discrimination. Migration ordering checkpoint correctly rejects out-of-order migrations.
- **Scope**: medium (~8-10 files)

### Task P2.9: Mine #5 API Contract Boundary Candidates
- **Phase**: 2
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/`, CNCF repos with API boundaries: gRPC ecosystem, Kubernetes API extensions, Envoy control plane
- **Outputs**: `benchmarks/mined/api_contract_candidates.md` — 10-12 candidates where API change in producer repo broke or required updates in consumer repos.
- **Success criteria**: ≥10 candidates with: (a) breaking API change PR in producer, (b) corresponding fix PRs in ≥1 consumer repo, (c) API contract (proto, OpenAPI, or typed interface) exists.
- **Scope**: medium (~3-5 files)

### Task P2.10: Extract GT and Author #5 API Contract Tasks
- **Phase**: 2
- **Dependencies**: P2.9, P2.1
- **Agent type**: general-purpose
- **Inputs**: Candidates from P2.9, sandbox templates
- **Outputs**: 8-10 tasks under `benchmarks/dependency_management/api-contract-{NNN}/` and `benchmarks/feature_delivery/api-contract-{NNN}/`
- **Success criteria**: Schema-valid. Checkpoints: identify breaking change in contract (0.20) → find all consumer call sites (0.35) → determine required consumer updates (0.30) → verify backward compatibility strategy (0.15). `multi_repo_pattern = "propagate"`. `difficulty_stratum ∈ {dual_repo, multi_repo}`.
- **Scope**: large (~30-35 files)

### Task P2.11: Verify #5 Tasks
- **Phase**: 2
- **Dependencies**: P2.10, P0.1
- **Agent type**: tdd-guide
- **Inputs**: Tasks from P2.10
- **Outputs**: `tests/test_api_contract_verifiers.py`
- **Success criteria**: 3-tier discrimination. Cross-repo consumer detection is correctly verified (finds all consumers, not just first match).
- **Scope**: medium (~8-10 files)

### Task P2.12: Sample Runs for Batch 2 (All 3 Types)
- **Phase**: 2
- **Dependencies**: P2.5, P2.8, P2.11
- **Agent type**: general-purpose
- **Inputs**: 1 task each from #1, #25, #5
- **Outputs**: `results/sample_runs/{dep_traversal,schema_evolution,api_contract}/` — run logs, scores, token counts (baseline + MCP)
- **Success criteria**: All 6 runs complete. Multi-repo sandbox works end-to-end. Score distribution shows meaningful variance between baseline and MCP.
- **Scope**: medium (~8-10 files)

---

## Phase 3: Batch 3 — Deeper Authoring

Task types: **#22 Multi-Repo Refactor Orchestration**, **#13 Dead Code / Feature Flag Necropsy**. These require specialized verification logic beyond the answer verifier.

### Task P3.1: Implement Topological Ordering Verifier
- **Phase**: 3
- **Dependencies**: P0.1
- **Agent type**: tdd-guide
- **Inputs**: `lib/eb_verify/plugins/`, convergence debate (ordering verification spec for #22)
- **Outputs**: `lib/eb_verify/plugins/topological_order.py` — verifier that checks if an agent's proposed refactor ordering is topologically valid (no broken intermediate states in the dependency graph)
- **Success criteria**: Tests with ≥5 fixtures: correct ordering → pass, reversed ordering → fail, partial ordering → partial credit, cyclic proposal → fail, alternative valid ordering → pass.
- **Scope**: medium (~3-5 files)

### Task P3.2: Implement Call Graph Reachability Verifier
- **Phase**: 3
- **Dependencies**: P0.1
- **Agent type**: tdd-guide
- **Inputs**: `lib/eb_verify/plugins/`
- **Outputs**: `lib/eb_verify/plugins/call_graph.py` — verifier that checks if identified dead code is truly unreachable (no remaining callers in the codebase)
- **Success criteria**: Tests with ≥5 fixtures: actually dead code → pass, code with hidden callers → fail, code reachable only through reflection/dynamic dispatch → flagged with lower confidence.
- **Scope**: medium (~3-5 files)

### Task P3.3: Mine #22 Multi-Repo Refactor Candidates
- **Phase**: 3
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/`, target: large OSS refactors with multi-PR chronology (Kubernetes, Envoy, TensorFlow, gRPC ecosystem)
- **Outputs**: `benchmarks/mined/refactor_orchestration_candidates.md` — 8-10 candidates. Each: refactor description, PR sequence, repos involved, dependency ordering constraints.
- **Success criteria**: ≥8 candidates with: (a) ≥2 PRs across ≥2 repos, (b) clear dependency ordering (PR B must land after PR A), (c) intermediate state would break if ordering reversed.
- **Scope**: medium (~3-5 files)

### Task P3.4: Author #22 Multi-Repo Refactor Tasks
- **Phase**: 3
- **Dependencies**: P3.1, P3.3, P2.1
- **Agent type**: general-purpose
- **Inputs**: Candidates from P3.3, topological verifier from P3.1, sandbox templates
- **Outputs**: 5-8 tasks under `benchmarks/technical_debt/refactor-orchestration-{NNN}/`
- **Success criteria**: Schema-valid. Checkpoints: identify all repos requiring changes (0.20) → determine correct change ordering (0.35) → verify no broken intermediate states (0.30) → identify required test updates (0.15). `multi_repo_pattern = "orchestrate"`.
- **Scope**: large (~20-25 files)

### Task P3.5: Verify #22 Tasks
- **Phase**: 3
- **Dependencies**: P3.4
- **Agent type**: tdd-guide
- **Inputs**: Tasks from P3.4, topological verifier
- **Outputs**: `tests/test_refactor_orchestration_verifiers.py`
- **Success criteria**: Topological verifier correctly accepts valid orderings and rejects invalid ones. Multiple valid orderings are accepted (not just the historical one).
- **Scope**: medium (~6-8 files)

### Task P3.6: Mine #13 Dead Code Necropsy Candidates
- **Phase**: 3
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/`, target repos: React, Angular, VS Code, TypeScript (projects with actual cleanup PRs)
- **Outputs**: `benchmarks/mined/dead_code_candidates.md` — 6-8 candidates. Each: cleanup PR, removed code, proof of unreachability.
- **Success criteria**: ≥5 candidates with: (a) actual cleanup/removal PR, (b) code was genuinely dead (no callers), (c) codebase ≥100K LoC (navigation is non-trivial).
- **Scope**: medium (~3-5 files)

### Task P3.7: Author #13 Dead Code Necropsy Tasks
- **Phase**: 3
- **Dependencies**: P3.2, P3.6
- **Agent type**: general-purpose
- **Inputs**: Candidates from P3.6, call graph verifier from P3.2
- **Outputs**: 3-5 tasks under `benchmarks/technical_debt/dead-code-{NNN}/`
- **Success criteria**: Schema-valid. Checkpoints: identify candidate dead code (0.25) → prove unreachability (0.40) → identify safe removal scope (0.25) → flag false positives from dynamic dispatch (0.10). `difficulty_stratum ∈ {large_single, monorepo_cross_package}`.
- **Scope**: medium (~12-15 files)

### Task P3.8: Verify #13 Tasks
- **Phase**: 3
- **Dependencies**: P3.7
- **Agent type**: tdd-guide
- **Inputs**: Tasks from P3.7, call graph verifier
- **Outputs**: `tests/test_dead_code_verifiers.py`
- **Success criteria**: Reachability verifier correctly identifies truly dead code vs code with hidden callers. False positive rate <10%.
- **Scope**: small (~4-6 files)

### Task P3.9: Sample Runs for Batch 3
- **Phase**: 3
- **Dependencies**: P3.5, P3.8
- **Agent type**: general-purpose
- **Inputs**: 1 task each from #22 and #13
- **Outputs**: `results/sample_runs/{refactor_orchestration,dead_code}/`
- **Success criteria**: All runs complete. MCP-mode shows measurable advantage on multi-repo refactor task (cross-repo navigation).
- **Scope**: medium (~5-6 files)

---

## Phase 4: Batch 4 — Conditional/Stretch

Task types: **#9 Incident Investigation (simplified)**, **#4 Configuration Drift**, **#10 Permission/Access Audit** (conditional). Each has a go/no-go mining gate.

### Task P4.1: Mining Validation Sprint — #9 Incident Investigation
- **Phase**: 4
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/`, public postmortem databases (GitHub postmortems, Kubernetes failure stories, AWS post-event summaries)
- **Outputs**: `benchmarks/mined/incident_investigation_candidates.md` — 5-8 candidates. Each: error log/alert, codebase at buggy commit, fix commit, root cause explanation.
- **Success criteria**: **Go/no-go gate**: ≥5 viable candidates where authoring estimated <6hrs each. If <5: skip to P4.4 backup.
- **Scope**: medium (~3-5 files)

### Task P4.2: Author #9 Simplified Incident Tasks
- **Phase**: 4
- **Dependencies**: P4.1 (go decision), P2.1
- **Agent type**: general-purpose
- **Inputs**: Candidates from P4.1, sandbox templates
- **Outputs**: 3-5 tasks under `benchmarks/incident_response/incident-investigation-{NNN}/`
- **Success criteria**: Schema-valid. Checkpoints: identify error source from log (0.20) → trace cross-service root cause (0.40) → identify remediation files (0.25) → propose prevention mechanism (0.15). `multi_repo_pattern = "investigate"`. No event-replay machinery — just codebase at buggy commit + error log.
- **Scope**: medium (~15-18 files)

### Task P4.3: Mining Validation Sprint — #4 Configuration Drift
- **Phase**: 4
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/`, Helm chart repos (bitnami/charts), Terraform module registries, Kustomize-based repos
- **Outputs**: `benchmarks/mined/config_drift_candidates.md` — 5-8 candidates with multi-layer config hierarchies where drift exists.
- **Success criteria**: **Go/no-go gate**: ≥5 candidates with ≥3-layer config hierarchy. Only complex drift (not simple value diff).
- **Scope**: medium (~3-5 files)

### Task P4.4: Author #4 Configuration Drift Tasks
- **Phase**: 4
- **Dependencies**: P4.3 (go decision)
- **Agent type**: general-purpose
- **Inputs**: Candidates from P4.3
- **Outputs**: 3-5 tasks under `benchmarks/platform_engineering/config-drift-{NNN}/`
- **Success criteria**: Schema-valid. Tasks involve ≥3-layer hierarchy (base values → overlay → environment-specific). Checkpoints: identify drift locations (0.30) → trace override chain (0.35) → determine intended vs accidental drift (0.20) → propose reconciliation (0.15).
- **Scope**: medium (~15-18 files)

### Task P4.5: Mining Validation Sprint — #10 Permission/Access Audit
- **Phase**: 4
- **Dependencies**: P0.4
- **Agent type**: general-purpose
- **Inputs**: `scripts/mining/`, target repos: Keycloak, GitLab CE, Harbor, Casbin, OPA
- **Outputs**: `benchmarks/mined/rbac_audit_candidates.md` — mining results from 2-day focused sprint.
- **Success criteria**: **Go/no-go gate**: ≥5 viable tasks with multi-layer policy chains. If <5: fall back to #24 Adversarial Sabotage Detection.
- **Scope**: medium (~3-5 files)

### Task P4.6: Author #10 or #24 Security Tasks
- **Phase**: 4
- **Dependencies**: P4.5 (determines which type)
- **Agent type**: general-purpose
- **Inputs**: Candidates from P4.5 (or planted-bug templates if #24)
- **Outputs**: 3-5 tasks under `benchmarks/security_operations/`
- **Success criteria**: Schema-valid. Provides security_operations suite coverage regardless of which task type was selected.
- **Scope**: medium (~15-18 files)

### Task P4.7: Verify All Phase 4 Tasks
- **Phase**: 4
- **Dependencies**: P4.2, P4.4, P4.6
- **Agent type**: tdd-guide
- **Inputs**: All Phase 4 tasks
- **Outputs**: `tests/test_phase4_verifiers.py`
- **Success criteria**: 3-tier discrimination for all Phase 4 verifiers.
- **Scope**: medium (~8-10 files)

---

## Phase 5: Cross-Cutting Agent Tasks

These tasks span all phases and ensure the benchmark is coherent, calibrated, and documented.

### Task P5.1: Calibration Task Set (15% Single-Repo)
- **Phase**: 5 (can start after Phase 1)
- **Dependencies**: P1.3, P1.8, P1.12
- **Agent type**: general-purpose
- **Inputs**: All authored tasks, PRD (15% calibration requirement)
- **Outputs**: 10-12 calibration tasks under `benchmarks/*/calibration-{NNN}/` — single-repo, small codebase where MCP advantage should be <0.05
- **Success criteria**: Calibration tasks are ≥15% of total task count. Each is single-repo, `difficulty_stratum = "calibration"`. MCP bias check: baseline and MCP scores within 0.05 on sample run.
- **Scope**: large (~25-30 files)

### Task P5.2: MCP Mirror Generation
- **Phase**: 5 (after Phase 2)
- **Dependencies**: P2.4, P2.7, P2.10
- **Agent type**: general-purpose
- **Inputs**: All multi-repo tasks, `scripts/` (MCP mirror prototype), sg-evals mirror format
- **Outputs**: `configs/sg_mirrors/` — Sourcegraph mirror configurations for all multi-repo tasks. Update `tool_access.sourcegraph_mirrors` in each task.toml.
- **Success criteria**: Every multi-repo task has sg-evals mirror references. Mirror configs follow existing sg-evals format. Verified that Sourcegraph can index all referenced repos.
- **Scope**: medium (~15-20 files)

### Task P5.3: Score Distribution Analysis
- **Phase**: 5 (after Phase 3)
- **Dependencies**: P1.5, P1.14, P2.12, P3.9
- **Agent type**: general-purpose
- **Inputs**: All sample run results from `results/sample_runs/`
- **Outputs**: `results/analysis/score_distribution.md` — statistical analysis of score spread across task types, difficulty strata, and tool modes. Histograms, variance analysis, identification of tasks with degenerate distributions.
- **Success criteria**: Score distribution has meaningful spread (std dev >0.15). No task type is all-zero or all-one. Identified tasks with poor discrimination are flagged for revision.
- **Scope**: small (~2-3 files)

### Task P5.4: Cost Model Validation
- **Phase**: 5 (after Phase 2)
- **Dependencies**: P1.5, P1.14, P2.12
- **Agent type**: general-purpose
- **Inputs**: All sample run results (token counts, timing)
- **Outputs**: `results/analysis/cost_model.md` — per-task-type cost estimate (tokens, sandbox minutes, total $). Full benchmark run cost projection at 80-100 tasks.
- **Success criteria**: Cost model covers all task types with measured data. Full benchmark estimated cost is documented. Identifies any prohibitively expensive task types.
- **Scope**: small (~2-3 files)

### Task P5.5: Suite Coverage Audit
- **Phase**: 5 (after Phase 4)
- **Dependencies**: All authoring tasks
- **Agent type**: general-purpose
- **Inputs**: All `benchmarks/*/task.toml` files, PRD suite targets
- **Outputs**: `results/analysis/suite_coverage.md` — actual vs target distribution across: 7 suites, 5 difficulty strata, 4 multi-repo patterns, 3 difficulty levels
- **Success criteria**: All 7 PRD suites have ≥3 tasks. Difficulty stratum distribution within 5% of target (15/25/30/20/10). Total task count ≥68 (minimum from convergence report).
- **Scope**: small (~2-3 files)

### Task P5.6: Documentation Update
- **Phase**: 5 (after Phase 4)
- **Dependencies**: All other tasks
- **Agent type**: doc-updater
- **Inputs**: All produced artifacts, CLAUDE.md, PRD.md
- **Outputs**: Updated `CLAUDE.md` (new key files, conventions), `README.md` (if it exists), `docs/TASK_AUTHORING_GUIDE.md` (how to add new tasks following the established pattern)
- **Success criteria**: CLAUDE.md reflects current project state. Task authoring guide enables a new contributor to author a task without reading convergence reports.
- **Scope**: medium (~3-5 files)

### Task P5.7: Full Benchmark Dry Run
- **Phase**: 5 (final task)
- **Dependencies**: P5.1, P5.2, P5.5
- **Agent type**: general-purpose
- **Inputs**: All authored tasks, full infrastructure
- **Outputs**: `results/dry_run/` — complete benchmark run results for a 10-task sample (2 per batch), all 3 modes (baseline, MCP-only, hybrid)
- **Success criteria**: 30 runs complete without infrastructure failure. Scores captured with full metadata. Results reproducible (re-run variance <0.15 on same task).
- **Scope**: large (~10-15 files)

---

## Dependency Graph Summary

```
Phase 0 (all parallel):
  P0.1 ─────────────────────────────────────────────┐
  P0.2 ──→ P0.5                                     │
  P0.3                                               │
  P0.4 ──────────────────────────────────────────────┤
                                                     │
Phase 1 (3 parallel pipelines after P0):             │
  P1.1 → P1.2 → P1.3 → P1.4 → P1.5                │
  P1.6 → P1.7 → P1.8 → P1.9 → P1.14              uses P0.1
  P1.10 → P1.11 → P1.12 → P1.13 → P1.14           │
                                                     │
Phase 2 (3 parallel pipelines, needs P0.2+P0.5):    │
  P2.1 (sandbox templates)                           │
  P2.2 → P2.3 → P2.4 → P2.5 → P2.12              uses P0.1
  P2.6 → P2.7 → P2.8 → P2.12                       │
  P2.9 → P2.10 → P2.11 → P2.12                     │
                                                     │
Phase 3 (needs Phase 2 sandbox, P0.1):               │
  P3.1 (topo verifier) ──→ P3.4 → P3.5 → P3.9     │
  P3.2 (call graph) ──→ P3.7 → P3.8 → P3.9         │
  P3.3 → P3.4                                        │
  P3.6 → P3.7                                        │
                                                     │
Phase 4 (conditional, needs P0.4):                    │
  P4.1 → P4.2 ──┐                                    │
  P4.3 → P4.4 ──┼→ P4.7                             │
  P4.5 → P4.6 ──┘                                    │
                                                     │
Phase 5 (cross-cutting):                              │
  P5.1 (after Phase 1)                                │
  P5.2 (after Phase 2)                                │
  P5.3 (after Phase 3 sample runs)                    │
  P5.4 (after Phase 2 sample runs)                    │
  P5.5 (after Phase 4)                                │
  P5.6 (after all)                                    │
  P5.7 (final, after P5.1 + P5.2 + P5.5)            │
```

## Task Count Summary

| Phase | Tasks | Parallelism | Estimated Files |
|-------|-------|-------------|-----------------|
| 0: Infrastructure | 5 | 4 parallel + 1 sequential | ~15-25 |
| 1: Batch 1 (Quick Wins) | 14 | 3 parallel pipelines | ~120-160 |
| 2: Batch 2 (Multi-Repo) | 12 | 3 parallel pipelines + 1 shared | ~110-140 |
| 3: Batch 3 (Deep Authoring) | 9 | 2 parallel tracks | ~55-70 |
| 4: Batch 4 (Conditional) | 7 | 3 parallel sprints + 1 verify | ~45-60 |
| 5: Cross-Cutting | 7 | mostly sequential | ~55-75 |
| **Total** | **54 agent tasks** | | **~400-530 files** |

## Critical Path

The longest sequential chain determines minimum wall-clock time:

```
P0.4 → P1.1 → P1.2 → P1.3 → P1.4 → P1.5 → P5.3 → P5.7
       (mining validation → first task pipeline → analysis → dry run)
```

Phases 1-4 batch pipelines are internally sequential (mine → GT → author → verify → run) but the 3 pipelines within each batch are fully parallel. Phase 5 cross-cutting tasks can overlap with later phases.

---

# Testing Plan, Success Criteria, and Go/No-Go Gates

## 1. Per-Task-Type Success Criteria

Each task type must meet ALL of the following before shipping:

### Tier 1 — Core Suite (8 task types)

| # | Task Type | Min Viable Tasks | Max Authoring Cost | Max Token Cost/Run | Max Sandbox Time |
|---|-----------|-----------------|--------------------|--------------------|------------------|
| **#5** | API Contract Boundary Analysis | 6 | 4 hrs/task | $2.50 | 20 min |
| **#22** | Multi-Repo Refactor Orchestration | 4 | 5 hrs/task | $3.00 | 25 min |
| **#1** | Dependency Graph Traversal Races | 8 | 3 hrs/task | $2.00 | 15 min |
| **#12** | Monorepo Package Boundary Referee | 6 | 2 hrs/task | $1.50 | 10 min |
| **#25** | DB Schema Evolution Impact Analysis | 6 | 4 hrs/task | $2.50 | 20 min |
| **#23** | Error Message Provenance Tracing | 8 | 2 hrs/task | $1.50 | 10 min |
| **#18** | Support Code Mapping | 8 | 1.5 hrs/task | $1.00 | 10 min |
| **#13** | Dead Code / Feature Flag Necropsy | 3 | 4 hrs/task | $2.00 | 15 min |

### Tier 2 — Conditional (2 task types + 1 conditional slot)

| # | Task Type | Min Viable Tasks | Max Authoring Cost | Max Token Cost/Run | Max Sandbox Time |
|---|-----------|-----------------|--------------------|--------------------|------------------|
| **#9** | Incident Investigation (simplified) | 3 | 6 hrs/task | $3.00 | 25 min |
| **#4** | Configuration Drift Forensics | 3 | 3 hrs/task | $1.50 | 15 min |
| **#10/#24** | Permission Audit / Sabotage Detection | 3 | 4 hrs/task | $2.00 | 15 min |

### Universal Quality Gates (every task, every type)

**Verification robustness test:**
- Run verifier on 5+ known-good answers and 5+ known-bad answers per task
- False positive rate (bad answer scores > 0.5): < 5%
- False negative rate (good answer scores < 0.5): < 10%
- At least 2 known-bad answers must be "near misses" (partially correct) to test checkpoint granularity

**Score distribution requirement:**
- Run 3+ agent attempts per task (using Sonnet 4.6 baseline mode)
- Score standard deviation across attempts > 0.15
- No task may produce identical scores on all 3 runs
- At least 1 run must score between 0.2 and 0.8 (not degenerate)

**MCP delta measurement:**
- For each task, run: baseline (local tools only) and MCP-enabled (Sourcegraph MCP + local tools)
- Record per task: score delta, tool call count, unique files accessed, retrieval precision, retrieval recall
- Tier 1 task types: aggregated MCP delta must be statistically significant (paired t-test, p < 0.05) across 3+ runs per task, 4+ tasks per type
- Tier 2 task types: MCP delta measured but significance not required for shipping

**Reproducibility:**
- Same task, same agent, same model, 3 runs: score variance < 0.15
- If variance >= 0.15, investigate non-determinism source (sandbox, model temperature, timing) and fix before shipping

**Anti-gaming floor:**
- A trivial agent (lists files, echoes prompt, outputs random content) must score < 0.20 on every task
- A grep-only agent (no semantic understanding, pattern matching only) must score < 0.40 on every task
- If either threshold is exceeded, the task's verifier or checkpoint weights need redesign

---

## 2. Testing Matrix

### Agent x Tool Access x Model Grid

| Dimension | Values |
|-----------|--------|
| **Agents** | Claude Code (primary), OpenHands (secondary validation on 20% sample) |
| **Tool access modes** | `baseline` (local grep/find/read only), `mcp_only` (Sourcegraph MCP, no local search), `hybrid` (agent chooses freely) |
| **Models** | Haiku 4.5 (floor model), Sonnet 4.6 (primary), Opus 4.6 (ceiling — 10% sample only) |
| **Runs per cell** | 3 minimum for reproducibility |

### Run Count Calculation

**Full matrix (Claude Code only):**

| | Haiku 4.5 | Sonnet 4.6 | Opus 4.6 |
|---|-----------|------------|----------|
| baseline | 3 runs x 80 tasks | 3 runs x 80 tasks | 3 runs x 8 tasks |
| mcp_only | 3 runs x 80 tasks | 3 runs x 80 tasks | 3 runs x 8 tasks |
| hybrid | 3 runs x 80 tasks | 3 runs x 80 tasks | 3 runs x 8 tasks |

- Haiku + Sonnet full: 2 models x 3 modes x 80 tasks x 3 runs = **1,440 runs**
- Opus sample: 3 modes x 8 tasks x 3 runs = **72 runs**
- OpenHands validation: 1 model (Sonnet) x 3 modes x 16 tasks x 3 runs = **144 runs**

**Total: 1,656 runs**

### Estimated Cost

| Component | Per-Run Cost | Runs | Subtotal |
|-----------|-------------|------|----------|
| Haiku 4.5 task runs | ~$0.40 avg | 720 | $288 |
| Sonnet 4.6 task runs | ~$1.80 avg | 864 | $1,555 |
| Opus 4.6 task runs | ~$6.00 avg | 72 | $432 |
| OpenHands (Sonnet) | ~$1.80 avg | 144 | $259 |
| Sandbox compute (Daytona) | ~$0.15/run | 1,656 | $248 |
| Sourcegraph MCP API (MCP modes) | ~$0.10/run | 828 | $83 |
| **Total estimated** | | | **$2,865** |

**Budget ceiling: $3,500** for complete benchmark evaluation run.

**Single benchmark run (1 agent, 1 model, 3 modes, 1 run each):**
- Sonnet 4.6: 3 modes x 80 tasks x 1 run = 240 runs x ~$2.05 = **~$492**
- Target: total single-run cost < $500

---

## 3. Go/No-Go Gates

### Gate 0 → 1: Infrastructure Ready

All must pass before any task authoring begins.

| Criterion | Measurement | Threshold |
|-----------|-------------|-----------|
| `eb_verify` smoke test | Run checkpoint runner on 3 synthetic tasks with known scores | All 3 produce expected scores within 0.01 |
| Multi-repo sandbox | Clone 2 repos (one Go, one Python) into `/workspace/` | Total clone+build < 2 minutes, workspace < 50 MB |
| `task.toml` schema validation | Validate 10 example task definitions (one per task type) | All 10 pass schema validation with no warnings |
| Cross-repo `test.sh` | Run a 2-repo integration test in sandbox | Exits 0, both repos accessible, cross-repo file references resolve |
| Dockerfile template | Build sandbox images for baseline, mcp_only, hybrid modes | All 3 build successfully, agent can invoke tools in each mode |

### Gate 1 → 2: Batch 1 Complete

Batch 1 = #23 Error Provenance + #18 Support Code Mapping + #12 Monorepo Boundary.

| Criterion | Measurement | Threshold |
|-----------|-------------|-----------|
| Task count | Tasks passing all universal quality gates | >= 25 across the 3 types (min 6 per type) |
| Verification robustness | FP/FN rates on known-good/bad answers | FP < 5%, FN < 10% for every task |
| Score distribution | StdDev across 3 Sonnet runs per task | > 0.15 for >= 80% of tasks |
| MCP delta | Baseline vs hybrid score difference | Measured for all tasks; directional trend visible (hybrid >= baseline on >= 60% of tasks) |
| Anti-gaming | Trivial agent scores | < 0.20 on all Batch 1 tasks |
| Reproducibility | Score variance on 3 identical runs | < 0.15 for >= 90% of tasks |
| Cost validation | Actual vs estimated token + sandbox cost | Within 2x of per-task estimates in Section 1 |

### Gate 2 → 3: Multi-Repo Validated

Batch 2 = #1 Dependency Graph + #25 DB Schema + #5 API Contract (all multi-repo).

| Criterion | Measurement | Threshold |
|-----------|-------------|-----------|
| Task count | Multi-repo tasks passing quality gates | >= 20 across the 3 types |
| Cross-repo `test.sh` | Reliability across all multi-repo tasks | Success rate >= 95% (no flaky sandbox failures) |
| Sandbox budget | Disk footprint per 2-repo task | < 100 MB workspace, < 200 MB Docker image |
| Sandbox budget | Time from container start to agent ready | < 3 minutes for 2-repo tasks, < 5 minutes for 3-repo |
| MCP delta (multi-repo) | Paired t-test on baseline vs hybrid | p < 0.10 for at least 2 of 3 multi-repo task types |
| Cross-repo ground truth | Second reviewer F1 agreement | >= 0.80 for all multi-repo tasks |

### Gate 3 → 4: Core Suite Ready

All Tier 1 task types authored, validated, and measured.

| Criterion | Measurement | Threshold |
|-----------|-------------|-----------|
| Total task count | Tasks passing all quality gates | >= 60 |
| Suite coverage | PRD suites with >= 3 validated tasks | >= 5 of 7 suites |
| MCP delta significance | Paired t-test per Tier 1 type | p < 0.05 for >= 5 of 8 Tier 1 task types |
| Model discrimination | Mean score Haiku vs Sonnet | Sonnet mean > Haiku mean on >= 70% of tasks |
| Cost model | Full single-run cost (Sonnet, 3 modes, 60+ tasks) | < $500 |
| Reproducibility | Full re-run rank-order consistency | Spearman rho > 0.85 between two complete runs |
| Multi-repo ratio | Tasks requiring 2+ repos | >= 30% of total tasks |
| Calibration check | MCP delta on 15% calibration tasks | < 0.05 average delta (no MCP bias on easy tasks) |

---

## 4. Conditional Task Type Gates

### #9 Incident Investigation — GO/NO-GO Decision

**GO if ALL of:**
- Authoring cost < 6 hours/task (measured on first 3 tasks)
- 3+ tasks pass verification robustness (FP < 5%, FN < 10%) within a 1-week sprint
- Cross-service root cause tracing checkpoint scores show spread (StdDev > 0.15)
- At least 2 of 3 prototype tasks use real public postmortem data (not synthetic)

**NO-GO if ANY of:**
- Authoring cost exceeds 8 hours/task on 2+ of first 3 attempts
- Fewer than 3 tasks pass verification robustness after 1-week sprint
- Verification requires subjective judgment on root cause correctness (no deterministic check possible)

**If NO-GO:** incident_response suite deferred to Phase 2. Reallocate authoring hours to expanding #23 and #18 (which partially cover investigation workflows).

### #4 Configuration Drift Forensics — GO/NO-GO Decision

**GO if ALL of:**
- Tasks scoped to complex hierarchies (Helm/Terraform/Kustomize with 3+ layers)
- MCP delta > 0.10 on at least 2 of 3 prototype tasks
- Verifier can deterministically check drift detection (not just "found a difference" but "found the RIGHT difference in the right layer")

**NO-GO if ANY of:**
- MCP delta < 0.05 on 2+ of 3 tasks (grep is sufficient — confirms MCP-Maximalist concern)
- Ground truth is ambiguous (multiple valid drift interpretations per task)
- Only simple key-value drift tasks are mineable (no complex hierarchy tasks found)

**If NO-GO:** platform_engineering suite covered by extending #22 (refactor orchestration) with CI/CD-adjacent tasks. #4 deferred to Phase 2 with redesigned scope.

### #10 Permission/Access Audit — GO/NO-GO Decision

**GO if ALL of:**
- 2-day mining sprint on Keycloak, GitLab CE, Harbor, Casbin, OPA yields 5+ viable task candidates
- At least 3 of 5 candidates have deterministic ground truth (policy evaluation is mechanically checkable)
- Multi-layer policy chain traversal is required (not single-file grep)

**NO-GO trigger:** < 5 viable tasks after 2-day mining sprint.

**If NO-GO:** Activate **#24 Adversarial Sabotage Detection** as backup for security_operations coverage:
- Plant known bugs in real OSS repos (deterministic GT guaranteed)
- 3-5 tasks, authoring cost ~3 hrs/task (lower than mining-dependent types)
- security_operations suite ships either way

---

## 5. Quality Assurance Framework

### Ground Truth Validation

| Check | Method | Threshold | Frequency |
|-------|--------|-----------|-----------|
| Independent ground truth | Second reviewer (different agent or human) independently produces ground truth | F1 agreement > 0.80 with primary ground truth | Every task |
| Cross-backend validation | Run curator with local-only AND separate search backend | F1 agreement > 0.80 between backends | Every task |
| Deterministic layer coverage | AST/import parsing verifies all structural claims | 100% of deterministic claims verified | Every task |
| Solve-verification | Different model (Haiku if primary is Sonnet) attempts task using ONLY curated context | Model achieves > 0.60 score using only ground truth context | Every task |

### Verifier Mutation Testing

Inject known errors into agent outputs and verify the verifier catches them:

| Mutation Type | Injection Method | Detection Target |
|---------------|-----------------|------------------|
| Missing file | Remove 1 required file from output | Verifier must score < 0.50 |
| Wrong file | Replace correct file with unrelated file from same repo | Verifier must score < 0.40 |
| Partial fix | Apply fix to repo A but not repo B in multi-repo task | Score between 0.25-0.60 (partial credit, not full) |
| Cosmetic-only change | Whitespace/comment-only diff | Score < 0.20 |
| Correct but incomplete | All required files but missing 1 checkpoint | Score reflects missing checkpoint weight |

**Aggregate requirement:** Verifier catches > 90% of injected mutations (scores within expected range).

Run mutation testing on 100% of tasks before shipping. Minimum 5 mutations per task.

### Anti-Gaming Checks

| Agent Type | Behavior | Max Allowable Score |
|------------|----------|-------------------|
| Null agent | Returns empty output | 0.00 |
| Echo agent | Echoes back the prompt/instructions | 0.10 |
| Random-file agent | Lists random files from repo | 0.15 |
| Grep-all agent | Greps for keywords from prompt, returns all matches | 0.35 |
| Copy-paste agent | Copies existing code without modification | 0.20 |

If any trivial agent exceeds its threshold on any task, that task is flagged for verifier redesign. The task does NOT ship until the verifier is fixed.

### Calibration Analysis

The 15% calibration tasks (single-repo, small codebase, straightforward navigation) serve as MCP bias detectors:

- **Expected behavior:** MCP delta < 0.05 on calibration tasks (MCP provides negligible advantage on easy tasks)
- **If MCP delta > 0.10 on calibration tasks:** Investigation required — either the task isn't actually easy, or the baseline tooling is artificially constrained
- **Calibration tasks must still meet all universal quality gates** (verification robustness, score spread, reproducibility)
- **Distribution:** At least 2 calibration tasks per Tier 1 task type (total: ~12 calibration tasks out of 80)

### Staleness Detection

| Check | Frequency | Action on Failure |
|-------|-----------|-------------------|
| Clone all pinned repo versions | Monthly CI job | Flag broken repos, attempt alternate mirror, escalate if unfixable |
| Build/test all pinned repos | Monthly CI job | Pin to last-known-good commit if HEAD breaks |
| Verify external data sources (OSV/NVD) | Monthly | Update CVE data if stale, flag affected tasks |
| Sourcegraph MCP endpoint health | Weekly CI job | Alert if API changes affect MCP-mode tasks |
| Docker base image compatibility | Monthly | Rebuild sandbox images, verify agent tools still work |

**Staleness budget:** No more than 5% of tasks may be in "stale" state at any time. If > 5% break, pause new task authoring and fix staleness first.

---

## 6. Benchmark-Level Success Criteria

The benchmark as a whole succeeds — and is ready for publication — when ALL of the following hold:

### Task Quality

| Criterion | Threshold |
|-----------|-----------|
| Total tasks passing all per-task quality gates | >= 80 |
| All 7 PRD suites have validated tasks | >= 3 tasks per suite (or documented NO-GO with backup coverage) |
| Multi-repo tasks (2+ repos) | >= 30% of total tasks (>= 24 of 80) |
| Monorepo cross-package tasks | >= 10% of total tasks (>= 8 of 80) |
| Difficulty distribution | 25-35% medium, 45-55% hard, 15-25% expert |

### MCP Signal

| Criterion | Threshold |
|-----------|-----------|
| MCP delta statistically significant (p < 0.05) | >= 5 of 8 Tier 1 task types |
| Hybrid mode >= baseline on average | >= 70% of tasks |
| Calibration tasks MCP delta | < 0.05 average (no bias) |
| At least 1 task type with MCP delta > 0.20 | Yes (validates MCP as meaningful tool, not noise) |

### Discrimination

| Criterion | Threshold |
|-----------|-----------|
| Model tier discrimination | Sonnet > Haiku on >= 70% of tasks |
| Score range across all tasks | Mean score between 0.20-0.80 (not floor/ceiling) |
| Per-task-type score spread | StdDev > 0.15 for >= 80% of tasks |
| Opus ceiling check (10% sample) | Opus > Sonnet on >= 50% of sampled tasks |

### Reproducibility

| Criterion | Threshold |
|-----------|-----------|
| Per-task score variance (3 runs) | < 0.15 for >= 90% of tasks |
| Full benchmark rank-order consistency | Spearman rho > 0.85 between 2 complete runs |
| Sandbox reliability | < 2% of runs fail due to infrastructure (not agent) |

### Cost

| Criterion | Threshold |
|-----------|-----------|
| Single benchmark run (1 agent, 1 model, 3 modes) | < $500 |
| Full evaluation matrix (all agents, models, modes) | < $3,500 |
| Per-task average cost (Sonnet, single run) | < $2.50 |
| Per-task average sandbox time | < 20 minutes |

### Publication Readiness

| Criterion | Threshold |
|-----------|-----------|
| Verifier mutation testing pass rate | > 90% across all tasks |
| Anti-gaming check pass rate | 100% (no task allows trivial agent > threshold) |
| Ground truth F1 agreement (independent reviewer) | > 0.80 for 100% of tasks |
| Staleness: all pinned repos clone and build | 100% at time of publication |
| Documentation: task authoring guide, scoring methodology, reproduction instructions | Complete and reviewed |

---

## Appendix A: Debate Provenance

Full convergence debate report: `.brainstorm/da5fbe049382/convergence_debate_report.md`
Brainstorm session (30 ideas): `.brainstorm/da5fbe049382/report.md`
Individual idea descriptions: `.brainstorm/da5fbe049382/ideas/001.md` through `030.md`

### Debate Participants
- **MCP-Maximalist**: Optimized for Sourcegraph MCP signal gap
- **Enterprise-Realist**: Optimized for enterprise workflow frequency
- **Feasibility-First**: Optimized for ground truth quality and shipping speed

### Key Debate Moments
- Feasibility-First upgraded #22 from reject to accept after deterministic ordering verification was proposed
- MCP-Maximalist dropped #30 after acknowledging subjective verification
- Enterprise-Realist conceded #13 after recognizing absence-detection as unique cognitive axis
- All three converged on reframing #18 as navigation-weighted "Code Mapping"
