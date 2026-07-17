# Handoff: finish the prompt-echo remediation (quarantine 3 → 0)

**Epic:** `EnterpriseBench-rryas` (clean MCP vs baseline vs CLI headline study).
**Own this bead:** `EnterpriseBench-jn73.2.7.3.1.2` — "Re-scope 4 task-design
checkpoints that grade prompt-provided info". The remaining 3 tasks are its scope.
**Parent:** `EnterpriseBench-jn73.2.7.3.1` (P0, pre-headline).
**Supersedes:** `rryas_configdrift_authoring_handoff.md` (this file, renamed —
config-drift is done; `git log --follow` for the prior revisions).

## State

Quarantine `tests/integrity/known_prompt_echo_leaks.json` went **6 → 3**:

```
technical_debt/refactor-orchestration-005
technical_debt/refactor-orchestration-006
feature_delivery/monorepo-boundary-003
```

Cleared: `config-drift-004` (`1348620`), `tri-tokio-001` (`8007acc`),
`tri-babel-001` (`8d861e5`). No config-drift tasks remain quarantined
(`jn73.2.7.3.1.1` may be closeable — check its 7-task scope first).

Full-suite diff against the session-start tree: **418 → 418 failures, zero new.**

## Start here

```bash
bd show EnterpriseBench-jn73.2.7.3.1.2      # your bead; the tri-* findings are in its comments
cat tests/integrity/known_prompt_echo_leaks.json
git log --oneline 1348620 8007acc 8d861e5   # the three worked examples
```

## What the previous handoff got wrong (do not re-inherit)

1. **"config-drift-004 requests a corrected artifact."** It does not. Its Output
   section only ever asked for `DRIFT_REPORT.json`; the `values.yaml` path it
   named is a *source*. `validate_corrected_config` was deleted, per 001/002/003.
2. **"Class B — the real defect is in the prompt, not the checks."** True but
   *insufficient* for both tri-* tasks: their **premise was false**. The answer
   key encoded a chain that does not exist at the pinned revs, so stripping the
   giveaway and grading "the derived order" against that key would have produced
   a green, un-passable task — the exact trap step 3 exists to catch. Stephanie's
   call was **re-scope to the real graph** (`55ef000` precedent). Verify the
   premise before assuming the fix is prompt-only.

## The method (steps 3 and 5 catch fabrication)

Verified per task: **echo → 0, correct → 1.0, old-key's-answer → ~0.**

1. **Verify the key against raw source at the pinned SHA.** Never trust it. Every
   config-drift key was wrong; both tri-* chains were invented from world
   knowledge about famous ecosystems. Unauthenticated `raw.githubusercontent.com`
   / `api.github.com` work fine (no `GITHUB_TOKEN` needed).
2. **Split the vocabulary.** `grep -coF -- "<token>" instruction.md`. **Use `-F`**:
   a regex `.` matches hyphens/spaces and hides real leaks. Count > 0 ⇒ unusable
   as evidence. Judge against **instruction.md only** — `task.toml`'s
   `[task].prompt` is stale CSB metadata, never shown (`run_task.py` feeds
   `agent_command < /workspace/instruction.md`). **Re-sync it anyway**: it is a
   regeneration landmine, and all three tasks cleared this session still had a
   `[task].prompt` spelling out the giveaway.
3. **Score a plausible CORRECT answer, not just the key.** The key passing proves
   nothing — those keys were written to fit the grader. Also score the old key's
   own answer: ~0 ⇒ fabricated, not imprecise. Harness (rebuild it, ~2 min; it is
   the highest-value 30 lines in this workflow and no repo copy exists yet):

   ```bash
   # score.sh <candidate> — run each check in a WORKSPACE holding the REAL files
   WS=$(mktemp -d); cp "$1" "$WS/<DELIVERABLE>"          # + any repo files the checks read
   for spec in check_a.sh:0.55 check_b.sh:0.45; do
     s="${spec%%:*}"; w="${spec#*:}"
     out=$(WORKSPACE="$WS" TASK_DIR="$PWD" bash "checks/$s" 2>&1)
     echo "$out" | grep -q '^{' || { echo "$s BROKEN (no verdict): $out"; continue; }
     echo "$s $(echo "$out" | tail -1) weight=$w"
   done
   ```
   Score at minimum: (a) `cp instruction.md <deliverable>`, (b) a fabrication
   built ONLY from prompt vocabulary, (c) a correct answer derived from the repos,
   (d) the old key's own answer, (e) empty file / no file.
