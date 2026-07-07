---
name: eb-checkpoint-scoring
description: >
  How an EnterpriseBench task becomes a number. Load this skill whenever you
  are (a) reading, changing, or debugging checkpoint scoring — task_score,
  total_score, reward.txt, weights, min(grep, judge), the Tier-2 LLM-judge cap;
  (b) touching lib/eb_verify/runner.py, lib/eb_verify/scoring.py,
  scripts/sandbox/test_runner.sh, or the scoring phases of
  scripts/orchestration/run_task.py (_run_scoring, _apply_llm_judge);
  (c) confused why a score changed in tests but not in real runs (the
  two-scorer silent-miss trap); (d) working with verification_modes,
  expected_solution.json, ground_truth.json, or solve_verify.py (layered
  ground truth); or (e) interpreting task_score vs normalized_score in
  results.json / analyze_scores.py output. NOT for writing new tasks
  (eb-task-authoring), artifact validators (eb-verification-library),
  container mechanics (eb-sandbox-execution), or the integrity invariant
  itself (eb-scoring-integrity-doctrine).
---

# eb-checkpoint-scoring — how a task becomes a number

All file paths, line numbers, and behaviors in this skill were verified
against the repo at `main` HEAD `7cfb8b0` on **2026-07-07**. Line numbers
drift; re-verify with the commands in "Provenance and maintenance" before
citing them elsewhere.

## When NOT to use this skill

| You want to…                                                                  | Use instead                     |
| ----------------------------------------------------------------------------- | ------------------------------- |
| Understand the scoring-integrity invariant and the incident catalog behind it | `eb-scoring-integrity-doctrine` |
| Add or debug an artifact validator (answer, code_patch, runbook, …)           | `eb-verification-library`       |
| Write or fix a task, its checkpoints, or its verifier scripts                 | `eb-task-authoring`             |
| Debug Docker/container mechanics, file copying, chown gates                   | `eb-sandbox-execution`          |
| Run a benchmark campaign and turn raw runs into figures                       | `eb-run-and-analyze`            |
| Work on the scorer_guard consolidation / `tests/integrity/` corpus            | `eb-scorer-guard-campaign`      |
| Get oriented in the repo at all                                               | `eb-orientation`                |

This skill is the map of the scoring machinery as it exists. It documents
several live bugs; do not "fix" them ad hoc — scoring-path changes are gated
(see "Change gating" at the end).

## Jargon (defined once)

| Term                            | Meaning here                                                                                                                                                                                                                         |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Checkpoint**                  | One graded sub-goal of a task. Declared in `task.toml` as a `[[checkpoints]]` entry (schema: 1–5 per task). Each has a bash **verifier** script.                                                                                     |
| **Verifier**                    | A bash script that inspects the workspace and prints JSON `{"score": 0.0–1.0, "passed": …, "detail": …}` to stdout. Fallback contract: no JSON → exit 0 means score 1.0, nonzero means 0.0.                                          |
| **Tier 1 / grep score**         | The deterministic verifier-script score. Called "grep" because most verifiers grep the agent's report for required facts.                                                                                                            |
| **Tier 2 / LLM judge**          | An LLM (default `cc:haiku` = Claude Code CLI running Haiku) that grades the agent's answer against a curated `expected_solution.json`. Acts as a **ceiling**: final = `min(grep, judge)`. It can only lower a score, never raise it. |
| **Tier 3 / solve-verification** | Offline structural verification (`scripts/solve_verify.py`): checks ground-truth file claims against real repo trees using AST/manifest parsers. Runs outside the task pipeline.                                                     |
| **`expected_solution.json`**    | Per-task curated ground truth for the judge: `{"checkpoints": {"<name>": {"expected_solution": str, "evaluation_criteria": [str]}}}`.                                                                                                |
| **`ground_truth.json`**         | Per-task factual answer key (copied into the container at `/workspace/.task/ground_truth.json` for verifiers to read).                                                                                                               |
| **`verification_modes`**        | Top-level `task.toml` array. Schema enum: `deterministic`, `llm_curator`, `solve_verified`, `structural_match`. `llm_curator` switches on Tier 2.                                                                                    |
| **`verifier_infra_error`**      | The failure class a run must get when scoring infrastructure (not the agent) failed. The doctrine: an infra failure must never be recorded as a `0.0` or as an inflated grep score.                                                  |

