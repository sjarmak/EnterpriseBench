# CSB Bug Audit Report

**Generated:** 2026-03-28
**Auditor:** a1-bug-auditor agent
**Source:** ~/CodeScaleBench/ (275 canonical tasks, 20 suite dirs)

---

## Verifier Quality Distribution Summary

| Classification | Count | Eligible for Core Benchmark |
|---|---|---|
| `core_ready` | 156 | Yes |
| `conditional` | 316 | Yes (if fills critical gap) |
| `extension_only` | 0 | No |
| **Total in labels** | **472** | — |

**Note:** verifier_quality_labels.json covers 472 tasks (275 canonical + 197 in backup/trimmed suites). All 275 canonical tasks appear in the labels.

Issue breakdown across conditional tasks:
- `weak_assertion` only: 234 tasks — single assertion pattern in verifier (O.e)
- Both `weak_assertion` + `missing_oracle`: 48 tasks — (see BUG-001 re: "missing_oracle" mislabel)
- `missing_oracle` only: 34 tasks — (see BUG-001 re: mislabel)
- `core_ready` (no issues): 156 tasks

---

## Task Gap Summary

| Comparison | Count A | Count B | Gap | Explanation |
|---|---|---|---|---|
| CANONICAL.json | 275 | csb-v2-dual264 suite | 11 | 11 tasks excluded: no dual-mode verification |
| CANONICAL.json | 275 | selected_benchmark_tasks.json | 1 | bustub-hyperloglog-impl-001 missing |
| CANONICAL.json | 275 | active suite dirs (csb_org_*, csb_sdlc_*) | 0 | All 275 present in both locations |

**Note:** The "7-task gap" referenced in the convergence report (275 canonical vs 268 active) does not match current repository state. The current meaningful gap is 11 tasks excluded from csb-v2-dual264 (see CSB-BUG-006).

---

## Bugs

### CSB-BUG-001: generate_verifier_labels.py Maps R.4 (sdlc_phase) as "missing_oracle"

**Severity:** high
**Component:** verifier, metadata
**Affected tasks:** 82 tasks incorrectly labeled `missing_oracle` in verifier_quality_labels.json
**Description:** `scripts/evaluation/generate_verifier_labels.py` maps R.4 audit warnings to the string label `"missing_oracle"`. However, R.4 in `abc_audit.py` checks for `sdlc_phase` populated in `selected_benchmark_tasks.json`, **not** for missing oracle files. The actual oracle existence check is T.8. As a result, 82 tasks are labeled `"missing_oracle"` when they actually lack `sdlc_phase` — a completely different issue. This corrupts the quality classification and any downstream reasoning that relies on the "missing oracle" flag.

**Reproduction:**
1. Check `configs/verifier_quality_labels.json` — tasks labeled with `"missing_oracle"` issue
2. Check `scripts/evaluation/abc_audit.py` function `check_r4_sdlc_phase()` — confirms R.4 = sdlc_phase
3. Check `scripts/evaluation/abc_audit.py` function `check_t8_oracle_exists()` — confirms T.8 = oracle files

**Fix approach:** Change `generate_verifier_labels.py` to use T.8 for `missing_oracle` labeling. Add a separate `missing_sdlc_phase` issue type for R.4 WARN. Regenerate labels after fix.

---

### CSB-BUG-002: 111 Tasks Missing `sdlc_phase` in selected_benchmark_tasks.json

**Severity:** medium
**Component:** metadata
**Affected tasks:** 111 tasks (out of 274 in selected_benchmark_tasks.json)
**Description:** `configs/selected_benchmark_tasks.json` has 111 tasks with a null or missing `sdlc_phase` field. This field is used by R.4 audit checks, task taxonomy assignment, and downstream reporting. The `ccx-agentic-*` tasks are overrepresented in the missing set.

**Reproduction:**
```python
import json
with open('configs/selected_benchmark_tasks.json') as f:
    data = json.load(f)
missing = [t['task_id'] for t in data['tasks'] if not t.get('sdlc_phase')]
print(len(missing))  # 111
```

**Fix approach:** Populate `sdlc_phase` for all 111 tasks using the task category (`ccb_swebenchpro` → `fix`, `cross-repo-config-trace` → `understand`, etc.) and regenerate labels. The `task_type_taxonomy.json` `suite_to_task_type` mapping can assist.

---

### CSB-BUG-003: Verifier Version Drift — oracle_checks.py Has 3 Diverged Versions

**Severity:** high
**Component:** verifier
**Affected tasks:** 9 canonical tasks with outdated verifier (127+18 non-canonical copies also affected)
**Description:** `oracle_checks.py` exists in 549 copies across the benchmark (266 + 127 + 18 unique checksums; 411 in active dirs, 138 in backups). Three distinct versions are in circulation:

| Version | Hash prefix | Lines | Issue | Count (active) |
|---|---|---|---|---|
| v3 (current) | `6db14d61` | 795 | Group-aware recall logic | 266 |
| v2 (old, csb_metrics import) | `a6fb0319` | 722 | Missing group-aware recall | 18 |
| v1 (old, ccb_metrics import) | `bbbb2a5b` | 722 | Missing group-aware recall | 127 |

The v3 upgrade added group-aware recall: oracle symbols sharing a `"group"` field are treated as alternatives, so finding any one member satisfies the group. Tasks on v2/v1 score alternative-path recalls incorrectly — agents are penalized for finding valid alternative code paths.

**9 canonical tasks with v2 (outdated):**
- ccx-crossorg-288, ccx-crossorg-295, ccx-dep-trace-293, ccx-platform-291
- ccx-agentic-290, ccx-migration-289, ccx-migration-294
- ccx-compliance-286, ccx-compliance-292

**Fix approach:** Replace all non-v3 copies with the canonical v3 version (`benchmarks/csb/crossrepo/ccx-config-trace-010/tests/oracle_checks.py`). Long-term: move `oracle_checks.py` to a shared library (`lib/csb/`) and import it, eliminating per-task copies entirely.

---

### CSB-BUG-004: promoted_verifier.py Has 123 Copies with Zero Version Control

**Severity:** medium
**Component:** verifier
**Affected tasks:** 110 active copies (1 unique version detected); any future divergence undetected
**Description:** `promoted_verifier.py` exists in 123 copies (110 active, 13 in backups), all currently identical (hash `272c3ad4`). There is no mechanism to detect or prevent future drift. Any bugfix to `promoted_verifier.py` must be applied to 110+ files manually or via script. Combined with the 549 `oracle_checks.py` copies, CSB has **672 duplicated verifier library files** with no centralized version control.

**Fix approach:** Move `promoted_verifier.py` to `lib/csb/` and import it in each task's verifier. This eliminates per-task copies and makes upgrades atomic.

---

### CSB-BUG-005: curl-security-review-001 MCP Verifier: RewardFileNotFoundError

**Severity:** high
**Component:** verifier
**Affected tasks:** 1 (`curl-security-review-001`, backed up in `benchmarks/backups/csb_sdlc_test/`)
**Description:** The `curl-security-review-001` task MCP verifier fails with `RewardFileNotFoundError` in every MCP run. Root cause: wrong Sourcegraph mirror URL in the clone manifest, causing the verifier to fail before writing `reward.txt`. The task was removed from active `csb_sdlc_test` suite and placed in backups. In MCP mode, the agent ran for 21 minutes and produced no `review.json` because it could not access the SG mirror — it fell back to WebFetch/curl instead of MCP tools since `--mcp-config` was not correctly wired.

Evidence from run logs: `"curl-security-review-001 MCP has a systemic verifier bug — RewardFileNotFoundError every time in MCP mode"` and `"fix: curl-security-review-001 MCP verifier — wrong mirror URL in clone manifest"` (git history).

**Reproduction:** Launch `curl-security-review-001` with MCP config against the sg-evals mirror.

**Fix approach:** Update `tests/repo_manifest.json` with the correct Sourcegraph mirror URL. Re-run the MCP verifier validation. Re-add task to `csb_sdlc_test` after validation passes.

---

### CSB-BUG-006: 11 Canonical Tasks Excluded from csb-v2-dual264 (Dual-Verifier Gap)

**Severity:** medium
**Component:** metadata, task_definition
**Affected tasks:** 11 tasks (all in canonical 275, none in csb-v2-dual264)
**Description:** The `benchmarks/suites/csb-v2-dual264.json` suite has 264 tasks while `CANONICAL.json` has 275 — an 11-task gap. These 11 tasks are present in all directories and in `csb-v2-full-validated.json` (275 tasks) but missing from `csb-v2-dual264.json`. They also have incomplete metadata in CANONICAL.json (null `task.id`, null `category`).

**Missing tasks:**
- `ansible-abc-imports-fix-001`, `nodebb-notif-dropdown-fix-001`, `nodebb-plugin-validate-fix-001` — SWE-bench Pro type, `reward_type: test_ratio`
- `ansible-galaxy-tar-regression-prove-001`, `flipt-auth-cookie-regression-prove-001`, `qutebrowser-adblock-cache-regression-prove-001`, `qutebrowser-darkmode-threshold-regression-prove-001`, `qutebrowser-hsv-color-regression-prove-001`, `qutebrowser-url-regression-prove-001`, `teleport-ssh-regression-prove-001`, `vuls-oval-regression-prove-001` — regression-prove type, debug suite