4. **Kill free credit — in both directions.** A checkpoint paying for a *missing*
   artifact is free credit; one paying for *silence* is too (`check_parallelism`
   handed an empty file 0.5). Check the inverse as well: config-drift-004's config
   checkpoint *docked* a compliant agent 0.25 for not mutating a file it was never
   asked to touch, while paying an agent that silently edited the repo. If the
   prompt never asks for the artifact, **delete the checkpoint** and rebalance
   (schema requires weights sum 1.0).
5. **Check both failure directions: recall AND precision.** tri-babel is now a
   pure precision task — the repo set is in the prompt, so naming all three proves
   nothing; the finding is that webpack is **out** of scope. Record dead ends in
   `not_drifted` / `not_affected` / `phantom_edges` with the reason, so the next
   author does not "rediscover" them.
6. **Run the FULL suite as a DIFF against a baseline, not a pass count.** ~418
   failures are pre-existing, so "418 failed" tells you nothing. **Do not use a
   detached worktree at the session-start SHA** — the tree carries a large pile of
   untracked files the worktree lacks, which alone swings the count 222 ↔ 418.
   Toggle *your own* changes in the *same* tree:
   ```bash
   git stash push -q -m gate -- <your paths only>   # NOT run_task.py: pre-existing mod
   pytest tests/ -q -m "not network and not docker" -p no:cacheprovider \
     --ignore=tests/security/test_file_extraction_plugin.py \
     | grep ^FAILED | sed 's/FAILED //' | sort > /tmp/base.txt
   git stash pop -q
   # ...rerun into /tmp/head.txt...
   comm -13 /tmp/base.txt /tmp/head.txt   # MUST be empty
   ```
7. **A check that emits no JSON verdict is BROKEN, not a 0.0.** An apostrophe
   inside `python3 -c '...'` (`axum's`) silently killed a check this session and
   the harness scored the corpse 0.0 — the `91ae289` laundering class, reproduced
   inside the gate itself. Avoid apostrophes in the `-c` body (or use a quoted
   heredoc), and run
   `pytest tests/integrity/test_verifier_verdict_parseable.py`, which exists to
   catch exactly this.

## Remaining 3 — pre-loaded facts

All three are **`monorepo_cross_package`, single-repo**. This matters: unlike the
tri-* tasks, they invent no cross-repo chain. Their package graphs are *internal*
and mechanically derivable (babel `packages/*/package.json`, k8s
`staging/src/k8s.io/*/go.mod`), so the premise is **more likely sound** — but the
tri-* siblings both failed that check, so verify it first regardless (step 1).

| task | repo @ rev | checkpoints |
|---|---|---|
| `refactor-orchestration-005` | babel @ `v7.25.0` | identify_repos .25 / topological_order .45 / parallelism .30 |
| `refactor-orchestration-006` | kubernetes @ `v1.34.0` | same |
| `monorepo-boundary-003` | babel @ `v7.22.20` | identify_affected_packages .25 / classify_change_impact .45 / identify_boundary_violations .30 |

- **005** is the mildest: it genuinely asks the agent to *determine* the order.
- **006** hands over a partial chain ("e.g. client-go depends on apimachinery").
- **monorepo-boundary-003** has **no giveaway in the prompt and is not in the topo
  family** (different checkpoints, different checks:
  `check_affected_packages.sh` / `check_boundary_violations.sh` /
  `check_impact_classification.sh`). Its leak is elsewhere — **diagnose before
  rewriting**. Start with `A.echo_leak(...)` plus step 3's fabrication candidate.

Note 005/006 also score 0.0 in `tests/test_topo_order_markdown_extraction.py`
because their per-repo detail sits in markdown table cells the extractor does not
read (`EnterpriseBench-e1eq`). Pre-existing and separate — do not chase it.

