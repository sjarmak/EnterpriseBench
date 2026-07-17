# Handoff: finish the prompt-echo remediation (quarantine 3 → 0)

**Epic:** `EnterpriseBench-rryas` (clean MCP vs baseline vs CLI headline study).
**Parent:** `EnterpriseBench-jn73.2.7.3.1` (report-verifier prompt-echo standardize).
**Supersedes:** the "quarantine 6" revision of this file (`3d98ee8`). Its
*Remaining 6* framing is now wrong in one way that matters — see *What this
handoff got wrong* below.

## State

Quarantine `tests/integrity/known_prompt_echo_leaks.json` went **6 → 3**:

```
feature_delivery/monorepo-boundary-003
technical_debt/refactor-orchestration-005
technical_debt/refactor-orchestration-006
```

Cleared this session: `config-drift-004` (`1348620`), `tri-tokio-001` (`8007acc`),
`tri-babel-001` (`8d861e5`).

Full-suite diff against the session-start tree: **418 → 418 failures, zero new**.

## What this handoff got wrong (do not re-inherit)

1. **"config-drift-004 requests a corrected artifact."** It does not. Its Output
   section only ever asks for `DRIFT_REPORT.json`; the `values.yaml` path it
   names is a *source*. `validate_corrected_config` was deleted, per the
   001/002/003 precedent.
2. **"Class B ×4 — the real defect is in the prompt, not the checks."** True but
   *insufficient* for the two tri-* tasks. Their **premise was false**: the
   answer key encoded a chain that does not exist at the pinned revs. Stripping
   the giveaway and grading "the derived order" against that key would have
   produced a green, un-passable task — the exact trap step 3 exists to catch.
   Stephanie's call: **re-scope to the real graph** (the `55ef000` precedent).
   Check the premise before assuming the fix is prompt-only. **005/006 and
   monorepo-boundary-003 are unverified on this axis.**

## The method (unchanged, and it keeps paying)

Steps 3 and 5 are the ones that catch fabrication. Verified per task:
echo → 0, correct → 1.0, old-key's-answer → ~0.

1. **Verify the key against raw source at the pinned SHA.** Never trust it. Every
   config-drift key was wrong; both tri-* chains were invented. Unauthenticated
   `raw.githubusercontent.com` / `api.github.com` work fine (no `GITHUB_TOKEN`).
2. **Split the vocabulary.** `grep -coF -- "<token>" instruction.md`. **Use `-F`.**
   Judge against **instruction.md only** — `task.toml`'s `[task].prompt` is stale
   CSB metadata, never shown. (Re-sync it anyway: it is a regeneration landmine.
   All three tasks cleared this session had a `[task].prompt` still spelling out
   the giveaway.)
3. **Score a plausible CORRECT answer, not just the key.** The key passing proves
   nothing. Also score the old key's own answer: ~0 means fabricated, not imprecise.
4. **Kill free credit.** Both directions. A checkpoint paying for a *missing*
   artifact is free credit; one paying for *silence* is too (`check_parallelism`
   gave 0.5 to an empty file). And check the inverse: config-drift-004's config
   checkpoint *docked* a compliant agent 0.25 for not mutating an unrequested file.
5. **Check both failure directions.** Recall AND precision. tri-babel is now a
   pure precision task: the repo set is in the prompt, so naming all three proves
   nothing — the finding is that webpack is **out** of scope.
6. **Run the FULL suite as a DIFF against a baseline, not a pass count.**

   The suite has ~418 pre-existing failures, so "418 failed" tells you nothing.
   **Do not use a detached worktree at the session-start SHA** — the tree carries
   a large pile of untracked files (expected_solution.json etc.) that the worktree
   lacks, which alone swings the count 222 ↔ 418. Toggle *your own* changes in the
   *same* tree instead:
   ```bash
   git stash push -q -m gate -- <your paths only>   # not run_task.py: pre-existing mod
   pytest tests/ -q -m "not network and not docker" -p no:cacheprovider \
     --ignore=tests/security/test_file_extraction_plugin.py \
     | grep ^FAILED | sed 's/FAILED //' | sort > /tmp/base.txt
   git stash pop -q
   # ...rerun into /tmp/head.txt...
   comm -13 /tmp/base.txt /tmp/head.txt   # MUST be empty
   ```
7. **A check that emits no JSON verdict is BROKEN, not a 0.0.** An apostrophe in
   `python3 -c '...'` (`axum's`) killed a check silently this session; the ad-hoc
   harness scored the corpse 0.0 and it looked like a clean result.
   `tests/integrity/test_verifier_verdict_parseable.py` is what catches this —
   run it. Avoid apostrophes in the `-c` body, or use a quoted heredoc.

