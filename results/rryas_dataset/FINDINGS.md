# rryas.8 curated-dataset gate analysis

Reproducible run of the executable selection gates from
`docs/internal/rryas_curated_dataset_handoff.md` over the 122-task CRNT
candidate pool. Tool: `scripts/validation/curated_gate_analyzer.py`
(`--json` / `--shortlist`). Raw data: `gate_analysis.json`, `gate_analysis.txt`.

## Dependency check (before the headline run)

- **7rc1 arm guards — LIVE on main.** Implemented as a filesystem *mode-gate*
  (`run_task.py:_apply_mode_gate`): gated arms lose agent read on the local
  repos while the scorer keeps read, proven bidirectionally per trial. This
  supersedes the epic's "empty `/workspace` sg_only image" design; arms are
  genuinely distinct at the environment level.
- **Per-trial image DIGEST in results.json — NOT met.** Zero references in the
  orchestration code. Under the mode-gate design the arm images are
  byte-identical (ablation applied at runtime, not baked per arm), so the
  digest is no longer the audit surface — the mode-gate probe is. The epic
  mandate is arguably moot but is not satisfied. **PL decision needed:**
  formally drop it, or record the digest anyway for auditability.

## Gate results over 122 candidates

| gate | method | result |
|------|--------|--------|
| 1 retrieval necessity | CRNT pool (structural) | 122 (the pool) |
| 2 mcp_only-answerable | ground_truth files are indexed source | **clean** (0 suspects; 6 heuristic flags all confirmed indexed source: `src/build/` dirs, committed lockfiles, java `.../vendor/` packages) |
| 3 prompt-echo resistant | `cp instruction.md` → deliverable, all checks must score 0 | 18 PASS · **47 FAIL** · 57 inconclusive |
| 4 deterministic-consistent | expected_solution → deliverable passes every check | 18 PASS · 30 FAIL · 74 inconclusive |

Gate 3/4 are testable only for md-grep deliverables (67 tasks). The other 55
carry structured/JSON deliverables (`answer.json`, `DRIFT_REPORT.json`,
`dead_code_report.json`) or lack `expected_solution.json` (8 tasks); the
md-grep echo/consistency vector is N/A for them and they report inconclusive.

## Executable shortlist: 18 tasks passing gates 2+3+4

```
dependency_graph (13): dep-graph-dual-log4j-spring-001, dep-graph-dual-prometheus-thanos-001,
                       dep-traversal-001..009,011,012
incident_investigation (3): incident-inv-dual-cortex-thanos-001,
                            incident-investigation-dual-cilium-001,
                            incident-investigation-dual-opa-001
config_drift (1): config-drift-dual-jaeger-otel-001
refactor_orchestration (1): refactor-dual-axum-tower-001
stratum: multi_repo 10, dual_repo 8
```

**Problem: 13/18 (72%) are dependency_graph.** This is the handoff's explicit
anti-goal ("not a dependency-graph benchmark in disguise"). The clean set is
too narrow and too skewed to be the 30-40 type-balanced headline set alone.

## The two blockers to a balanced 30-40 set

1. **Prompt-echo leakage in 47 md-grep tasks (jn73.2.7.3 class, far wider than
   the 3 known).** By type: incident_investigation 16, dependency_graph 10,
   refactor_orchestration 7, api_contract 6, error_provenance 4, config_drift 4.
   Independently verified: `api-contract-001/check_classification.sh` scores
   **1.0 on a raw `cp instruction.md`** — it greps generic vocabulary
   (`compile|runtime|silent|metadata lost`) the prompt already hands the agent.
   `incident-investigation-dual-vault-001` partial-credits an echo (0.75 / 0.5 /
   0.33) though its answer key is healthy (all 1.0). These must be re-anchored to
   non-prompt evidence (dep-traversal `scoring_evidence` template) or excluded.
   incident_investigation is a core type and the worst-hit — fixing it is the
   highest-leverage move to de-skew the shortlist.

2. **55 structured-deliverable tasks are unassessed by this tool.** They hold
   the type diversity the shortlist lacks (support_code_mapping,
   error_provenance, dead_code_necropsy, db_schema_evolution). A JSON-aware
   echo/consistency vector (build a valid-schema echo, assert the structured
   checks reject prompt vocabulary) is needed to bring them into scope.

## Recommendation

The clean-18 is a verified backbone, not a headline set. To reach a credible
type-balanced 30-40, pick one path (PL to confirm):

- **(A) Fix the echo leaks** in the 47 — start with the 16 incident_investigation
  tasks — under jn73.2.7.3, then re-run this analyzer. Highest quality, most work.
- **(B) Extend the analyzer** with a JSON-aware vector to unlock the 55
  structured tasks, widening coverage without re-authoring checks.
- **(C) Ship a smaller dep-graph-weighted headline** from the clean-18 now, and
  broaden later. Fastest, but concedes the diversity goal.

Then run the empirical mini 3-arm pilot (accounts) on whatever survives, keeping
only tasks with arm separation (cli sgx>0 / mcp_only mcp>0, baseline not winning).

---

## Addendum 2026-07-19 (rryas.8 focus): re-run on current main + hard-exclusion applied

The gate results above are the 2026-07-15 snapshot (122 candidates). Re-running
`curated_gate_analyzer.py` on main after the prompt-echo re-anchoring landed changes the
picture materially: **83 CRNT candidates, gate3 = 70 pass / 0 fail / 13 inconclusive**
(was 47 fail), `known_prompt_echo_leaks.json` is now empty, and **all_pass = 48**
(dependency_graph 21/48 = 44%, no longer 72%).

Applying the 2026-07-19 hard-exclusion directive (findings 639lv/mgodn/ozbjt/v9okc):
union of finding-named real task-ids = 40, **intersection with the 48 all_pass = 0**; a
per-vector class scan for the ozbjt freebie and v9okc patch-grep mechanisms across all 48
finds **0 hits**. Eligible pool = 48; 35 excluded (25 JSON-class/639lv, 8 gate4-inconclusive,
2 gate4-fail).

Full methodology, limitations (md-report-only scope; closed-book residual deferred to the
pilot; dep_graph skew handled by stratified analysis, not deletion), and the candidate
manifest are in **`MANIFEST.md`**. The empirical 3-arm pilot + PL sign-off remain the
lock gate; `candidate_manifest.json` is explicitly a candidate, not the final set.
