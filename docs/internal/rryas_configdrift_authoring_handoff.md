# Handoff: finish the prompt-echo remediation (quarantine 6 → 0)

**Epic:** `EnterpriseBench-rryas` (clean MCP vs baseline vs CLI headline study).
**Parent:** `EnterpriseBench-jn73.2.7.3.1` (report-verifier prompt-echo standardize).
**Supersedes:** `docs/internal/rryas_residual_reanchor_handoff.md` (its "residual 11"
framing is now wrong in ways that matter — read *What that handoff got wrong* below).

## State

Quarantine `tests/integrity/known_prompt_echo_leaks.json` went **11 → 6**:

```
platform_engineering/config-drift-004
feature_delivery/monorepo-boundary-003
technical_debt/refactor-orchestration-005
technical_debt/refactor-orchestration-006
technical_debt/refactor-orchestration-tri-babel-001
technical_debt/refactor-orchestration-tri-tokio-001
```

`tests/integrity/` + schema + preflight: **1375 passed / 3 skipped / 6 xfailed**.

## What the previous handoff got wrong (do not re-inherit these assumptions)

1. **main was red** and it did not say so. `refactor-orchestration-tri-tokio-001`
   was a 12th leaker: tracked, leaking, never quarantined. Recorded in `4e28221`.
2. **"Re-anchor the checks" is not the fix for config-drift.** The keys were
   *fabricated*, and the checks were built to match them. Re-anchoring a check to
   a fabricated key produces a task that is green and still un-passable.
3. **The quarantine understates the leaks.** Its only vector is
   `cp instruction.md <deliverable>`; for a JSON deliverable that is not valid
   JSON, so `json.load` throws, the check scores 0.0, and the task is certified
   clean *without ever being exercised*. 81 of 180 report tasks are JSON-only.
   That is bead **`jn73.2.7.3.1.4` (P0, pre-headline)** and it is still open.

## The method that worked (reuse it)

Per task, in this order. Steps 3 and 5 are the ones that catch fabrication.

1. **Verify the key against raw source at the pinned SHA.** Never trust it. Every
   config-drift key was wrong. `GITHUB_TOKEN` is absent but unauthenticated
   `raw.githubusercontent.com` / `api.github.com` work fine.
2. **Split the vocabulary.** `grep -coF -- "<token>" instruction.md`. **Use `-F`**:
   a regex `.` matches hyphens and spaces, so `ansible.galaxy.collection` silently
   "matches" `ansible-galaxy collection` and hides a real leak. Tokens with count
   > 0 are unusable as evidence; count 0 is gradeable.
   Judge against **instruction.md only** — that is the whole text the agent gets
   (`run_task.py`: `agent_command < /workspace/instruction.md`). `task.toml`'s
   `[task].prompt` is stale CSB metadata, never shown, and diverges in ~155 tasks.
