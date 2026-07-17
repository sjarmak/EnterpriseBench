# Handoff: prompt-echo remediation is DONE (quarantine 6 → 0)

**Epic:** `EnterpriseBench-rryas` (clean MCP vs baseline vs CLI headline study).
**Bead:** `EnterpriseBench-jn73.2.7.3.1.2` — "Re-scope 4 task-design checkpoints
that grade prompt-provided info". **Closed.** Its findings are in its comments.
**Parent:** `EnterpriseBench-jn73.2.7.3.1` (P0, pre-headline).
**Supersedes:** the 3-remaining revision of this file (`git log --follow`).

## State

`tests/integrity/known_prompt_echo_leaks.json` is **`[]`**. No task in the suite
is a known prompt-echo leak.

| task | commit | echo | fabrication | correct |
|---|---|---|---|---|
| `config-drift-004` | `1348620` | — | 0.81 → 0.00 | 0.46 → 1.00 |
| `tri-tokio-001` | `8007acc` | 1.00 → 0.00 | — | 0.65 → 1.00 |
| `tri-babel-001` | `8d861e5` | 1.00 → 0.00 | — | — → 1.00 |
| `refactor-orch-005` | `16615fc` | 0.32 → 0.00 | 0.88 → 0.00 | 0.37 → 1.00 |
| `refactor-orch-006` | `0963bfd` | 0.17 → 0.00 | 0.89 → 0.00 | 0.27 → 1.00 |
| `monorepo-boundary-003` | `e97e610` | 0.63 → 0.00 | 0.70 → 0.00 | 1.00 → 1.00 |

Empty file and missing file are 0.00 on every checkpoint of all six.

Full-suite diff against the session-start tree: **418 head vs 419 base, zero new
failures.** The gate earned its keep this phase: its first run surfaced **8 new
failures** the per-task work had missed (a dropped executable bit, and two
per-family test modules still holding the fabricated graphs — see the corrected
metadata list under Pointers). Run it; do not assume targeted tests are enough.

The one base-only failure, `tests/test_closed_book_gate.py::
test_committed_baseline_is_in_sync_with_corpus`, is another session's untracked
work: its `configs/closed_book_baseline.json` was computed from a corpus that
already includes these rewrites, so it passes at head and fails when they are
reverted. Expected, not ours.

## What this phase established (do not re-learn)

**Four of the six were FALSE-PREMISE, not prompt-only.** The handoff that opened
this phase warned that "the defect is in the prompt" is insufficient; that held
every time it was tested. 005 and 006 were the third and fourth cases:

- **005**: three of the four packages the key named **do not exist**
  (`@babel/plugin-transform-react-{compat,source,self}`; the real ones are
  `-react-jsx-*`). The names came from PR #17620's **title**, which uses Babel's
  shorthand — copied without opening `packages/`. The asserted diamond through
  the two presets is false at every edge, and the one package the key **missed**
  (`@babel/standalone`) is the only one that needed changing.
- **006**: three of the seven nodes (`build-infra`, `distroless-images`,
  `e2e-infra`) **do not exist**. A Go toolchain bump touches **no** staging repo
  — PR #137080 changed seven files, none under `staging/src/`.
- **003**: premise **sound**. The real Class B. Not re-scoped.

**A real edge can still be a phantom.** 006's asserted staging chain is *true* as
Go module facts — client-go really does require apimachinery — but carries **no
constraint for a toolchain bump**. An agent can "verify" the chain in a `go.mod`
and still be wrong. Recall of a graph is not a finding; knowing whether the
change traverses it is. Expect this class again.

**The key can contradict its own data.** 003's `changed_package` named
`helper-create-class-features-plugin` while its own `changed_files` listed not one
file from it. Read the key against itself before reading it against the repo.

**Case matters in the vocabulary split.** 006's `instruction.md` capitalises
`Staging` / `Distroless`, so `grep -coF` reported 0 and hid the leak while the
checks matched case-insensitively. Use **`grep -coiF`** when the check lowercases.

**Real PR file lists are the strongest ground truth available** and cost one
`curl`. `api.github.com/repos/<r>/pulls/<n>/files` settled 005, 006 and 003
outright, and in each case the *package set* it returned was the answer. No
`GITHUB_TOKEN` needed.

