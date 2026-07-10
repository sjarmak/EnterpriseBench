# topo_order docker-cp rescore — pt0n/lyse findings

Read-only re-score of the 5 (+lyse) docker-cp-contaminated `topo_order`
checkpoints. Method chosen by Stephanie 2026-07-10: reconstruct the agent's
`REFACTOR_PLAN.md` from the locked `agent_trace.jsonl` Write calls and re-score
it under the fixed `validate_refactor_plan_markdown`. **No container, no agent
re-run, no API** — isolates the verifier-fix effect from agent-re-run noise.

Reproduce: `python3 scripts/analysis/rescore_topo_order_pt0n.py --out results/rescore_topo_order_pt0n/topo_rescore_summary.json`

## Verified corrections (from the locked `results/runs/<task>/<mode>/`)

| pair | owner | topo (was → now) | task_score (was → now) | note |
|---|---|---|---|---|
| refactor-orch-004 / baseline | aq8e | 0.0 → **1.0** | 1.8 → **2.8** | contamination corrected |
| refactor-orch-007 / baseline | aq8e | 0.0 → **1.0** | 1.8 → **2.8** | contamination corrected |
| refactor-orch-007 / mcp_only | uu17 | 0.0 → **1.0** | 1.8 → **2.8** | contamination corrected |
| refactor-orch-008 / mcp_only | uu17 | 0.0 → **0.2222** | 1.8 → **2.0222** | contamination corrected (partial) |
| refactor-orch-001 / mcp_only | uu17 | 0.0 → 0.0 | 1.8 → 1.8 | **genuine 0** — extractor can't resolve its "Step N — <verb> …" tokens to graph repos; the uncontaminated **baseline** arm of 001 also scores topo 0.0 (exit 0), so no bias |
| refactor-orch-006 / mcp_only | lyse | 0.0 → 0.0 | 1.4 → 1.4 | **genuine 0** — agent covered 1/7 graph repos, 0/13 constraints |

All six had `topo_order` `exit_code=1` in the locked runs — the docker-cp
`ModuleNotFoundError` crash signature. Four were real silent-zeros; two
(001, 006) score 0.0 legitimately under the fixed verifier.

Note: `results/rerun_pt0n/` is an abandoned *full re-run* attempt — its fresh
agent runs produced different (lower: 1.0/1.5) outputs and several
`mcp_infra_error` phases, i.e. exactly the agent-re-run noise the read-only
method avoids. It is superseded by this rescore.

## Headline integration — the 4 changed cells and their injection points

The changed cells (001/006 unchanged) feed the aq8e/uu17 headline via:

- **base_median** (`results/rescore_aq8e/aggregated_median.json`, aq8e baseline
  re-score → the **aq8e-symmetric** headline): 004 `1.8→2.8`, 007 `1.8→2.8`.
  (7 vals are 7 judge passes; the deterministic `topo_order` fix is constant
  across them, so each cell's median moves by the full delta.)
- **mcp_median** (`results/rescore_aq8e/mcp_only_uu17_median.json`, uu17 mcp
  re-score → both headlines): 007 `1.8→2.8`, 008 `1.8→2.0222`.
- **9awn baseline re-run** (`EnterpriseBench-9awn/results/rerun_9awn/<task>/baseline/results.json`
  → the **uu17-mixed** headline's baseline): 004 and 007 are **also**
  topo-contaminated (0.0/exit 1) with their *own* separate artifacts, so the
  mixed variant's baseline needs its own reconstruction+rescore from the 9awn
  traces (not yet done).

Membership: 001/004/007/008 are in the affected-29 (their arms are overridden
by the medians above); 006 is not in affected-29, and its cell is unchanged, so
it does not move the headline either way.

## Completeness audit — the 5-pair scope was incomplete (but the delta is not)

Scanning **all** locked runs for `topo_order exit_code=1` (the docker-cp crash
signature) surfaced two contaminated tasks the handoff's 5 pairs missed, both in
the locked-105 and both `affected=False` (not overridden by the k4tv rescores):

| task | baseline (was→now) | mcp (was→now) | delta (was→now) |
|---|---|---|---|
| refactor-orchestration-tri-babel-001 | 1.5 → 2.5 | 1.5 → 2.5 | 0.0 → 0.0 |
| refactor-orchestration-tri-tokio-001 | 1.5 → 2.5 | 2.0 → 3.0 | +0.5 → +0.5 |

Both arms lift by exactly +1.0 (both agents wrote valid orderings), so the
MCP-vs-baseline **delta is unchanged** and the headline is unaffected. The same
holds for `007` in the 5-pair set (both arms contaminated, both correct to +1.0,
`d_symmetric=0`). The cells that actually move the headline are the
**asymmetrically** contaminated ones: `004` (baseline-only → −1.0 symmetric) and
`008` (mcp-only → +0.2222). Absolute per-task topo scores for tri-babel/tri-tokio
remain at their locked (contaminated) values in the clean-set base of both the
old and new headlines, which is why the delta is identical either way.

## Regenerated headline (before → after topo fix)

`recompute_headline_{aq8e,uu17}.py` re-run with the in-memory correction
(`topo_corrections.json` via `topo_corrections.py`; published median artifacts
untouched). Also fixed a stale path in both scripts (`AQ8E/UU17 "results"` →
repo-root `MAIN "results"`; broken by the earlier analysis-script move).

| variant | mean before → after | verdict |
|---|---|---|
| OLD locked | −0.0925 → −0.0925 | unchanged (pre-correction baseline) |
| uu17 mixed | −0.1041 → −0.1020 | MCP_worse (unchanged) |
| aq8e symmetric | −0.0826 → −0.0900 | MCP_worse (unchanged) |

Median 0.0 in every variant; direction MCP_worse throughout;
`conclusion_changed_vs_mixed=False`. **The topo_order contamination fix does not
change the headline conclusion — no MCP win, in every variant, before or after.**
