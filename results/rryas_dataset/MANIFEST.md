# rryas curated 3-arm dataset — eligible pool, exclusions, candidate manifest

Deliverable for **EnterpriseBench-rryas.8** (MCP vs baseline vs CLI headline study).
Satisfies the 2026-07-19 human-priority note: *"Record the eligible pool, exclusions
with reasons, and final paired task manifest,"* excluding any task affected by the open
verifier/reward-integrity findings unless fixed **and** independently verified — *"prefer
exclusion over delaying the headline study."*

All numbers here are regenerated, not asserted:

```bash
python3 scripts/validation/curated_gate_analyzer.py --json > results/rryas_dataset/gate_analysis.json
python3 scripts/validation/curate_rryas_manifest.py            # eligible/exclusions/candidate JSON
PYTHONPATH=lib python3 -m pytest tests/integrity/test_rryas_manifest.py -q   # re-derives, fails on drift
```

## Status word: CANDIDATE, not final

This is a **candidate** manifest. Arm separation is unproven until the empirical mini
3-arm pilot runs; a non-trivial fraction of structurally-clean tasks is expected to fail
it (the driving lesson: `technical_debt/calibration-001` did 41 turns of real work with
**0 sgx calls** and was correctly gated `infra_sgx_unused` — structurally perfect, useless
for separating arms). **Candidates ≠ final trials.** "Final" is reserved for the
post-pilot, PL-signed set.

## What changed since the historical FINDINGS.md

The prior snapshot (122 candidates, 18 clean, 47 echo-FAIL, 72% dependency_graph) predates
the prompt-echo re-anchoring. On current main (`curated_gate_analyzer.py`, 83 CRNT
candidates):

| gate | result now | was |
|------|-----------|-----|
| 3 prompt-echo (`cp instruction.md` → deliverable scores 0) | **70 pass · 0 fail · 13 inconclusive** | 18 · 47 · 57 |
| 4 expected_solution consistency | 51 pass · 2 fail · 30 inconclusive | 18 · 30 · 74 |
| `tests/integrity/known_prompt_echo_leaks.json` quarantine | **empty** | populated |
| all_pass (gate 2+3+4) | **48** | 18 |

The echo leaks the old FINDINGS flagged are re-anchored; dependency_graph is now 21/48
(44%), not 72%.

## Dependency status (7rc1 arm guards)

- **Arm mode-gate — LIVE on main** (`run_task.py:_apply_mode_gate`, `mode_gate`): gated
  arms lose agent read on local repos while the scorer keeps it, proven bidirectionally
  per trial. Arms are genuinely distinct at the environment level.
- **Per-trial image DIGEST in results.json — still UNMET** (0 references in orchestration).
  Under the mode-gate design the arm images are byte-identical (ablation applied at
  runtime), so the digest is arguably moot — but the epic mandate is unsatisfied.
  **Open PL decision: formally drop it, or record the digest for auditability.**

## Eligible pool — 48 tasks

Every all_pass task that survives the hard-exclusion scan. By type / stratum:

- **type:** dependency_graph 21 · incident_investigation 16 · api_contract 6 ·
  error_provenance 4 · config_drift 1
- **stratum:** dual_repo 30 · multi_repo 11 · tri_repo 7

Full list: `eligible_pool.json`. This **is** the candidate manifest (`candidate_manifest.json`)
— see the type-skew note below for why it is not pre-trimmed to a round 30–40.

## Exclusions — 35 tasks, with reasons

`exclusions.json` carries the per-task reasons. Summary:

| reason | n | finding |
|--------|---|---------|
| JSON deliverable, no JSON-shaped echo vector (certified-clean-without-exercise) | 25 | 639lv |
| gate4 inconclusive (no `expected_solution.json`) | 8 | — |
| gate4 fail (expected_solution does not pass its own checks) | 2 | — |

Two-layer hard-exclusion method (the class scan is the load-bearing half):

1. **name-set** — real task-ids named by each open finding: 639lv 5, mgodn 39, ozbjt 17,
   v9okc 0 (union 40). **Intersection with the 48 eligible = 0.**
2. **per-vector class scan** — because gate3 (`instruction.md` echo == 0) discharges
   **mgodn only**. It does *not* see:
   - **ozbjt** (freebie / scorable-without-repo): a check that emits full credit when a
     ground-truth key is absent (e.g. `dead-code-003/check_feature_flags.sh:31-33` →
     `score 1.0` on empty GT). Scanned across all 48 checks: **0 hits** (and all such
     JSON-deliverable instances are already excluded above).
   - **v9okc** (patch-grep): scoring by grepping a diff. Scanned: **0 hits** (the 48 are
     all md-report deliverables, no patch surface).

   The scan (`curate_rryas_manifest.freebie_checks` / `patch_checks`) is re-run in the
   invariant test, so a future check-script drift that reintroduces either mechanism into
   a manifest task fails CI.