**Root cause:** These tasks appear to use single-mode verification (direct test execution only) rather than dual-mode (direct + artifact), but `csb-v2-full-validated.json` marks them as `['direct', 'artifact']` — inconsistency between suite files.

**Fix approach:** Audit the 11 tasks' verification modes. Add dual-mode verifiers where missing, or explicitly exclude them from dual-mode suites with documented reason. Update `csb-v2-dual264.json`.

---

### CSB-BUG-007: 13 Tasks with Incomplete Metadata in CANONICAL.json

**Severity:** medium
**Component:** metadata
**Affected tasks:** 13 tasks
**Description:** 13 of 275 canonical tasks have null `task.id` in CANONICAL.json. 8 of these also lack `language`, `difficulty`, and `category`. CANONICAL.json statistics report 8 tasks with `"unknown"` language/difficulty — but the actual count of metadata-incomplete tasks is 13 (the statistics undercount).

**Tasks with null task.id and missing category (5 tasks):**
- `envoy-grpc-server-impl-001`
- `k8s-runtime-object-impl-001`
- `python-http-class-naming-refac-001`
- `etcd-grpc-api-upgrade-001`
- `numpy-dtype-localize-001`

**Tasks with null task.id and partial metadata (8 regression-prove tasks):**
- `ansible-galaxy-tar-regression-prove-001`, `flipt-auth-cookie-regression-prove-001`
- `qutebrowser-*-regression-prove-001` (5 tasks), `teleport-ssh-regression-prove-001`
- `vuls-oval-regression-prove-001`

**Fix approach:** Populate missing fields by reading `task.toml` for each task and backfilling CANONICAL.json. The `task.toml` files contain the authoritative metadata.

---

### CSB-BUG-008: bustub-hyperloglog-impl-001 Present in CANONICAL.json but Not in selected_benchmark_tasks.json

**Severity:** low
**Component:** metadata
**Affected tasks:** 1 (`bustub-hyperloglog-impl-001`)
**Description:** CANONICAL.json has 275 tasks; `selected_benchmark_tasks.json` has 274. The missing task is `bustub-hyperloglog-impl-001`, which exists in both `benchmarks/csb/feature/` and `benchmarks/csb_sdlc_feature/` but was never added to the selection registry. This means it would never be included in benchmark runs that use `selected_benchmark_tasks.json` as the source.

**Fix approach:** Add `bustub-hyperloglog-impl-001` to `selected_benchmark_tasks.json` with appropriate metadata (language: unknown/C++, sdlc_phase: feature, suite: csb_sdlc_feature).

---

### CSB-BUG-009: Non-Standard Ground Truth Schemas Across 101 Tasks

**Severity:** medium
**Component:** ground_truth
**Affected tasks:** 101 tasks (out of 275 canonical)
**Description:** The standard ground truth format (`files` + `symbols` arrays) is used by 174 tasks. The remaining 101 tasks use 9 different custom schemas:

| Schema type | Count | Example fields |
|---|---|---|
| `files` only | 38 | `files`, no `symbols` |
| `expected_files` | 20 | `expected_files`, `expected_keywords` |
| `expected_refs/new_symbol/old_symbol` | 10 | rename detection tasks |
| `required_findings` | 9 | incident tasks |
| `canonical_name/path/function_id` | 8 | symbol resolution |
| `required_topics` | 7 | documentation tasks |
| `buggy_files` | 4 | debug/fault tasks |
| `scoring_categories` | 2 | review tasks |
| `entries/key_fields` | 2 | migration tasks |
| `steps` | 1 | workflow tasks |

This heterogeneity means no single verifier can score all tasks against ground truth — each schema requires its own parsing logic. EnterpriseBench's `eb_verify` library must handle all 10 schemas or fail to score non-standard tasks.

**Fix approach:** Define a canonical ground truth schema (as in `schemas/task.schema.json`) with a discriminated union. Migrate non-standard schemas to use the union format with typed variants. Document expected schema per task type.

---

### CSB-BUG-010: 8+ Scripts Independently Redefine DIR_PREFIX_TO_SUITE Mapping

**Severity:** medium
**Component:** metadata
**Affected tasks:** All 275 (any run processing could be affected)
**Description:** The mapping from directory prefix to suite name (e.g., `csb_sdlc_fix_` → `csb_sdlc_fix`) is defined independently in 8+ scripts across `scripts/analysis/`, `scripts/evaluation/`, and `scripts/maintenance/`. A single `configs/suite_mapping.json` file exists but is not consistently used. If a new suite is added, all 8+ definitions must be updated — and historically at least one definition has drifted (evidenced by `pipeline_audit.md`).

