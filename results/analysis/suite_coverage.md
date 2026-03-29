# Suite Coverage Audit

**Date:** 2026-03-28
**Source:** All `task.toml` files in `benchmarks/` (excluding `mined/`)

---

## Summary

| Metric | Count |
|--------|-------|
| Total task.toml files | 100 |
| Example/template tasks | 2 (`chain_example`, `event_replay_example`) |
| **Real tasks** | **98** |
| PRD target | 79 (range 71-97) |

**Status: 98 tasks exceeds the PRD target of 79 and the upper bound of 97.** The task count is slightly over the max range, but this is acceptable if quality is maintained.

---

## 1. Suite Distribution

PRD requires all 7 suites have >= 3 tasks.

| Suite | Actual | PRD Min (>=3) | Status |
|-------|--------|---------------|--------|
| customer_escalation | 22 | 3 | PASS |
| dependency_management | 21 | 3 | PASS |
| feature_delivery | 23 | 3 | PASS |
| incident_response | 7 | 3 | PASS |
| platform_engineering | 4 | 3 | PASS |
| security_operations | 7 | 3 | PASS |
| technical_debt | 14 | 3 | PASS |
| **Total** | **98** | | |

All 7 suites meet the minimum threshold. Distribution is heavily weighted toward `customer_escalation`, `dependency_management`, and `feature_delivery` (66 of 98 = 67%).

---

## 2. Difficulty Stratum Distribution

PRD targets: 15% calibration, 25% large single, 30% dual, 20% multi (3-5 repo), 10% monorepo.

Note: The data contains variant stratum names:
- `tri_repo` (4 tasks) maps to `multi_repo` per PRD (3-5 repo category)
- `monorepo_cross_pkg` (2 tasks) maps to `monorepo_cross_package`
- **No `calibration` stratum exists** in any task

| Stratum (normalized) | Actual | Actual % | PRD Target % | Target Count (of 79) | Gap |
|----------------------|--------|----------|--------------|----------------------|-----|
| calibration | **0** | **0.0%** | 15% | ~12 | **-12 (MISSING)** |
| large_single | 58 | 59.2% | 25% | ~20 | +38 (OVER) |
| dual_repo | 13 | 13.3% | 30% | ~24 | -11 (UNDER) |
| multi_repo (incl. tri_repo) | 15 | 15.3% | 20% | ~16 | -1 (NEAR) |
| monorepo_cross_package (incl. monorepo_cross_pkg) | 12 | 12.2% | 10% | ~8 | +4 (OVER) |
| **Total** | **98** | **100%** | 100% | 79 | |

### Critical Gaps

1. **Calibration stratum is completely absent (0 of ~12 target).** This is the most critical gap. The PRD requires 15% calibration tasks (single-repo, MCP bias check). Not a single task has `difficulty_stratum = "calibration"`.

2. **large_single is massively over-represented (59% vs 25% target).** 58 tasks vs ~20 target. Many of these may actually be appropriate for recategorization as calibration tasks (single-repo, simpler scope).

3. **dual_repo is significantly under-represented (13% vs 30% target).** Only 13 tasks vs ~24 target. Needs ~11 more dual-repo tasks.

---

## 3. Difficulty Level Distribution

PRD targets: 30% medium, 50% hard, 20% expert.

| Difficulty | Actual | Actual % | PRD Target % | Target Count (of 79) | Gap |
|------------|--------|----------|--------------|----------------------|-----|
| medium | 24 | 24.5% | 30% | ~24 | 0 (ON TARGET, % slightly low) |
| hard | 58 | 59.2% | 50% | ~40 | +18 (OVER) |
| expert | 16 | 16.3% | 20% | ~16 | 0 (ON TARGET, % slightly low) |
| **Total** | **98** | **100%** | 100% | 79 | |

The absolute counts for medium and expert are on target, but the proportions are skewed because hard is over-represented (59% vs 50%). This is a minor imbalance; adding calibration tasks (likely medium difficulty) would naturally correct the proportions.

---

## 4. Multi-Repo Pattern Distribution

PRD defines 4 atomic patterns: propagate, investigate, enforce, orchestrate.

