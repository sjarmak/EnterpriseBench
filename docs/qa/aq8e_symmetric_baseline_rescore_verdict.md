# aq8e — Symmetric Baseline Re-Score: does the no-MCP-win parity conclusion hold?

**Bead:** EnterpriseBench-aq8e (symmetric-baseline hardening of 9awn/uu17) · **Date:** 2026-06-27
**Mode:** read-only re-SCORE — no agent execution, no container, no SG token, no API key
**Code:** origin/main @94e0e0d (the k4tv/hmcp verifier-soundness fix), run in worktree
`EnterpriseBench-aq8e` (branch `audit/eb-aq8e-symmetric-baseline-rescore`, based at
origin/main; `run_task.py` verified byte-identical to 94e0e0d, and the
`expected_solution.json` set matches uu17 exactly: 21 of 29 affected tasks have it,
8 do not).

## Verdict (acceptance #4)

**The no-MCP-win parity conclusion HOLDS. No defensibility/headline event; no escalation.**
Scoring BOTH arms identically (re-score of the locked transcripts under the fixed
verifier) leaves the MCP-vs-baseline direction unchanged: mean delta negative,
median 0.0, MCP never wins — including at the pro-MCP judge-noise extreme.

One honest nuance, surfaced not buried: the symmetric re-score does **not strengthen**
the anti-MCP magnitude the way uu17 predicted. It moves the point estimate slightly
**toward parity** (mean −0.0826 vs the mixed-method −0.1041) because it removes a
scoring-asymmetry artifact — not because MCP improved. The conclusion is the same and
now rests on a cleaner (symmetric) footing; the direction does not change, so the
acceptance-#4 escalation trigger ("conclusion CHANGES → STOP") is **not** met.

## Three headlines over the locked N=105 (Δ = mcp − baseline)

| set | mean Δ | median Δ | better/tie/worse | direction |
|---|---:|---:|---|---|
| OLD locked (p6ux.28) | −0.0925 | 0.0 | 24 / 52 / 29 | MCP_worse |
| uu17 MIXED (baseline re-run + mcp re-score) | **−0.1041** | 0.0 | 23 / 49 / 33 | MCP_worse |
| **aq8e SYMMETRIC (both arms re-scored)** | **−0.0826** | **0.0** | 25 / 52 / 28 | **MCP_worse** |

The **mcp arm is held fixed at uu17's accepted re-score median** in both the MIXED and
SYMMETRIC rows, so the *only* change between them is the baseline arm's
re-run → re-score swap. This isolates the verifier effect from baseline agent
re-run noise — exactly the asymmetry the skeptic raised.

**Pipeline validation:** this script's MIXED row reproduces uu17's reported close
**exactly** (−0.1041 / median 0.0 / 23-49-33), and its OLD row reproduces p6ux.28
(−0.0925 / 24-52-29). The symmetric number is the only new quantity.

### Symmetric judge-noise sensitivity band (BOTH arms varied)

| extreme | mean Δ | median Δ | better/tie/worse |
|---|---:|---:|---|
| pro-MCP (mcp_max − base_min) | −0.0303 | 0.0 | 30 / 48 / 27 |
| anti-MCP (mcp_min − base_max) | −0.1297 | 0.0 | 23 / 51 / 31 |

**No MCP win across the full symmetric band [−0.130, −0.030]; median 0.0 throughout.**
Even the most pro-MCP corner (mcp at its highest judged pass, baseline at its lowest)
stays negative and does not flip. Variant A (re-applied `baseline≠0` membership,
N=104): mean −0.0834, median 0.0.

## Why symmetric is less anti-MCP than mixed (the mechanism)

The mixed method capped only the **mcp** arm with the working Tier-2 judge; the
baseline arm was a fresh re-run that was NOT judge-capped the same way. That left
two asymmetry artifacts that the symmetric re-score corrects:

1. **support-map-grafana-alerts-004 (the dominant driver).** Under the symmetric
   re-score the judge scores **0.0 on all four baseline checkpoints** (grep
   0.94/1.0/0.0/1.0 → judge 0.0 → capped 0.0), so the baseline re-scores to **0.0**,
   tying mcp's re-scored 0.0 → Δ = 0. The mixed method left baseline at the re-run's
   2.82 while mcp was capped to 0, manufacturing a **spurious −2.82 anti-MCP delta**.
   Removing that artifact accounts for essentially all of the −0.1041 → −0.0826 shift.
