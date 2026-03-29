# Legacy CSB Task Debt Assessment

Generated: 2026-03-28

## Overview

13 legacy tasks were assessed against the current EnterpriseBench standards defined in `schemas/task.schema.json` and the reference `EXAMPLE_TASK.toml`. The assessment covers schema compliance, ground truth completeness, verifier quality, task type fit, and migration effort.

### Current Standards Checklist

A fully compliant task has:
1. `task.toml` validates against `schemas/task.schema.json`
2. `task_type` field set (one of 10 types)
3. `difficulty_stratum` set at top level
4. `ground_truth` section with `required_files` and `sufficient_files`
5. `ground_truth.json` file (separate from task.toml)
6. Multiple weighted checkpoints (2-5) with verifier scripts in `checks/`
7. `tool_access` with `mcp_benefit_rationale`
8. Pinned `rev` (not `HEAD`)
9. Real repo URLs (not `github.com/unknown/repo`)

## Per-Task Assessment

### Summary Table

| # | Task ID | Suite | Has GT in TOML | Has GT.json | Has Checks | Fits Type | Schema Issues | Effort | Recommendation |
|---|---------|-------|----------------|-------------|------------|-----------|---------------|--------|----------------|
| 1 | `chain_example` | dependency_management | No | No | Yes (4) | dependency_graph | Missing task_type, difficulty_stratum, ground_truth, tool_access | **Example only** | **Retire** |
| 2 | `event_replay_example` | incident_response | No | No | No | incident_investigation | Missing task_type, difficulty_stratum, ground_truth, tool_access, checkpoints reference nonexistent scripts | **Example only** | **Retire** |
| 3 | `ansible-abc-imports-fix-001` | incident_response | Partial | No | No | refactor_orchestration | Missing task_type, rev=HEAD, single checkpoint, no checks/ dir, no ground_truth.json | Medium | **Migrate** |
| 4 | `ansible-galaxy-tar-regression-prove-001` | incident_response | Partial | No | No | error_provenance | Missing task_type, rev=HEAD, url=unknown/repo, single checkpoint, no checks/ dir | Medium | **Migrate** |
| 5 | `aspnetcore-code-review-001` | feature_delivery | Partial | No | No | api_contract | Missing task_type, rev=HEAD, url malformed, single checkpoint, no checks/ dir | Medium | **Migrate** |
| 6 | `beam-pipeline-builder-refac-001` | technical_debt | Minimal | No | No | refactor_orchestration | Missing task_type, rev=HEAD, no required_files in GT, single checkpoint, no checks/ dir | Medium | **Migrate** |
| 7 | `bustub-hyperloglog-impl-001` | feature_delivery | Partial | No | No | N/A (algorithm impl) | Missing task_type, rev=HEAD, url=unknown/repo, references TheAgentCompany env, single checkpoint | High | **Retire** |
| 8 | `camel-routing-arch-001` | feature_delivery | Partial | No | No | api_contract | Missing task_type, rev=HEAD, single checkpoint, no checks/ dir | Medium | **Migrate** |
| 9 | `ccx-compliance-052` | security_operations | Partial | No | No | config_drift | Missing task_type, single checkpoint, no checks/ dir. Has sg-evals mirror. | Low | **Migrate** |
| 10 | `ccx-compliance-053` | security_operations | Partial | No | No | config_drift | Missing task_type, single checkpoint, no checks/ dir. Has sg-evals mirror. | Low | **Migrate** |
| 11 | `ccx-dep-trace-106` | dependency_management | Partial | No | No | dependency_graph | Missing task_type, single checkpoint, no checks/ dir. Has sg-evals mirror. Prompt says GCC but repo is llvm-project. | Medium | **Migrate** (fix repo mismatch) |
| 12 | `ccx-incident-032` | incident_response | Partial | No | No | incident_investigation | Missing task_type, single checkpoint, no checks/ dir. Has sg-evals mirror. | Low | **Migrate** |
| 13 | `ceph-rgw-auth-secure-001` | security_operations | Minimal | No | No | config_drift | Missing task_type, rev=HEAD, no required_files in GT, single checkpoint, no checks/ dir | Medium | **Migrate** |

### Detailed Per-Task Notes

#### 1. chain_example (RETIRE)

- **Location**: `benchmarks/chain_example/`
- **Purpose**: Example/template for chain session type. Not a real benchmark task.
- **Issues**: Not under any suite directory. Uses `[[sessions]]` array which is not in the schema (the schema has no `sessions` field). Has a `[simulation]` section not in schema.
- **Verdict**: Keep as documentation reference only. Move to `benchmarks/EXAMPLE_CHAIN_TASK.toml` (which already exists and is better). Delete the directory.

#### 2. event_replay_example (RETIRE)

