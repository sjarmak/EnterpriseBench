# uu17 — Can Re-Scoring (No Token) Close the 9awn Headline Recompute?

**Bead:** EnterpriseBench-uu17 (split from 9awn / k4tv path-A) · **Date:** 2026-06-26
**Mode:** read-only re-SCORE — no agent execution, no container, no SG token, no API key
**Code:** origin/main @94e0e0d (the k4tv/hmcp verifier-soundness fix), run in worktree
`enterprisebench-uu17` (branch `fix/eb-uu17-mcp-rescore`).

## Verdict (acceptance #3)

**Re-scoring CLOSES the headline-recompute path without a token.** The locked
N=105 mcp_only transcripts are intact and re-scorable under the fixed verifier;
the recomputed MCP-vs-baseline headline is defensible and its **parity
conclusion is unchanged**. The mcp_only RE-RUN that 9awn parks on the deferred
demo token is **not required** to answer the question the k4tv defect raised —
the defect was in verifier *scoring*, not agent behavior, and 966x already
certified the locked mcp_only agent outputs VALID, so re-scoring the captured
outputs under @94e0e0d is the correct and sufficient remedy for the mcp_only arm.

**No defensibility/headline event (acceptance #4): the parity finding HOLDS.**
The fix moves the mean *slightly more anti-MCP*; MCP never wins under any variant
or judge-noise extreme.

## Headline: old vs new (locked N=105)

| set | mean Δ (mcp−base) | median Δ | better/tie/worse |
|---|---:|---:|---|
| OLD locked (p6ux.28) | −0.0925 | 0.0 | 24 / 52 / 29 |
| **NEW, fixed-105 membership** | **−0.1041** | **0.0** | 23 / 49 / 33 |
| variant A, re-applied membership (N=104) | −0.1315 | 0.0 | 22 / 49 / 33 |
| judge-noise band, mcp MAX (most pro-MCP) | −0.0707 | 0.0 | 24 / 50 / 31 |
| judge-noise band, mcp MIN (most anti-MCP) | −0.1136 | 0.0 | 23 / 48 / 34 |

Direction old = MCP_worse, new = MCP_worse. **No MCP win across the full range
[−0.131, −0.071]; median 0.0 throughout.** The pro-MCP extreme does not flip.

## Acceptance #1 — transcripts intact

All **29** k4tv-affected llm_curator tasks in the locked set (23 uniformly-uncapped
+ 6 INCONSISTENT) have intact mcp_only transcripts at
`results/runs/<task>/mcp_only/agent_trace.jsonl`. Every one contains the Write
tool-calls that reconstruct `answer.json` (the artifact the fixed verifier reads)
plus the task-specific artifact (BLAST_RADIUS.md / IMPACT_REPORT.md /
REFACTOR_PLAN.md / …). **0 missing, 0 incomplete.** Re-scorable with no live run.

## Method (acceptance #2)

The k4tv/hmcp fix (@94e0e0d) repaired Tier-2 llm_curator scoring: it derives the
agent-artifact path from task metadata (so the judge actually runs) and routes
no-artifact runs to `verifier_infra_error` instead of recording un-capped grep.
The deterministic Tier-1 grep was unchanged, so the **old locked mcp_only
checkpoint `score`s already are the uncapped grep scores**. Re-scoring therefore =
apply the (now-working) Tier-2 cap `min(grep, judge)` to the captured artifacts:

1. Reconstruct the agent answer artifact from the locked `agent_trace.jsonl`
   Write calls (same bytes that were in-container).
2. Call the EXACT @94e0e0d `run_task._apply_llm_judge`, monkeypatching only the
   container `cat` to return the reconstructed artifact. The judge runs host-side
   via the `cc:haiku` CLI backend (no token, no API key).
3. `expected_solution.json` availability in the uu17 worktree (tracked@94e0e0d)
   matches the 9awn baseline environment exactly (0 mismatches across 29), so
   both arms are scored under identical conditions. 8 of the 29 lack
   `expected_solution.json` → judge skipped in both arms (pass-through), same as
   baseline.

Scripts: `rescore_mcp_only_uu17.py`, `recompute_headline_uu17.py`. Per-task
outputs: `results/rescore_uu17/`.

## Judge non-determinism — measured and bounded

The Tier-2 `cc:haiku` judge is **noisy at the partial-credit boundary** (it
returns 0.5 vs 1.0 on the same input across runs). A single re-score pass is
therefore not defensible. Mitigation: **7 independent passes**, aggregated by
per-task **median**, plus a min/max sensitivity band reported above. 6 of the 21
judged tasks were unstable across passes (spread 0.5–1.0). The conclusion is
robust to this noise — every point in the band is "no MCP win."

Per-task mcp_only re-score moves (median over 7 passes; all are caps **down**, as
expected when the working judge ceilings inflated grep):

| task | old mcp | new mcp (median) | note |
|---|---:|---:|---|
| support-map-grafana-alerts-004 | 1.9 | 0.0 | unstable [0.0,1.0] |
| dep-traversal-003 | 4.0 | 3.0 | unstable [3.0,4.0] |
| dep-traversal-004 | 4.0 | 3.0 | unstable [3.0,4.0] |
| dep-traversal-012 | 3.67 | 3.17 | unstable [2.67,3.17] |
| incident-inv-docker-shutdown-004 | 4.0 | 3.0 | stable |
| dep-traversal-009 | 4.0 | 3.5 | stable |
| dep-traversal-010 | 4.0 | 3.5 | unstable [3.5,4.0] |

## Correctness notes / caveats (for PL)

1. **One baseline cell genuinely needs a re-run, not a re-score:**
   `api-contract-gocp-module-007` baseline persisted `verifier_infra_error`
   (success=False) in the 9awn re-run — its 0.0 is an infra artifact, not a
   measurement. Recompute uses the **locked baseline fallback** for it (no valid
   re-run replacement exists). This is a baseline-arm issue, 1/105, does not
   affect the conclusion.
2. **`dep-traversal-tri-openssl-001`** baseline re-ran to a legitimate 0.0
   (phase=complete) → under the locked clean-set convention it is `baseline_dead`
   and dropped in variant A (N=104). In fixed-105 it is kept (delta +2.75,
   pro-MCP) — yet the mean is still negative.
3. **Methodological asymmetry (inherent in 9awn's chosen method):** the baseline
   arm was a fresh agent RE-RUN under the fixed verifier, while mcp_only is a
   RE-SCORE of locked agent outputs. The comparison thus mixes baseline
   agent-noise (e.g. argocd 2.25→0.25, openssl 2.75→0.0 on re-run) with the
   verifier fix. The bead specifies "re-scored mcp_only + already-done baseline",
   so this is the method followed. To isolate the verifier-fix effect cleanly,
   re-score the **locked baseline** transcripts the same way (symmetric
   re-score-both) — recommended follow-up; it would only remove pro-MCP
   baseline-noise artifacts, strengthening "no MCP win."

## Bottom line

The mcp_only re-score path is feasible, executed, and produces a defensible
recomputed headline **without the deferred token**. Parity holds (mean
−0.10 ± judge noise, median 0.0, no MCP win). The token-blocked mcp_only re-run
is not needed to close the k4tv verifier-defect question for the mcp_only arm.
Branch-ready; not pushed (mayor publishes).