### The trap specific to the topo family (005/006)

**The order alone is not creditable evidence.** Under *either* corrected tri-*
graph the old chain order still validated — a fan-out admits `[tokio, hyper,
axum]`, and `resolve_tokens_to_graph` drops non-nodes so `[babel, webpack,
next.js]` resolves to `[babel, next.js]`. Both are also exactly what a model that
knows the ecosystem guesses without opening a file. So every checkpoint there is
**gated** on a manifest token absent from the prompt (`0.14`, `acorn`). Do the
same for 005/006: find the token only a reader of the monorepo has.

**Do not** pad `scoring_evidence` to clear a token minimum — it silences the echo
test by failing *everyone* (a correct plan scored 0.0 while the key scored 1.0).
`test_scoring_evidence_is_nonprompt.py` does **not** catch that; only step 3 does.

The shared `eb_verify.plugins.topological_order` was **not** modified and 005/006
still use it. Keep it that way — fix graphs and gates in the task, not the plugin.

## Known-open, not this bead's to close

1. **`tests/security/test_file_extraction_plugin.py` (untracked, another session)**
   imports `eb_verify.plugins.file_extraction`; the scorer lives under
   `eb_verify.scorers`. It raises a **collection error that aborts the entire
   suite**, so a naive `grep ^FAILED` gate reports "0 failures" from a suite that
   never ran. Currently `--ignore`d. **Tell that session** — it is not ours to fix.
2. **`jn73.2.7.3.1.4`** — JSON-echo blind spot (81 tasks). config-drift-004 was a
   live instance: the quarantine saw only `check_config_valid.sh`'s free 1.0 while
   the real leak (a *valid-JSON* report fabricated from prompt vocabulary scoring
   **0.8125**, vs **0.4625** for a correct one) was invisible, because a `.md` copy
   is not valid JSON.
3. **`jn73.2.7.3.1.3`** — path fidelity, still needs `GITHUB_TOKEN`.
4. **Closed-book risk is NOT closed.** Both tri-* tasks are echo-resistant but a
   model may recall that axum 0.6 sits on hyper 0.14, or that webpack parses with
   acorn, without reading anything. Recorded in each key's
   `scoring_evidence._residual_risk`. An untracked `tests/test_closed_book_gate.py`
   suggests another session is on it. **Do not read an echo pass as a closed-book
   pass** — and expect 005/006 to carry the same exposure (the babel and k8s
   package graphs are well-known).
5. `tests/test_task_output_path_consistency.py` red for 17 tasks (pre-existing).

## Pointers

- Root cause + gate analysis: `results/rryas_dataset/FINDINGS.md`
- Rescan quarantine: `python3 scripts/validation/curated_gate_analyzer.py --rescan-quarantine`
- Check one task: `python3 -c "import sys;sys.path.insert(0,'scripts/validation');
  import curated_gate_analyzer as A,pathlib as P;print(A.echo_leak(P.Path('<dir>')))"`
  — **an empty dict does not mean clean for a JSON deliverable** (see #2 above).
- **Hardcoded metadata locations found so far** (CSB carried 11; touch a task's
  `checks/` or weights and these move in the SAME commit):
  - `tests/test_phase4_verifiers.py` — checks, weights, gt/partial answers
  - `tests/test_topo_order_markdown_extraction.py` — `GRAPH_*` graphs; a *fixture*,
    deliberately NOT synced to ground truth, labelled so it is not copied back
  - `tests/test_file_extraction.py` — `NESTED_GT` = tri-babel's `required_files`
  - `configs/` manifests reference task ids (`sweep_manifest*.json`, `pilot_manifest.json`, …)
- Worked examples, increasing difficulty: `6cbbc54` (real PR data), `80ca4f8`
  (key named files that never call the helper), `2c1ac55` (drift in the wrong
  file), `55ef000` (premise false → re-scope), `1440322` (key absent,
  required_files inverted), **`1348620`** (fabricated key *inverted* the grade:
  fabrication 0.8125 > correct 0.4625), **`8007acc`** / **`8d861e5`** (chain
  invented from world knowledge; prompt-only echo scored a perfect **1.0000**,
  empty file 0.15).