2. **Baseline re-run agent-noise that had *inflated* MCP** (config-drift-argocd
   2.25→0.25, openssl 2.75→0.0, jackson 3.0→2.0 on re-run) is also removed: the
   re-score holds those baselines at their locked values, so their spurious pro-MCP
   deltas (+2.0, +2.75, +1.0 in mixed) collapse to 0 in symmetric. These pull in the
   opposite direction and partially offset (1).

The net of removing both is a small move toward parity. The qualitative result —
median 0.0, mean negative, majority tie-or-worse — is unchanged.

## Acceptance #1 — transcripts intact

All **29** affected baseline transcripts are present and re-scorable. 25 use the flat
layout (`results/runs/<task>/baseline/agent_trace.jsonl`); **4 use a multi-rep layout**
(`baseline/rep{1,2,3}/`) where the locked top-level `task_score` is the MAX across reps
— for those the re-score reconstructs the artifact from the rep whose `results.json`
score equals the locked top-level value (the rep that produced the locked number).
**0 missing, 0 incomplete.** Of the 29: 21 have `expected_solution.json` (judged),
8 do not (judge skipped, pass-through) — identical to the mcp_only arm in uu17.

## Acceptance #3 — gocp-module-007 disposition

**Under the re-score, gocp-module-007 needs NO re-run and NO fallback cell.** Its
*locked* baseline transcript is intact (phase=complete, 2 Write calls, has
`expected_solution.json`) and re-scores **stably to 4.0 across all 7 passes** (judge
does not cap it). The `verifier_infra_error` that afflicted the **9awn re-run** was a
property of that fresh re-run's container, not of the captured baseline output; the
re-score reads the valid locked artifact and so sidesteps it entirely. gocp is scored
as a real measurement (baseline 4.0, mcp re-score 3.67, Δ = −0.33, anti-MCP) — **never
scored 0**. This is a strict improvement over the mixed method, which had to substitute
the locked baseline as a fallback for gocp's failed re-run cell.

## Method (acceptance #2)

Identical to uu17's `rescore_mcp_only_uu17.py`, retargeted to the baseline arm:

1. Reconstruct the agent answer artifact from the locked baseline
   `agent_trace.jsonl` Write calls (multi-rep aware, see acceptance #1).
2. Call the exact @94e0e0d `run_task._apply_llm_judge`, monkeypatching only the
   container `cat` to return the reconstructed artifact. Judge runs host-side via the
   `cc:haiku` CLI backend (no token, no API key). Tier-2 cap `min(grep, judge)` applied
   identically to both arms.
3. **7 independent passes**, aggregated by per-task **median** + min/max band (the
   cc:haiku judge is noisy at the 0.5↔1.0 partial-credit boundary). 6 of the judged
   tasks were unstable across passes (dep-traversal-004/005/006/008/012,
   support-map-grafana-alerts-004); median dampens it and the min/max band bounds the
   conclusion.

Scripts: `rescore_baseline_aq8e.py`, `aggregate_baseline_aq8e.py`,
`recompute_headline_aq8e.py`. Per-task outputs: `results/rescore_aq8e/`. The mcp arm
reuses uu17's accepted median (`results/rescore_aq8e/mcp_only_uu17_median.json`,
extracted from `fix/eb-uu17-mcp-rescore`).

## Note on task membership (~38 vs 29)

The bead text says "~38 affected llm_curator tasks, esp. the 6 delta-poisoning ones".
The canonical k4tv-affected llm_curator set
(`rerun_9awn/affected_tasklist.json`) is **29** — 23 `UNIFORMLY-UNCAPPED` + 6
`INCONSISTENT`. The 6 INCONSISTENT (= the "delta-poisoning") tasks are
dep-traversal-003, dep-traversal-005, dep-traversal-007, dep-traversal-010,
refactor-orch-001, refactor-orch-003. A valid symmetric comparison to uu17's headline
**requires identical task membership**, so this re-score uses the same 29 and the same
locked N=105, matching uu17 one-for-one.

## Bottom line

The symmetric re-score closes the asymmetry critique: both arms scored the same way
under the fixed verifier, the recomputed headline is **mean −0.0826 / median 0.0 / no
MCP win**, robust across the full judge-noise band, with gocp resolved cleanly (no
fallback) and the dominant mixed-method anti-MCP cell (support-map −2.82) shown to be a
scoring-asymmetry artifact. The conclusion is **unchanged** and now methodologically
cleaner. Direction does not flip → no acceptance-#4 escalation. Branch-ready; not
pushed (mayor publishes).