## Remaining 3

All three still assert `parallelizable_steps`/topo answers in the prompt. **Verify
the premise against the manifests first** — the two tri-* siblings both failed it.

- **`refactor-orchestration-005`** — milder: genuinely asks the agent to *determine*
  the order. Uses the shared topo plugin.
- **`refactor-orchestration-006`** — gives a partial chain ("e.g. client-go depends
  on apimachinery").
- **`monorepo-boundary-003`** — no giveaway in the prompt; the leak is elsewhere.
  Diagnose before rewriting.

Note 005/006 also score 0.0 in `tests/test_topo_order_markdown_extraction.py`
because their per-repo detail sits in markdown table cells the extractor does not
read (`EnterpriseBench-e1eq`). That is pre-existing and separate.

### The trap specific to this family

**The order alone is not creditable evidence.** Under *either* corrected graph the
old chain order still validates — a fan-out admits `[tokio, hyper, axum]`, and
`resolve_tokens_to_graph` drops non-nodes so `[babel, webpack, next.js]` resolves
to `[babel, next.js]`. Both are also exactly what a model that knows the ecosystem
guesses without opening a file. So every checkpoint is gated on a manifest token
absent from the prompt (`0.14`, `acorn`). Do the same for 005/006.

**Do not** pad `scoring_evidence` to clear a token minimum: it silences the echo
test by failing *everyone*. `scratchpad/tri-tokio-padding.patch` (if still present)
is the worked anti-pattern; `test_scoring_evidence_is_nonprompt.py` does **not**
catch it — only scoring a plausible correct answer does.

The shared `eb_verify.plugins.topological_order` was **not** modified (005, 006 and
both tri-* tasks use it). Keep it that way; fix graphs and gates in the task.

## Known-open, not mine to close

1. **`tests/security/test_file_extraction_plugin.py` (untracked, another session)**
   imports `eb_verify.plugins.file_extraction`; the scorer lives under
   `eb_verify.scorers`. It raises a **collection error that aborts the entire
   suite** — a naive `grep ^FAILED` gate reports "0 failures" from a suite that
   never ran (the `91ae289` laundering class, in the gate itself). Currently
   `--ignore`d. Tell that session.
2. **`jn73.2.7.3.1.4`** — JSON-echo blind spot (81 tasks). config-drift-004 was a
   live instance: quarantine saw only `check_config_valid.sh`'s free 1.0 while the
   real leak (a *valid-JSON* report fabricated from prompt vocabulary scoring
   0.8125) was invisible, because a `.md` copy is not valid JSON.
3. **`jn73.2.7.3.1.3`** — path fidelity, still needs `GITHUB_TOKEN`.
4. **Closed-book risk is NOT closed.** Both tri-* tasks are now echo-resistant but
   a model may recall that axum 0.6 sits on hyper 0.14, or that webpack uses acorn,
   without reading anything. Recorded in each key's
   `scoring_evidence._residual_risk`. An untracked `tests/test_closed_book_gate.py`
   suggests another session is on this. **Do not read an echo pass as a closed-book
   pass.**
5. `tests/test_task_output_path_consistency.py` red for 17 tasks (pre-existing).

## Pointers

- Root cause + gate analysis: `results/rryas_dataset/FINDINGS.md`
- Rescan quarantine: `python3 scripts/validation/curated_gate_analyzer.py --rescan-quarantine`
- Check one task: `python3 -c "import sys;sys.path.insert(0,'scripts/validation');
  import curated_gate_analyzer as A,pathlib as P;print(A.echo_leak(P.Path('<dir>')))"`
  — **an empty dict does not mean clean for a JSON deliverable.**
- **Hardcoded metadata locations found so far** (CSB carried 11; touch a task's
  checks/weights and these must move in the same commit):
  `tests/test_phase4_verifiers.py` (checks, weights, gt/partial answers),
  `tests/test_topo_order_markdown_extraction.py` (`GRAPH_*` graphs — a *fixture*,
  deliberately not synced; labelled so it is not copied back),
  `tests/test_file_extraction.py` (`NESTED_GT` = tri-babel's required_files).
- Worked examples, increasing difficulty: `6cbbc54` (real PR data), `80ca4f8`,
  `2c1ac55`, `55ef000` (premise false → re-scope), `1440322`,
  `1348620` (fabricated key **inverted** the grade: fabrication 0.8125 > correct
  0.4625), `8007acc` / `8d861e5` (chain invented from world knowledge; prompt-only
  echo scored a perfect 1.0).