| Pattern | Actual | % of known |
|---------|--------|-----------|
| investigate | 42 | 58.3% |
| enforce | 14 | 19.4% |
| propagate | 8 | 11.1% |
| orchestrate | 8 | 11.1% |
| **unknown/missing** | **26** | — |
| **Total** | **98** | |

### Issues

1. **26 tasks (26.5%) have no multi_repo_pattern set.** These are all from the tasks without `task_type` (CCX legacy tasks, example tasks, standalone feature_delivery tasks). The `[metadata]` section is missing or does not include `multi_repo_pattern`.

2. **investigate is heavily dominant (58% of known patterns).** This makes sense for single-repo tasks (error tracing, incident investigation, dead code analysis), but the distribution should be validated against PRD intent.

---

## 5. Task Type Distribution

PRD defines 10 task types with specific count targets.

| # | Task Type | PRD Target | Actual | Status |
|---|-----------|-----------|--------|--------|
| 1 | api_contract | 8-10 | 8 | PASS (at minimum) |
| 2 | refactor_orchestration | 5-8 | 8 | PASS (at maximum) |
| 3 | dependency_graph | 10-12 | 12 | PASS (at maximum) |
| 4 | monorepo_boundary | 8-10 | 10 | PASS (at maximum) |
| 5 | db_schema_evolution | 8-10 | 10 | PASS (at maximum) |
| 6 | error_provenance | 10-12 | 10 | PASS (at minimum) |
| 7 | support_code_mapping | 10-15 | 12 | PASS |
| 8 | dead_code_necropsy | 3-5 | 5 | PASS (at maximum) |
| 9 | incident_investigation | 3-5 | 8 | **OVER** (3 are rbac-audit, 1 is dedicated) |
| 10 | config_drift | 3-5 | 4 | PASS |
| — | **missing/unknown** | 0 | **11** | **NEEDS FIX** |

### Issues

1. **11 tasks have no task_type.** These are legacy CSB tasks (ccx-*, ansible-*, ceph-*, beam-*) and standalone feature_delivery tasks (aspnetcore-*, bustub-*, camel-*). They need `task_type` assigned.

2. **incident_investigation has 8 tasks but target is 3-5.** The 4 rbac-audit tasks are classified as `incident_investigation` in task_type but live in `security_operations` suite. These may need their own task type or reclassification.

---

## 6. Suite x Stratum Cross-Tabulation

| Suite | calibration | large_single | dual_repo | multi_repo* | monorepo** | Total |
|-------|-------------|--------------|-----------|-------------|------------|-------|
| customer_escalation | 0 | 22 | 0 | 0 | 0 | 22 |
| dependency_management | 0 | 1 | 9 | 11 | 0 | 21 |
| feature_delivery | 0 | 13 | 0 | 0 | 10 | 23 |
| incident_response | 0 | 5 | 2 | 0 | 0 | 7 |
| platform_engineering | 0 | 4 | 0 | 0 | 0 | 4 |
| security_operations | 0 | 7 | 0 | 0 | 0 | 7 |
| technical_debt | 0 | 6 | 2 | 4 | 2 | 14 |

\* Includes tri_repo. \** Includes monorepo_cross_pkg.

### Key observations:
- **customer_escalation** (22 tasks) is 100% large_single -- no multi-repo tasks
- **feature_delivery** has good monorepo coverage but no dual_repo or multi_repo
- **platform_engineering** and **security_operations** are 100% large_single
- Only **dependency_management** and **technical_debt** have multi-repo diversity

---

## 7. Suite x Difficulty Cross-Tabulation

| Suite | medium | hard | expert | Total |
|-------|--------|------|--------|-------|
| customer_escalation | 7 | 13 | 2 | 22 |
| dependency_management | 5 | 11 | 5 | 21 |
| feature_delivery | 6 | 12 | 5 | 23 |
| incident_response | 0 | 7 | 0 | 7 |
| platform_engineering | 2 | 2 | 0 | 4 |
| security_operations | 1 | 6 | 0 | 7 |
| technical_debt | 3 | 7 | 4 | 14 |

### Issues:
- **incident_response** has no medium or expert tasks -- all 7 are hard
- **platform_engineering** has no expert tasks
- **security_operations** has no expert tasks and only 1 medium