**Fix approach:** Mandate use of `configs/suite_mapping.json` as the single source of truth. Refactor all 8+ scripts to load from it. Add a repo health check that fails if any hardcoded mapping is detected.

---

### CSB-BUG-011: Non-Atomic Run Promotion Pipeline (No Rollback on Failure)

**Severity:** high
**Component:** verifier
**Affected tasks:** All tasks in promoted runs
**Description:** The run promotion pipeline is a linear sequence: `consolidate_staging.py → promote_run.py → generate_manifest.py → extract_metrics.py → export_results.py`. If any step fails mid-way, the official runs directory is in a partially promoted state with no rollback mechanism. This has caused "bad data" in official results (documented in pipeline_audit.md: "8 errored batches" from `docgen_opus` runs with `RewardFileNotFoundError` + migration RuntimeError, and 4 rate-limited baselines with score=0.0 that required manual archival).

**Fix approach:** Wrap the promotion sequence in a transaction: write to a temporary staging directory and atomic-rename on success. Add `--validate-only` mode to each step. Implement rollback that removes the partial state.

---

### CSB-BUG-012: Ground Truth Loading Implemented 3 Different Ways

**Severity:** medium
**Component:** ground_truth
**Affected tasks:** All 275 canonical tasks (any scoring/analysis could be affected)
**Description:** The code for loading and parsing `ground_truth.json` and `oracle_answer.json` is independently reimplemented in at least 3 scripts (`trace_quality_pipeline.py`, `abc_audit.py`, various analysis scripts). Each implementation handles schema variations differently, leading to inconsistent results when the same task is analyzed by different scripts. Per `pipeline_audit.md`: "Ground truth loading implemented 3 different ways (maintenance burden)."

**Fix approach:** Create a single `GroundTruthRegistry` abstraction (identified in `phase2_consolidation_plan.md`) that handles all 10 schema variants. All scripts import from it. This consolidation is already planned but not implemented.

---

## Summary Table

| Bug ID | Severity | Component | Affected Count | Fix Complexity |
|---|---|---|---|---|
| CSB-BUG-001 | high | verifier, metadata | 82 tasks mislabeled | Low (script fix + regen) |
| CSB-BUG-002 | medium | metadata | 111 tasks | Medium (data population) |
| CSB-BUG-003 | high | verifier | 9 canonical + 145 non-canonical | Medium (file replacement) |
| CSB-BUG-004 | medium | verifier | 110 active copies | High (refactor to shared lib) |
| CSB-BUG-005 | high | verifier | 1 task (MCP mode) | Low (fix mirror URL) |
| CSB-BUG-006 | medium | metadata, task_definition | 11 tasks | Medium (audit + update suite) |
| CSB-BUG-007 | medium | metadata | 13 tasks | Low (backfill from task.toml) |
| CSB-BUG-008 | low | metadata | 1 task | Low (add to selection registry) |
| CSB-BUG-009 | medium | ground_truth | 101 tasks | High (schema migration) |
| CSB-BUG-010 | medium | metadata | All tasks (infrastructure) | Medium (refactor to single src) |
| CSB-BUG-011 | high | verifier | All promoted runs | High (atomic promotion) |
| CSB-BUG-012 | medium | ground_truth | All tasks (analysis) | Medium (extract shared lib) |

**Total: 12 bugs** matching the convergence report's "Fix 12 CSB bugs" target.

### Priority Order for EnterpriseBench Phase 1

1. **CSB-BUG-001** — Fix mislabeled quality classifications before any analysis
2. **CSB-BUG-003** — Standardize oracle_checks.py (scores are wrong for 9 canonical tasks)
3. **CSB-BUG-005** — Fix curl-security-review-001 MCP verifier (blocked task)
4. **CSB-BUG-007** — Backfill CANONICAL.json metadata (required for task taxonomy tagging)
5. **CSB-BUG-006** — Resolve dual-verifier gap (required for dual-mode runs)
6. **CSB-BUG-002** — Populate sdlc_phase (required for 7-suite taxonomy tagging)
7. **CSB-BUG-008** — Add bustub to selection registry
8. **CSB-BUG-009** — Standardize ground truth schemas (required for eb_verify)
9. **CSB-BUG-010** — Centralize suite mapping (infrastructure hygiene)
10. **CSB-BUG-011** — Atomic promotion (infrastructure reliability)
11. **CSB-BUG-012** — Consolidate ground truth loading (infrastructure hygiene)
12. **CSB-BUG-004** — Centralize promoted_verifier.py (long-term tech debt)
