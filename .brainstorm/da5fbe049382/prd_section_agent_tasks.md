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