**Where the integrity actually comes from.** Not the name intersection — that branch never
fires on an eligible task. Of the 40 finding-named tasks, 22 are in the CRNT pool and **all
22 are non-all_pass JSON-deliverable tasks already excluded by the structural gates**; 0 are
all_pass. The load-bearing firewall is limitation 1 below — the freebie/patch mechanisms live
in the JSON-deliverable class, which the md-report-only restriction excludes wholesale. The
name-set layer and the class scan are defense-in-depth that currently find nothing to remove;
they exist so that if a future md task adopts either mechanism, or a finding names an
md-report task, it is caught (and the class scan is re-derived in CI).

## Limitations that must travel with any headline drawn from this set

1. **md-report-only external validity.** Excluding all 25 JSON-deliverable tasks (639lv:
   no JSON-shaped echo vector exists yet, so an empty quarantine does *not* certify them
   clean) narrows the study to markdown-report retrieval tasks. Structured-deliverable
   families (support_code_mapping, dead_code_necropsy, db_schema_evolution, most of
   error_provenance) are **silent** in any conclusion. State this; do not generalize
   past md-report retrieval.
2. **Closed-book residual is not structurally dischargeable.** gate3 proves same-prompt
   echo resistance; it does *not* prove a task requires the repo (a model may answer from
   world knowledge). This vector is deferred to the pilot's **"baseline does not trivially
   win"** criterion — the operational closed-book filter — not claimed closed here.
3. **dependency_graph skew is an analysis problem, not a deletion problem.** dep_graph is
   21/48 (44%). Verified-clean, arm-separating tasks are **not** dropped to flatten the
   histogram (that trades statistical power for cosmetics). If the headline is a flat mean
   across tasks, over-representation is a genuine confound — the remedy is a **stratified /
   type-weighted estimator**, reported per type, not pre-deletion.
4. **Floor honesty.** After pilot attrition (limitation 2) the survivor count may fall
   below 30. The correct response is to rescope the headline to `<30` and report it, never
   to relax a gate to hit a round number.

## Remaining gates before lock (PL)

- **Gate 2 (mcp_only-answerable) did no filtering and is a coarse heuristic.** It flagged
  0/83 by pattern-matching non-source path segments in ground-truth files, and by its own
  docstring "surfaces suspects, does not judge." It does **not** verify the repos are served
  by the Sourcegraph mirror — the real precondition for the empty-`/workspace` mcp_only arm.
  That verification is deferred to the pilot's "mcp actually uses its tool" criterion; do not
  read gate 2 as having established remote-answerability.
- **Empirical mini 3-arm pilot** over the 48 candidates — keep only tasks with arm
  separation (`sgx_tool_calls > 0` for cli, `mcp_tool_calls > 0` for mcp_only, baseline
  not trivially winning). Per-task, one arm at a time; parallelize in the caller:
  ```bash
  python3 scripts/orchestration/run_task.py benchmarks/<suite>/<task>/task.toml \
    --mode {baseline|mcp_only|cli} --account <N> --output-dir results/runs/rryas_pilot/...
  ```
  Check infra first: `python3 scripts/infra/check_infra.py` (exit 0 = ready).
- **PRD task-mix** — score the locked set with `scripts/validation/task_mix_validator.py`
  and document any deviation (the eligible set spans only 5 of ~10 corpus types).
- **7rc1 per-trial image DIGEST** — the open PL drop-or-record decision above.
- **PL sign-off** on the final locked set.

## Pre-existing RED tests (known; not this bead's to fix, not counted as a green gate)

- `tests/test_noop_leak_sweep.py::test_allowlist_stays_minimal` — stale allowlist entry.
- `tests/security/test_file_extraction_plugin.py` — collection error (currently
  `--ignore`d); a naive `grep ^FAILED` gate would falsely read "0 failures" from a suite
  that never ran.

## Artifacts

- `gate_analysis.json` — raw per-task gate evidence (regenerate before trusting).
- `eligible_pool.json` — the 48, with type/stratum distribution.
- `exclusions.json` — the 35, each with a reason + the finding-named snapshot.
- `candidate_manifest.json` — the candidate set (= eligible pool) + status + skew note.
