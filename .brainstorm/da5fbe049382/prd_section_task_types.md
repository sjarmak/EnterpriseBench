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