## 1. The checkpoint model

A task declares checkpoints in `task.toml`:

```toml
[[checkpoints]]
name = "identify_cve"                    # human-readable name
weight = 0.10                            # 0–1; all weights MUST sum to 1.0 (±0.01)
verifier = "checks/check_cve_id.sh"      # path relative to the task dir
description = "Agent correctly identifies CVE-2021-23337"
timeout_seconds = 30                     # default 120
```

- Schema: `schemas/task.schema.json` — `checkpoints` requires `name`,
  `weight`, `verifier`; `minItems: 1`, `maxItems: 5`. Optional `repo_deps`
  (per-checkpoint repo anchoring for CRNT — see `eb-crnt-and-task-mix`).
- The weight-sum-1.0 rule is enforced twice: `lib/eb_verify/schema_validator.py`
  (semantic rule, tolerance ±0.01) and `scripts/validate_tasks_preflight.py`
  (part of `make verify-tasks`).
- Verifier output contract: JSON on stdout wins; otherwise exit code decides
  (0 → score 1.0, nonzero → 0.0).

**Critical fact before anything else: at the verified checkout (`main` HEAD
`7cfb8b0`) the declared `weight` values only affect the library scorer.
Production scoring is equal-weighted (section 3). In production, `task.toml`
weights are authoring metadata.** Branch `3psg/document-equal-weighting`
exists specifically to document this.

> **Stale-on-pull warning.** The already-fetched `origin/main` is 4 commits
> ahead (`8dcc7fe`, `414651a`, `f403c2a`, `8a8236f`) and its `run_task.py`
> DOES write per-checkpoint `.meta` weight sidecars derived from `task.toml`
> (see `_setup_container` on `origin/main`, ~lines 575–615: `checkpoint_meta
= _verifier_meta_by_name(...)` → `_write_content_to_container(...
"/workspace/.verifiers/<name>.meta")`). After a pull, production honors
> declared weights and `task_score` becomes a toml-weighted 0–1 value. Run
> `git log main..origin/main --oneline` before relying on the
> equal-weighting fact. This skill (§2, §3, §7) is the single home for the
> weighting mechanics; siblings point here.

## 2. THE TWO SCORERS (the single most important thing in this skill)

There are two independent implementations of checkpoint scoring. They do not
share code, they disagree on weighting, score scale, and checkpoint naming,
and only one of them produces the published numbers.