- **Location**: `benchmarks/event_replay_example/`
- **Purpose**: Example/template for event_replay session type. Not a real benchmark task.
- **Issues**: Not under any suite directory. Checkpoint verifiers reference `checks/` scripts that don't exist. Has event files (events.jsonl, oracle_actions.jsonl) which are useful as examples.
- **Verdict**: The `EXAMPLE_TASK.toml` and `EXAMPLE_CHAIN_TASK.toml` already exist at the benchmarks root. Move event replay example data to a similar pattern or delete. The event files could be preserved as reference.

#### 3. ansible-abc-imports-fix-001 (MIGRATE - Medium)

- **Origin**: csb_sdlc_fix
- **Quality**: Good prompt, good ground_truth.required_files, has csb_lineage. Migration status = metadata_merged.
- **Gaps**: No `task_type`, rev=HEAD (needs pinning), single monolithic checkpoint (needs 2-3 granular ones), no `checks/` scripts, no `ground_truth.json`, missing `mcp_benefit_rationale`.
- **Better fit**: `technical_debt` suite with `refactor_orchestration` type (it's an import modernization refactor).

#### 4. ansible-galaxy-tar-regression-prove-001 (MIGRATE - Medium)

- **Origin**: csb_sdlc_debug
- **Quality**: Good prompt (find-and-prove regression test). Has ground_truth.required_files.
- **Gaps**: `url = "github.com/unknown/repo"` (should be `github.com/ansible/ansible`), rev=HEAD, no task_type, single checkpoint, no checks/, no ground_truth.json.
- **Better fit**: `incident_response` with `error_provenance` type (regression investigation).

#### 5. aspnetcore-code-review-001 (MIGRATE - Medium)

- **Origin**: csb_sdlc_test
- **Quality**: Excellent prompt (structured code review with JSON output). Good ground_truth.
- **Gaps**: `url = "github.com/aspnetcore"` (malformed, should be `github.com/dotnet/aspnetcore`), rev=HEAD, no task_type, single checkpoint, no checks/.
- **Better fit**: `feature_delivery` is okay. Type could be `api_contract` (review of component API).

#### 6. beam-pipeline-builder-refac-001 (MIGRATE - Medium)

- **Origin**: csb_sdlc_refactor
- **Quality**: Good prompt but no ground_truth.required_files (only tiers=["curator"]).
- **Gaps**: rev=HEAD, no task_type, single checkpoint, no checks/, no GT files, missing ground_truth.required_files.
- **Better fit**: `technical_debt` with `refactor_orchestration` type. Needs GT files populated.

#### 7. bustub-hyperloglog-impl-001 (RETIRE)

- **Origin**: csb_sdlc_feature
- **Quality**: Prompt references TheAgentCompany GitLab (`the-agent-company.com:8929`) which is an external environment not available in EnterpriseBench sandboxes. URL is `github.com/unknown/repo`.
- **Issues**: Cannot work without TheAgentCompany infrastructure. Pure algorithm implementation task doesn't fit EnterpriseBench's focus on codebase understanding/context gathering.
- **Verdict**: Does not fit the benchmark's mission. Retire.

#### 8. camel-routing-arch-001 (MIGRATE - Medium)

- **Origin**: csb_sdlc_design
- **Quality**: Good architectural understanding prompt. Solid ground_truth.required_files.
- **Gaps**: rev=HEAD, no task_type, single checkpoint, no checks/. Output goes to `/logs/agent/solution.md` (non-standard path).
- **Better fit**: Could stay in `feature_delivery` or move to `technical_debt`. Type: `api_contract` (architecture tracing).

#### 9. ccx-compliance-052 (MIGRATE - Low)

- **Origin**: csb_org_compliance
- **Quality**: Good prompt, has Sourcegraph mirror, pinned rev (v1.31.2), solid ground_truth.required_files.
- **Gaps**: No task_type, single checkpoint, no checks/. Otherwise close to compliant.
- **Better fit**: `security_operations` is correct. Type: `config_drift` (compliance audit).

#### 10. ccx-compliance-053 (MIGRATE - Low)

- **Origin**: csb_org_compliance
- **Quality**: Good prompt, has Sourcegraph mirror, pinned rev, solid ground_truth.required_files.
- **Gaps**: Same as ccx-compliance-052 — no task_type, single checkpoint, no checks/.
- **Better fit**: Same as above.

#### 11. ccx-dep-trace-106 (MIGRATE - Medium)

- **Origin**: csb_org_crossrepo
- **Quality**: Good prompt about GCC pass registration. Has Sourcegraph mirror and pinned rev.
- **Gaps**: No task_type, single checkpoint, no checks/. **Major issue**: prompt is about GCC files (`gcc/passes.def`, `gcc/tree-ssa-dce.cc`) but repo URL points to `sg-evals/llvm-project`. Ground truth references `gcc/` paths within `llvm-project` repo — this is likely a repo mismatch bug from CSB.
- **Better fit**: `dependency_management` with `dependency_graph` type.

#### 12. ccx-incident-032 (MIGRATE - Low)

- **Origin**: csb_org_incident
- **Quality**: Good prompt (Envoy connection pool exhaustion debugging). Has Sourcegraph mirror, pinned rev, solid ground_truth.required_files.
- **Gaps**: No task_type, single checkpoint, no checks/.
- **Better fit**: `incident_response` with `incident_investigation` type. Nearly compliant.

#### 13. ceph-rgw-auth-secure-001 (MIGRATE - Medium)

- **Origin**: csb_sdlc_secure
- **Quality**: Good prompt (security audit). But ground_truth has only `tiers = ["curator"]` with no required_files.
- **Gaps**: rev=HEAD, no task_type, single checkpoint, no checks/, no GT files. Artifact says `code_patch` but task produces `security_assessment`.
- **Better fit**: `security_operations` is correct. Type: `config_drift` (security audit). Needs GT populated.

## Migration Plan

### Retire (3 tasks)

| Task | Reason |
|------|--------|
| `chain_example` | Template only, superseded by `EXAMPLE_CHAIN_TASK.toml` |
| `event_replay_example` | Template only, can be folded into example files |
| `bustub-hyperloglog-impl-001` | Depends on TheAgentCompany infra; pure algorithm impl doesn't fit EB mission |

**Action**: Archive to `benchmarks/_archived/` or delete entirely.

### Migrate (10 tasks)

#### Priority 1 — Low Effort (3 tasks)

These already have pinned revs, Sourcegraph mirrors, and solid ground truth. Just need `task_type`, split checkpoints, and `checks/` scripts.

| Task | Key Changes |
|------|-------------|
| `ccx-compliance-052` | Add task_type=config_drift, split into 2-3 checkpoints, create checks/ scripts |
| `ccx-compliance-053` | Same as above |
| `ccx-incident-032` | Add task_type=incident_investigation, split checkpoints, create checks/ scripts |

**Estimated effort per task**: ~1 hour

#### Priority 2 — Medium Effort (7 tasks)

These need rev pinning, repo URL fixes, ground truth population, and checkpoint creation.

| Task | Key Changes |
|------|-------------|
| `ansible-abc-imports-fix-001` | Pin rev, add task_type, split checkpoints, create checks/, consider moving to technical_debt |
| `ansible-galaxy-tar-regression-prove-001` | Fix URL (unknown/repo -> ansible/ansible), pin rev, add task_type=error_provenance, split checkpoints |
| `aspnetcore-code-review-001` | Fix URL (aspnetcore -> dotnet/aspnetcore), pin rev, add task_type, split checkpoints |
| `beam-pipeline-builder-refac-001` | Pin rev, add task_type=refactor_orchestration, populate GT required_files, split checkpoints |
| `camel-routing-arch-001` | Pin rev, add task_type, fix output path, split checkpoints |
| `ccx-dep-trace-106` | Fix repo mismatch (GCC prompt vs llvm-project repo), add task_type=dependency_graph, split checkpoints |
| `ceph-rgw-auth-secure-001` | Pin rev, add task_type, populate GT required_files, fix artifact type, split checkpoints |

**Estimated effort per task**: ~2-3 hours

## Common Migration Steps (all 10 tasks)

1. Add `task_type` field to `[task]`
2. Add `mcp_benefit_rationale` to `[tool_access]`
3. Split single checkpoint into 2-3 weighted checkpoints
4. Create `checks/` directory with verifier shell scripts
5. Create `ground_truth.json` file (extract from task.toml GT + expand)
6. Add `sufficient_files` to ground truth where missing
7. Pin `rev` to specific commit/tag (replace `HEAD`)
8. Fix malformed repo URLs
9. Ensure `csb_lineage.migration_status` progresses to `verified`

## Estimated Total Effort

- **Retire**: 3 tasks, ~30 minutes (move/delete + update any references)
- **Low-effort migrations**: 3 tasks x ~1 hour = ~3 hours
- **Medium-effort migrations**: 7 tasks x ~2.5 hours = ~17.5 hours
- **Total**: ~21 hours of migration work

## Priority Order

1. `ccx-incident-032` — closest to compliant, validates migration workflow
2. `ccx-compliance-052` — low effort, has sg-evals mirror
3. `ccx-compliance-053` — low effort, has sg-evals mirror
4. `ansible-abc-imports-fix-001` — real-world Python refactoring, good diversity
5. `camel-routing-arch-001` — good architectural understanding task, solid GT
6. `aspnetcore-code-review-001` — unique code review format, C# diversity
7. `ccx-dep-trace-106` — needs repo mismatch fix but valuable task
8. `ansible-galaxy-tar-regression-prove-001` — unique prove-it format
9. `ceph-rgw-auth-secure-001` — needs GT population
10. `beam-pipeline-builder-refac-001` — needs GT population, Java diversity
11. Retire `chain_example`, `event_replay_example`, `bustub-hyperloglog-impl-001`