## The method (unchanged; steps 3 and 5 catch fabrication)

Verified per task: **echo → 0, correct → 1.0, old-key's-answer → ~0.**

1. **Verify the key against raw source at the pinned SHA.** Never trust it.
2. **Split the vocabulary.** `grep -coiF -- "<token>" instruction.md`. Count > 0
   ⇒ unusable as evidence. Judge against **instruction.md only** — `task.toml`'s
   `[task].prompt` is stale CSB metadata, never shown. **Re-sync it anyway**: it
   is a regeneration landmine, and it held the giveaway verbatim in all three
   tasks this phase (006's spelled out "client-go depends on apimachinery ...
   must propagate in dependency order").
3. **Score a plausible CORRECT answer, not just the key.** Score at minimum:
   echo, a fabrication built ONLY from prompt vocabulary, a correct answer, the
   old key's own answer, empty file, no file. The harness is ~30 lines; rebuild
   it (no repo copy exists yet — see `_residual_risk` note below for why one
   would be worth having).
4. **Kill free credit in both directions.** Absence of work is 0.0.
5. **Check recall AND precision.** Record dead ends in `not_affected` /
   `phantom_edges` with the reason.
6. **Run the FULL suite as a DIFF, toggling your own changes in the same tree.**
   Not a detached worktree — untracked files alone swing the count 222 ↔ 418.
7. **A check that emits no JSON verdict is BROKEN, not a 0.0.** Run
   `pytest tests/integrity/test_verifier_verdict_parseable.py`.

### The design that worked, three times

State the false claim in `instruction.md` as an **explicitly-flagged assumption
to verify** ("our tracking notes / release notes say X — do not take that as
given; if a package the notes call affected turns out not to be, say so"). This:

- turns the old giveaway into **anti-evidence** (restating it now scores 0),
- makes the **precision half fair to grade** (you may require the refutation only
  because the prompt raised the claim),
- keeps the task honest about provenance.

Then gate every checkpoint on the one token a reader has and no restatement can
produce: `standalone` (005), `dependencies.yaml` (006), `applyDecs2305` (003).

### Two traps to avoid when gating

- **Do not gate a checkpoint on a token it already scores** — circular. 003's
  `identify_boundary_violations` therefore carries an empty `scoring_evidence`
  list on purpose; the reason is in `_boundary_evidence_note`.
- **Do not over-gate.** A correct plan scoring 0.0 is worse than a fabrication
  scoring 0.3. On 005 every variant that caught the generic phrasing "the two
  preset updates can run concurrently" also failed a plausible correct plan (one
  justifying its group by step number, or writing "no preset work is needed"), so
  the looser check shipped and the **measured** residual (0.30 for a fabrication
  that name-drops `standalone`) is recorded in `_residual_risk` instead. 006 and
  003 close the same hole to 0.00 because their phantom-wave / per-package tests
  bite without needing extra vocabulary.

## Known-open — NOT this bead's

1. **Closed-book risk is NOT closed.** All six tasks are echo-resistant and none
   is proven closed-book-resistant: `acorn`, `0.14`, `standalone`,
   `dependencies.yaml` and `applyDecs2305` are all knowable to a model that knows
   these ecosystems. Recorded in every key's
   `scoring_evidence._residual_risk`. An untracked `tests/test_closed_book_gate.py`
   suggests another session is on it. **Do not read an echo pass as a closed-book
   pass.**
2. **`jn73.2.7.3.1.4`** — JSON-echo blind spot (81 tasks). The echo gate is
   vacuous for JSON deliverables: `A.echo_leak()` returning `{}` does **not**
   mean clean when a `.md` copy is not valid JSON. config-drift-004 was a live
   instance.
3. **`jn73.2.7.3.1.3`** — path fidelity, still needs `GITHUB_TOKEN`.
4. **`tests/integrity/test_noop_leak_sweep.py::test_allowlist_stays_minimal`** is
   RED on main: its allowlist still carries
   `ansible-galaxy-tar-regression-prove-001:root_cause`, which no longer leaks.
   Pre-existing at `59b3bc4`, the owning session's own commit
   (`EnterpriseBench-b5vk6`) — **tell that session**, it is a one-line delete.
5. **`tests/security/test_file_extraction_plugin.py` (untracked, another
   session)** imports `eb_verify.plugins.file_extraction`; the scorer lives under
   `eb_verify.scorers`. It raises a **collection error that aborts the entire
   suite**, so a naive `grep ^FAILED` gate reports "0 failures" from a suite that
   never ran. Currently `--ignore`d. Tell that session.
6. **`EnterpriseBench-e1eq`** — 005/006 score 0.0 in
   `tests/test_topo_order_markdown_extraction.py` because their recorded baselines
   put per-repo detail in markdown table cells the extractor does not read.
   Pre-existing and separate. Both tasks' `instruction.md` now ask for a **flat**
   numbered list, which reduces but does not remove the exposure.
7. `tests/test_task_output_path_consistency.py` red for 17 tasks (pre-existing).

## Pointers

- Root cause + gate analysis: `results/rryas_dataset/FINDINGS.md`
- Rescan: `python3 scripts/validation/curated_gate_analyzer.py --rescan-quarantine`
- Check one task: `python3 -c "import sys;sys.path.insert(0,'scripts/validation');
  import curated_gate_analyzer as A,pathlib as P;print(A.echo_leak(P.Path('<dir>')))"`
  — **an empty dict does not mean clean for a JSON deliverable** (see #2).
- **Hardcoded metadata locations** (touch a task's `checks/`, graph or weights and
  these move in the SAME commit). **The previous revision of this list was
  incomplete and the full-suite gate caught it — 8 new failures.** Corrected:
  - **`tests/test_refactor_orchestration_verifiers.py`** — `RefactorTaskSpec` per
    task: `gt_order`, `dep_graph`, `alt_order`, `repo_keywords`, and full
    `gt_answer` / `partial_answer` documents. **Asserts GT ≥ 0.85, empty ≤ 0.10,
    partial 0.15–0.75, reversed ≤ 0.30**, so it MUST track the key. Covers
    001–008 incl. **005 and 006**.
  - **`tests/test_monorepo_boundary_verifiers.py`** — same shape
    (`TaskVerifierSpec`), covers **003**. Note the parametrize ids are bare task
    numbers, so `-k 005` matches *both* modules' 005 — they are different tasks.
    Run the exact node id.
  - `tests/test_phase4_verifiers.py` — checks, weights, gt/partial answers. Does
    **not** cover either family above; do not read its absence as "no test
    hardcodes this task".
  - `tests/test_topo_order_markdown_extraction.py` — `GRAPH_*` graphs are
    *fixtures* replaying recorded baselines, deliberately NOT synced to ground
    truth (they assert what a recorded run scores, not what the key says).
    `GRAPH_005` and `GRAPH_TRI_BABEL_001` are now labelled do-not-copy; they still
    hold the fabricated graphs on purpose. **This is the exception** — the two
    family modules above are the rule.
  - `tests/test_file_extraction.py` — `NESTED_GT` = tri-babel's `required_files`
  - `configs/` manifests reference task ids (`sweep_manifest*.json`, …)
  - The **executable bit** on `checks/*.sh` is asserted by
    `test_all_tasks_valid.py::test_check_scripts_exist_and_executable`. Rewriting
    a check (rather than editing it) drops it; `chmod +x` and
    `git update-index --chmod=+x`.
- Worked examples, increasing difficulty: `6cbbc54` (real PR data), `80ca4f8`
  (key named files that never call the helper), `2c1ac55` (drift in the wrong
  file), `55ef000` (premise false → re-scope), `1440322` (key absent,
  required_files inverted), `1348620` (fabricated key *inverted* the grade),
  `8007acc` / `8d861e5` (chain invented from world knowledge; prompt-only echo
  scored a perfect 1.0000), **`16615fc`** (three of four named packages do not
  exist; the missed package was the whole answer), **`0963bfd`** (real edges,
  zero constraint; ground truth declared by the repo in
  `build/dependencies.yaml`), **`e97e610`** (sound premise, 0.45 checkpoint paid
  for one word the prompt supplied).