|                                               | **Library scorer** (`CheckpointRunner`)                                                                                                                                                                 | **Production scorer** (`run_task.py` + `test_runner.sh`)                                                                                                                                                                                                                                                                                                                                                                                         |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Code                                          | `lib/eb_verify/runner.py` (`run_all`), `lib/eb_verify/scoring.py`                                                                                                                                       | `scripts/orchestration/run_task.py` (`_run_scoring`, `_apply_llm_judge`) + `scripts/sandbox/test_runner.sh` (runs in-container as `/workspace/test.sh`)                                                                                                                                                                                                                                                                                          |
| Invoked by                                    | `python -m eb_verify run <task.toml>` (i.e. `lib/eb_verify/cli.py`) and `tests/*` — **nothing else**. Verified: grep for `CheckpointRunner` finds only `cli.py`, `__init__.py`, `runner.py`, and tests. | Every real benchmark run (`scripts/run_benchmark.py` → `run_task.py`). This is where published numbers come from.                                                                                                                                                                                                                                                                                                                                |
| Weighting                                     | Honors `task.toml` weights: `total = Σ(score·weight) / Σ(weight)` (`scoring.py::compute_score`)                                                                                                         | **Equal-weighted at HEAD `7cfb8b0`.** `test_runner.sh` reads weight from a `<name>.meta` sidecar next to each verifier, defaulting to `1.0` — and at this checkout `run_task.py` **never writes `.meta` files** (verified: zero `.meta` references in `run_task.py`/`run_benchmark.py`). So every checkpoint weighs 1.0. **CHANGES ON PULL: `origin/main` writes `.meta` sidecars from `task.toml` weights** (see the §1 stale-on-pull warning). |
| Score scale                                   | `total_score` ∈ [0, 1] (weight-normalized)                                                                                                                                                              | `task_score` = **raw sum** of `score×weight` ∈ [0, N] where N = checkpoint count. Normalization happens later, in `scripts/analyze_scores.py`: `normalized = task_score / checkpoints_total` (divides by **count**, not weight sum).                                                                                                                                                                                                             |
| Checkpoint names                              | `task.toml` `name` fields                                                                                                                                                                               | **Verifier filenames**: `checks/check_cve_id.sh` → container `/workspace/.verifiers/cve_id.sh` (the `check_` prefix is stripped by `_setup_container`) → checkpoint name `cve_id` in results. See section 5 — this diverges from `task.toml` names in roughly half the corpus.                                                                                                                                                                   |
| Which verifiers run                           | Exactly the `[[checkpoints]]` list; a missing script scores 0.0 with detail "Verifier script not found"                                                                                                 | **Whatever `.sh` files are in `/workspace/.verifiers/`** (glob, alphabetical). A `checks/*.sh` file not declared in `task.toml` still gets scored; a declared checkpoint with no script silently doesn't exist.                                                                                                                                                                                                                                  |
| Tier-2 cap                                    | `min(grep, judge)` in `run_all`, names matched against `task.toml` names; warns about unmapped checkpoints (`_warn_unmapped_checkpoints`)                                                               | `min(grep, judge)` re-implemented independently in `_apply_llm_judge`, names matched against **filename-derived** names; unmapped checkpoints are skipped with no warning                                                                                                                                                                                                                                                                        |
| Artifact validation + grounded-citations gate | Yes (`validate_artifacts`, gate zeroes `total_score`)                                                                                                                                                   | Not in this path — at HEAD `7cfb8b0` the grounded-citations gate is absent from production `main` (it lives on a branch; audit 2026-07-06 finding #1)                                                                                                                                                                                                                                                                                            |
| Output                                        | `reward.txt` (human-readable summary)                                                                                                                                                                   | `results.json` `scores` dict + `verifier/output.json` under the run's output dir                                                                                                                                                                                                                                                                                                                                                                 |
| Test coverage                                 | `tests/test_runner.py` and friends — the tested one                                                                                                                                                     | Effectively untested at unit level; audited                                                                                                                                                                                                                                                                                                                                                                                                      |

### The silent-miss trap

Because the tested scorer is dead code from production's point of view
(2026-07-06 deep-audit finding #5, bead `cdzi`), **a change to the cap, the
weighting, or any scoring rule made in `lib/eb_verify/runner.py`/`scoring.py`
will pass all tests and change nothing in real runs.** The reverse also
holds: a change to `test_runner.sh` or `_apply_llm_judge` changes published
numbers with no unit test noticing.

Checklist for ANY scoring change:

- [ ] Identify which scorer you are actually editing (table above).
- [ ] If the rule must hold in real runs, it must land in
      `run_task.py`/`test_runner.sh` — not only in `lib/eb_verify/`.
- [ ] If you edit one implementation of a shared rule (e.g. the
      `min(grep, judge)` cap), grep for the other and change both or
      document why not: `grep -rn "min(grep" lib/ scripts/`.
- [ ] Ship tests in the same commit; note the production path has no unit
      harness, so a test may need to target the bash script or an extracted
      function.
- [ ] Scoring-path changes are gated — see "Change gating" below.

**PROVISIONAL pending Stephanie (discovery Q3):** whether the two scorers get
consolidated, the library path becomes a CI oracle, or `.meta`
weight-propagation lands so production honors declared weights, is an OPEN
decision. This skill teaches current reality and canonizes no future. Do not
build on any of the three futures without an explicit ruling.

## 3. Production scoring pipeline, step by step

This is the path that produces published numbers.

1. **Placement** (`run_task.py::_setup_container`): for each
   `task_dir/checks/check_<x>.sh`, copy to container
   `/workspace/.verifiers/<x>.sh` (prefix `check_` stripped, file made
   executable). `scripts/sandbox/test_runner.sh` is copied to
   `/workspace/test.sh`. `ground_truth.json` (if present) goes to
   `/workspace/.task/ground_truth.json`. Everything chowned to the agent
   user with a fail-loud gate (see `eb-sandbox-execution` for why).
2. **Tier 1** (`_run_scoring`, run_task.py:779): executes
   `bash /workspace/test.sh` inside the container with
   `WORKSPACE=/workspace TASK_DIR=/workspace/.task
PYTHONPATH=/workspace/.eb_verify` and `verifier_timeout` (default 600s).
   Parses stdout as JSON.
3. **Inside `test_runner.sh`** (full-run mode):
   - Iterates `/workspace/.verifiers/*.sh` in glob order.
   - Per verifier: weight and timeout read from an optional
     `<name>.meta` sidecar (`weight=…`, `timeout=…`; defaults 1.0 / 120s).
     No `.meta` is ever emitted by the orchestrator, so in practice:
     weight 1.0, timeout 120s for every checkpoint.
   - Runs the verifier under `timeout`; exit 124 → score 0.0
     "Timed out". Non-JSON stdout → exit-code fallback.
   - Extracts `score` and `passed` from the verifier JSON **with grep
     regexes**, not a JSON parser (`grep -oP '"score"\s*:\s*\K[0-9.]+'`).
     A verifier that prints valid JSON with `"score"` but no `"passed"`
     key counts as FAILED for `checkpoints_passed`/`all_passed` while its
     score still accumulates. Always print both keys.
   - Accumulates `task_score += score × weight` via `awk` float math
     (raw sum, no normalization).
   - Emits one JSON object to stdout (`task_score`, `all_passed`,
     `checkpoints_passed`, `checkpoints_total`, `checkpoints[]`) and also
     writes it to `/workspace/.results.json`. Exit 0 only if every
     checkpoint passed.
4. **Tier 2** (`_apply_llm_judge`, run_task.py:847) — only when the task's
   top-level `verification_modes` contains `llm_curator` AND
   `expected_solution.json` exists in the task dir:
   - Pulls the agent's answer out of the container: tries
     `/workspace/agent_output/answer.json` first, then any
     `/workspace/...` artifact path mentioned in the task's
     `instruction.md`.
   - **No agent output found → `scores["verifier_infra_error"]` is set and
     the run is routed to the re-run channel** (`failure_class` and `phase`
     become `verifier_infra_error`). This is the one correctly-guarded
     failure path in this function.
   - For each checkpoint entry whose (filename-derived) name has a key in
     `expected_solution.json`: judge scores 0–1, final =
     `min(grep_score, judge_score)`; `judge_score`/`grep_score` are
     recorded per checkpoint.
   - Recomputes `task_score = Σ(score × weight)` — again a raw sum (the
     code computes `total_weight` but does not divide by it).
5. **Persistence** (`_save_results`): the scores dict lands in
   `results.json` (top level `scores`) and `verifier/output.json` under the
   run output dir. Analysis (`make analyze` → `scripts/analyze_scores.py`)
   later computes `normalized_score = task_score / checkpoints_total` and
   writes `results/analysis/score_analysis.json`. Layout and promotion
   rules: `eb-run-and-analyze`.

### Known live holes in this path (do NOT rediscover these; they are filed)

All three confirmed live at HEAD `7cfb8b0` by the 2026-07-06 deep-audit and
re-verified 2026-07-07. Fixes exist on `fix/eb-*` branches, not `main`
(parked, not dead — check the bead store before re-landing anything):

1. **Broken `test.sh` persisted as a legit 0.0** — a crashed verifier is
   indistinguishable from an agent that failed everything.
2. **Judge failure inflates scores** — judge outages silently keep the
   **un-capped** grep score.
3. (Adjacent, owned by `eb-verification-library`): `code_patch.validate`
   collapses any git error into a false "no changes" 0.0.

Line-number anchors, exact failure paths, and re-verify commands for bugs
1–2 live in ONE home: **eb-scoring-integrity-doctrine (P4/P5)**. Do not
restate them here — one file changes when the scorer_guard campaign lands.

The doctrine these violate, and the consolidation campaign to close them
(`scorer_guard`, `tests/integrity/`), live in `eb-scoring-integrity-doctrine`
and `eb-scorer-guard-campaign`.

## 4. The checkpoint-name mismatch (measured 2026-07-07 — candidate finding)

The two scorers disagree on what a checkpoint is _called_, and Tier-2
matching is by name:

- Library: names come from `task.toml` (`identify_cve`).
- Production: names come from verifier filenames with `check_` stripped
  (`checks/check_cve_id.sh` → `cve_id`).
- `expected_solution.json` keys follow `task.toml` names — enforced by
  `scripts/validation/validate_expected_solutions.py` gate C1 ("every
  task.toml checkpoint name has a key").
- `_apply_llm_judge` looks up `expected_solution` keys by the
  **production** name. When they differ, the judge silently skips that
  checkpoint (`cp_gt is None → continue`) — the Tier-2 ceiling is not
  applied and the raw grep score stands, in exactly the runs that count.

Measured against the working tree on 2026-07-07 (script shipped with this
skill, `scripts/checkpoint_name_audit.py`):

- 180 active `task.toml` files under `benchmarks/` (excluding `_archived/`
  and `mined/`); 91 have at least one task.toml-name vs filename-derived-name
  mismatch.
- Of 112 tasks with `llm_curator` + `expected_solution.json`: in
  **10 tasks the production judge matches ZERO checkpoints** (Tier-2 is a
  complete no-op) and in **36 more it matches only some**.

Status: **candidate finding, not yet confirmed as a filed bead.** A
`bd list --search` pass this session found no existing bead for it, but the
search was shallow. Before filing or fixing: re-run the audit script, check
the bead store, and remember the fix touches the production scoring path
(gated — see below). The numbers above are a snapshot; re-measure, don't
quote.

```bash
python3 .claude/skills/eb-checkpoint-scoring/scripts/checkpoint_name_audit.py            # summary
python3 .claude/skills/eb-checkpoint-scoring/scripts/checkpoint_name_audit.py --verbose  # per-task detail
```

## 5. Library scoring pipeline (`CheckpointRunner`)

Use it as a local oracle / debugging harness, never as evidence about
production behavior.

```bash
pip install -e lib/                                   # once; see eb-build-and-test
python -m eb_verify run  benchmarks/<suite>/<task>/task.toml --workspace /path/to/workspace
python -m eb_verify check <checkpoint_name> benchmarks/<suite>/<task>/task.toml -w /path/to/workspace
```

`run_all()` (runner.py:335): sandbox health check (non-fatal) → per
checkpoint: Tier-1 verifier (subprocess, env `WORKSPACE`/`TASK_DIR`/`TASK_ID`,
scores clamped to [0,1]) → if `llm_curator` active and agent output found,
Tier-2 `min(grep, judge)` → artifact validation via the plugin registry →
`total_score = Σ(score·weight)/Σ(weight)` → grounded-citations gate (a failed
required artifact zeroes the total when the task demands grounded citations)
→ writes `reward.txt`. Exit code of `python -m eb_verify run` is 0 iff
`total_score > 0`.

Judge plumbing (both scorers share it): `lib/eb_verify/judge/` — model
string `cc:haiku` selects the Claude Code CLI backend; results carry
`score` (clamped 0–1), `passed`, `confidence` (high/medium/low),
`reasoning`, `evidence`.

Divergences to expect when comparing against a production run: weighted vs
equal weighting, `total_score` 0–1 vs `task_score` 0–N, `task.toml` vs
filename checkpoint names, artifact/groundedness gates present here only.

## 6. Layered ground truth (the three tiers)

Two related-but-different vocabularies exist; don't conflate them:

| Where                        | Field                | Allowed values                                                                                                             |
| ---------------------------- | -------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `task.toml` top level        | `verification_modes` | `deterministic`, `llm_curator`, `solve_verified`, `structural_match` — which verification strategies apply at scoring time |
| `task.toml` `[ground_truth]` | `tiers`              | `deterministic`, `curator`, `solve_verified` — which ground-truth curation tiers have been completed for the task          |

- **Tier 1 — deterministic**: the bash verifiers in `checks/`, reading the
  agent's report and (optionally) `/workspace/.task/ground_truth.json`.
  Always on.
- **Tier 2 — llm_curator**: `expected_solution.json` + LLM judge as a score
  ceiling, `min(grep, judge)`. The judge can never raise a score — it exists
  to catch answers that game the grep patterns (or grep patterns that are
  too generous). Curation gates: `make verify-expected-solutions`
  (`scripts/validation/validate_expected_solutions.py`) — C1: every
  `task.toml` checkpoint name keyed; H2: no `"_curation_required": true`
  left behind; H3 (warning): checkpoints with weight > 0.30 want ≥ 3
  evaluation criteria. A partially-curated `expected_solution.json`
  silently disables the cap for unmapped checkpoints — the library runner
  warns, production does not.
- **Tier 3 — solve_verified**: `scripts/solve_verify.py` — offline
  structural verification of ground-truth claims (does the claimed file
  exist at the pinned rev, do the claimed symbols parse) using per-language
  parsers (`python_ast`, `go_ast`, manifest parsers for JS/TS/Java/Ruby;
  structural path checks for more). It also compares structural results
  against recorded bash `task_score`s from `results/runs/`. Run it directly:
  `python3 scripts/solve_verify.py [--verbose]`. It is an audit tool, not
  part of per-run scoring.

`[ground_truth]` also carries `required_files` / `sufficient_files` (path,
repo, line_range, confidence, source ∈ deterministic|curator|both) and
`require_grounded_citations` (the groundedness gate — enforcement status per
scorer is in the section-2 table; details in `eb-verification-library`).

## 7. Trap quick-reference

| Trap                                                             | Reality                                                                                                                                                                                                                                                                                                    |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "I changed the weights in task.toml and the score didn't move"   | Production is equal-weighted; weights only affect `python -m eb_verify run`.                                                                                                                                                                                                                               |
| "task_score is 3.0, scores can't exceed 1.0"                     | Production `task_score` is a raw sum over checkpoints; divide by `checkpoints_total` (that's what `analyze_scores.py` does).                                                                                                                                                                               |
| "My scoring fix has green tests but runs are unchanged"          | You edited the library scorer; production is `run_task.py` + `test_runner.sh` (bead `cdzi`).                                                                                                                                                                                                               |
| "The judge should have capped this score"                        | Check (a) `verification_modes` contains `llm_curator`, (b) `expected_solution.json` exists, (c) the **filename-derived** checkpoint name is a key in it, (d) the judge didn't fail (failures currently keep un-capped grep — live bug), (e) an agent artifact was found.                                   |
| "Verifier prints `{"score": 1.0}` but the checkpoint shows FAIL" | Production greps for a literal `"passed": true`; print both keys.                                                                                                                                                                                                                                          |
| "A checkpoint in task.toml isn't in the results"                 | No matching `checks/*.sh` file — production scores files, not declarations. Extra `.sh` files get scored too.                                                                                                                                                                                              |
| "Run scored 0.0 — the agent must have failed"                    | Maybe. A broken `test.sh`, a `ModuleNotFoundError` in a verifier, or an unreadable instruction can all currently record 0.0 (live bug #1 above + incidents `hktt`/`s58f`). Check `results.json` for `scores.error`, `verifier/output.json`, and the doctrine skill's triage table before trusting any 0.0. |
| "Judge scored it 0.9, why is the final 0.4"                      | The cap is `min`, not `avg` — grep was 0.4. The judge can only lower.                                                                                                                                                                                                                                      |

## 8. Change gating

Any change to the production scoring path (`run_task.py` scoring phases,
`test_runner.sh`, verifier semantics, the cap, weighting) is
**HALT-branch-ready**: get the branch ready, ship tests in the same commit,
and stop for Stephanie's approval before merge.

**PROVISIONAL pending Stephanie (discovery Q5):** treat grading-keyword
relaxations in individual `task.toml`s, task-mix changes, and repo repins
with the same gate until ruled otherwise. Process mechanics (who dispatches
what, current dispatcher state) are internal-orchestration:
`eb-git-and-dispatch-workflow`.

## Provenance and maintenance

Authored 2026-07-07 against `main` HEAD `7cfb8b0` (retiring-fellow campaign,
authoring agent for eb-checkpoint-scoring). Every claim was verified against
the working tree that day. Re-verification one-liners:

```bash
# HEAD this skill was verified against
git log --oneline -1                                          # expect 7cfb8b0 or later — re-verify below if later

# CheckpointRunner still dead from prod's POV (expect: only cli.py, __init__.py, runner.py, tests/*)
grep -rln "CheckpointRunner" lib/ scripts/ tests/ | grep -v __pycache__

# Production still never emits .meta weight sidecars (expect: no output at 7cfb8b0;
# origin/main DOES emit them — if this greps hits, the pull landed and §1-3 weighting text is stale)
grep -n "\.meta" scripts/orchestration/run_task.py scripts/run_benchmark.py
git log main..origin/main --oneline   # non-empty => .meta weight delta not yet pulled

# test_runner still defaults weight 1.0 from .meta sidecar
grep -n "meta_file\|weight=" scripts/sandbox/test_runner.sh | head

# Production task_score still a raw (un-normalized) sum after the judge
grep -n "task_score" scripts/orchestration/run_task.py | tail -3

# Analysis still normalizes by checkpoint COUNT
grep -n "task_score / checkpoints_total" scripts/analyze_scores.py

# check_ prefix still stripped when copying verifiers into the container
grep -n 'startswith("check_")' scripts/orchestration/run_task.py

# min(grep, judge) still implemented twice (expect: runner.py AND run_task.py)
grep -rn "min(grep" lib/eb_verify/ scripts/orchestration/

# Live-bug status (broken test.sh → 0.0; judge failure → un-capped grep):
# anchors and re-verify commands live in eb-scoring-integrity-doctrine P4/P5

# Name-mismatch snapshot (numbers WILL drift; re-measure, don't quote)
python3 .claude/skills/eb-checkpoint-scoring/scripts/checkpoint_name_audit.py

# Schema enums for verification_modes / ground_truth.tiers
python3 -c "import json; s=json.load(open('schemas/task.schema.json')); print(s['properties']['verification_modes']['items']['enum'], s['properties']['ground_truth']['properties']['tiers']['items']['enum'])"

# Weight-sum gate still enforced
grep -n "1.0" lib/eb_verify/schema_validator.py | head -3 && grep -n "weights sum" -i scripts/validate_tasks_preflight.py

# Two-scorer future (Q3) still open? Check the bead store / branch
git branch -a | grep -i "cdzi\|equal-weighting"
```

Volatile facts to re-check if this skill feels stale: the three live bugs
(section 3) may have been fixed by the scorer_guard campaign; the
equal-weighting reality may have changed if `.meta` propagation landed; the
name-mismatch counts (section 4) drift with every task added.