3. **Score a plausible CORRECT answer, not just the key.** This is the step the
   old workflow lacked. `expected_solution.json` passing proves nothing — those
   keys were *written to fit the grader* (config-drift-001's said "so
   check_repo_set.sh's three greps fire"). Also score the OLD key's own answer:
   if it now scores ~0, the key was fabricated, not imprecise.
4. **Kill free credit.** An "optional" checkpoint that pays 1.0 for a missing
   artifact is free credit. If the prompt never asks for that artifact, *delete
   the checkpoint* — routing it to 0.0 instead makes the task un-passable for a
   compliant agent. Rebalance weights (schema requires sum 1.0).
5. **Check both failure directions.** Recall AND precision: several keys named
   files that contain nothing. Record them in `ground_truth.not_drifted` with the
   reason so the next author does not "rediscover" them.

Verified per task: echo → 0, correct → 1.0, old-key's-answer → ~0.

6. **Run the FULL suite, not the gates you picked.** This is the trap that caught
   this session. `tests/integrity/` + schema + preflight + output-path all went
   green while the config-drift rebuilds had silently broken **12 tests** in
   `tests/test_phase4_verifiers.py` (23 → 35 failures). It was reported as clean
   on that partial evidence and only surfaced when a push was contemplated.

   `tests/test_phase4_verifiers.py` is a **second hardcoded metadata location**:
   it duplicates each task's check-script list, weights, and a `gt_answer` /
   `partial_answer` fixture, rather than reading `task.toml`. Touch a task's
   `checks/` or weights and you must update it in the same commit (`e011bcb`).
   Assume there are others: CSB carried 11 metadata locations.

   The right gate is a **diff against a baseline**, not a pass/fail count — the
   suite has ~230 pre-existing failures, so "230 failed" tells you nothing:
   ```bash
   git worktree add -q --detach /tmp/base <SESSION_START_SHA>
   for w in /tmp/base .; do (cd $w && python3 -m pytest tests/ -q \
     -m "not network and not docker" -p no:cacheprovider 2>&1 \
     | grep ^FAILED | sed 's/FAILED //' | sort) ; done > /tmp/{base,head}.txt
   comm -13 /tmp/base.txt /tmp/head.txt   # MUST be empty
   ```

## Remaining 6

### config-drift-004 (same family, expect the same rot)
Not yet examined. Assume the key is wrong until proven otherwise. Note it is the
one config-drift task whose instruction **does** request a corrected artifact
(`/workspace/dandydeveloper-charts/charts/redis-ha/values.yaml`), so unlike
001/002/003 its `validate_corrected_config` may be legitimate — check before
deleting it. Its report path is `/workspace/argo-cd/DRIFT_REPORT.json`.

### Class B ×4 — checkpoints grade prompt-provided info
`refactor-orchestration-005`, `-006`, `-tri-babel-001`, `monorepo-boundary-003`,
plus `-tri-tokio-001` (quarantined in `4e28221`).

The real defect is **in the prompt, not the checks**. tri-tokio's instruction
states `The dependency chain is: tokio -> hyper -> axum`, and all three of its
checkpoints (weight 1.00) grade exactly that. tri-babel is identical
(`babel -> webpack -> next.js`). `-005` is milder (it genuinely asks the agent to
*determine* the order); `-006` gives a partial chain ("e.g. client-go depends on
apimachinery"); `monorepo-boundary-003` has no giveaway.

Stephanie's decision (this session): **strip the giveaway from the prompt** so the
order must be derived from the actual manifests, then grade the derived order —
the same shape as the dual-argocd re-scope in `55ef000`.

**Do not** do what the abandoned attempt did: it padded `scoring_evidence` with
`check_repo_set` (the verifier's own filename) and `parallelizable_steps` (a
ground_truth key) to clear the tool's 2-token minimum. That silences the echo test
by failing *everyone* — a correct plan scored 0.0 while the key scored 1.0. The
patch is preserved at `scratchpad/tri-tokio-padding.patch` as a worked example of
the anti-pattern. `tests/integrity/test_scoring_evidence_is_nonprompt.py` does
**not** catch it (the padded tokens are absent from the prompt, so they pass) —
only scoring a plausible correct answer catches it.

## Then: the P0 pre-headline gates

1. **`jn73.2.7.3.1.4`** — the JSON-echo blind spot (81 tasks). `985ff88` covers
   part of it statically; a real JSON-shaped vector does not exist yet. A parallel
   session was extending this (see *Coordination*).
2. **`jn73.2.7.3.1.3`** — path fidelity: `GITHUB_TOKEN=... python3
   scripts/validation/validate_expected_solutions.py benchmarks/ --check-paths`.
   Still not run (no token). Reconcile `incident-investigation-dual-flux-001`,
   whose `expected_answer` cites different files than its `scoring_evidence`.
3. `tests/test_task_output_path_consistency.py` is **red for 17 tasks** (was 19;
   the two config-drift duals now pass). Each red = an agent writes where no
   verifier reads = guaranteed 0.0. This is pre-existing and predates this work.

## Coordination — read before you touch tests/integrity/

A **second session is committing to `main` concurrently**. Its commits are
interleaved with this session's (`5392b65` fix(ci), `26ce2c4`…`0385f92` eb_verify
refactors). It also has **uncommitted** files converging on the same problem:

- `tests/integrity/test_required_files_evidence_nonprompt.py` — explicitly extends
  `test_scoring_evidence_is_nonprompt.py` (this session's `985ff88`) to the
  `required_files` file-path cohort it does not reach.
- `tests/integrity/test_prompt_echo_evidence.py` — the planted-`instruction.md`
  vector.

Not a collision — the two sessions divided the coverage — but reconcile before
adding a third overlapping invariant.

## Invariants added this session (do not regress)

- `tests/integrity/test_report_prompt_echo.py` — the md-echo vector (pre-existing).
  Its docstring now records the one-way quarantine exception and *why padding is
  not fixing*.
- `tests/integrity/test_verifier_verdict_parseable.py` (`baf8fed`) — every check's
  verdict must be readable by the **real** `test_runner.sh:parse_score`, lifted
  verbatim rather than reimplemented. Closes the blind spot that hid ansible's
  `check_test_fails.sh`: pytest wrote to stdout ahead of the JSON, so the
  checkpoint yielded *no verdict* and routed to `verifier_infra_error` on every
  run since it was written — while `curated_gate_analyzer` recorded it as `None`
  and `echo_leak` dropped `None` as "clean".
- `tests/integrity/test_scoring_evidence_is_nonprompt.py` (`985ff88`) — graded
  evidence is not prompt vocabulary. Two rules, because flat `scoring_evidence` is
  scored per-token (`found/len`, so every token must be non-prompt) while
  `drift_points.evidence_tokens` are ANDed (so only ≥1 must be).

## Pointers

- Root cause + gate analysis: `results/rryas_dataset/FINDINGS.md`
- Migration tool: `scripts/authoring/reanchor_report_checks.py` (fits the flat
  grep-grader shape only; it does **not** fit JSON-deliverable or Class B tasks)
- Rescan quarantine (reviewed act, post-fix):
  `python3 scripts/validation/curated_gate_analyzer.py --rescan-quarantine`
- Check one task: `python3 -c "import sys;sys.path.insert(0,'scripts/validation');
  import curated_gate_analyzer as A,pathlib as P;print(A.echo_leak(P.Path('<dir>')))"`
  — **empty dict does not mean clean for a JSON deliverable.** See `jn73.2.7.3.1.4`.
- Worked examples of the method, in increasing difficulty: `6cbbc54` (real PR data),
  `80ca4f8` (key named files that never call the helper), `2c1ac55` (key put the
  drift in the wrong file), `55ef000` (premise false → re-scope), `1440322`
  (premise real, key absent, required_files inverted).