---

## 8. Naming Inconsistencies

| Issue | Details |
|-------|---------|
| Stratum variant: `tri_repo` | Used by 4 refactor-orchestration tasks. PRD uses `multi_repo` for 3-5 repos |
| Stratum variant: `monorepo_cross_pkg` | Used by 2 refactor-orchestration tasks. Standard is `monorepo_cross_package` |
| Missing `task_type` | 11 tasks (see Section 5) |
| Missing `multi_repo_pattern` | 26 tasks (see Section 4) |

---

## 9. Recommendations

### Critical (must fix)

1. **Add calibration tasks.** The PRD requires ~12 calibration tasks (15% of target). These should be single-repo, lower-complexity tasks designed as MCP bias checks. Consider reclassifying some simpler `large_single` tasks or creating new calibration-specific tasks.

2. **Assign `task_type` to all 11 tasks missing it.** Map legacy CCX tasks and standalone tasks to one of the 10 defined types:
   - `ccx-dep-trace-106` -> `dependency_graph`
   - `ccx-compliance-052`, `ccx-compliance-053` -> new type or `rbac_audit`
   - `ccx-incident-032` -> `incident_investigation`
   - `ansible-*`, `ceph-*` -> `incident_investigation` or new type
   - `beam-pipeline-builder-refac-001` -> `refactor_orchestration`
   - `aspnetcore-code-review-001`, `bustub-*`, `camel-*` -> needs new type or existing fit

3. **Normalize stratum names.** Rename `tri_repo` -> `multi_repo` and `monorepo_cross_pkg` -> `monorepo_cross_package` for consistency.

### High (should fix)

4. **Increase dual_repo tasks.** Currently 13 vs ~24 target (30% of 79). Need ~11 more dual-repo tasks, especially in suites that are 100% large_single (customer_escalation, platform_engineering, security_operations).

5. **Assign `multi_repo_pattern` to all 26 tasks missing it.** Even single-repo tasks should have a pattern annotation for analysis.

6. **Reconsider rbac-audit task_type.** The 4 rbac-audit tasks are typed as `incident_investigation` but live in `security_operations`. This inflates incident_investigation count above the 3-5 target. Consider a separate `rbac_audit` or `security_audit` type.

### Medium (nice to have)

7. **Add difficulty variety to incident_response.** All 7 tasks are hard -- add 1-2 medium tasks.

8. **Add expert tasks to platform_engineering and security_operations.** Both suites lack expert difficulty.

9. **Add multi-repo tasks to customer_escalation.** All 22 tasks are large_single. Real customer escalations often span multiple services.

---

## 10. Tasks Missing `task_type` (Full List)

| Task ID | Suite | Path |
|---------|-------|------|
| ccx-dep-trace-106 | dependency_management | benchmarks/dependency_management/ccx-dep-trace-106/ |
| aspnetcore-code-review-001 | feature_delivery | benchmarks/feature_delivery/aspnetcore-code-review-001/ |
| bustub-hyperloglog-impl-001 | feature_delivery | benchmarks/feature_delivery/bustub-hyperloglog-impl-001/ |
| camel-routing-arch-001 | feature_delivery | benchmarks/feature_delivery/camel-routing-arch-001/ |
| ansible-abc-imports-fix-001 | incident_response | benchmarks/incident_response/ansible-abc-imports-fix-001/ |
| ansible-galaxy-tar-regression-prove-001 | incident_response | benchmarks/incident_response/ansible-galaxy-tar-regression-prove-001/ |
| ccx-incident-032 | incident_response | benchmarks/incident_response/ccx-incident-032/ |
| ccx-compliance-052 | security_operations | benchmarks/security_operations/ccx-compliance-052/ |
| ccx-compliance-053 | security_operations | benchmarks/security_operations/ccx-compliance-053/ |
| ceph-rgw-auth-secure-001 | security_operations | benchmarks/security_operations/ceph-rgw-auth-secure-001/ |
| beam-pipeline-builder-refac-001 | technical_debt | benchmarks/technical_debt/beam-pipeline-builder-refac-001/ |
