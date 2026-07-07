---
name: eb-run-and-analyze
description: >
  Runbook for the layer AROUND task execution: batches, campaigns, and
  analysis. Load this when you need to: run a batch/campaign of tasks
  (run_benchmark.py, run_sweep.py) or choose between entry points,
  parallelize across OAuth accounts, set a cost budget (--budget-usd
  watchdog), rerun with repetitions (--rep), understand the results/runs/
  directory layout or results.json schema, run the analysis pipeline (make
  analyze / charts / report / paper-figures), regenerate paper figures,
  interpret score_analysis.json, or promote a run to official status
  (RUN_PROMOTION). Do NOT load for: executing or debugging ONE task in its
  Docker sandbox (eb-sandbox-execution owns single-task execution; this
  skill only carries the run_task.py flag table for dispatch context), how
  scoring works inside the container (eb-checkpoint-scoring), MCP mode
  wiring (eb-mcp-modes), or chain/event_replay session mechanics
  (eb-session-types).
---

# eb-run-and-analyze — running benchmarks and producing figures

All facts below were verified against the repo on 2026-07-07. Paths are
relative to the repo root. Anything marked **(as of 2026-07-07)** may drift;
re-verify with the one-liners in "Provenance and maintenance" at the bottom.

## When NOT to use this skill

| You want                                                                    | Use instead                     |
| --------------------------------------------------------------------------- | ------------------------------- |
| What happens _inside_ the container: test.sh, checkpoint scoring, judge cap | `eb-checkpoint-scoring`         |
| The non-negotiable scoring rules (never record a fake 0.0)                  | `eb-scoring-integrity-doctrine` |
| Dockerfile generation, image tags, clone-in-build, chown gates              | `eb-sandbox-execution`          |
| baseline / mcp_only / hybrid semantics, MCP preflight, tokens               | `eb-mcp-modes`                  |
| chain / event_replay / resume session mechanics                             | `eb-session-types`              |
| Getting tests green locally (pip install -e lib/, pytest markers)           | `eb-build-and-test`             |
| Writing or fixing a task                                                    | `eb-task-authoring`             |
| First map of the whole project                                              | `eb-orientation`                |

This skill covers the layer _around_ a task run: dispatching, parallelism,
budgets, where output lands, and the raw-runs → figures pipeline.

## Vocabulary (defined once)

- **Mode** — tool-access arm of the experiment: `baseline` (local tools only),
  `mcp_only` (Sourcegraph MCP only), `hybrid` (both). A controlled independent
  variable; every run records its mode.
- **Rep** — repetition index. `--rep 3` writes output under a `rep3/`
  subdirectory so repeated runs of the same task+mode don't overwrite.
- **Run dir** — the per-execution output directory containing `results.json`.
- **Campaign dir** — an ad-hoc results directory for a named study
  (`results/mcp_batch_v7/`, `results/smoke_mcp/`, …).
- **Official run** — a raw run promoted into `results/official_runs/<run_id>/`
  by the promotion orchestrator (see RUN_PROMOTION section).
- **Account** — OAuth account number N. `run_task.py --account N` loads a
  token from `~/.claude-homes/accountN/.claude/.credentials.json` on the host.
  The multi-account layout is environment-specific infrastructure; the flag
  and path are what the code does (run_task.py, `_load_oauth_token`).

## Which entry point?

| Situation                                                                | Command                                                |
| ------------------------------------------------------------------------ | ------------------------------------------------------ |
| One task, full control (reps, ablations, keep container)                 | `scripts/orchestration/run_task.py`                    |
| A batch: a suite, filtered set, or everything, with parallelism + budget | `scripts/run_benchmark.py`                             |
| The full 3-mode sweep with skip-already-scored + manifest                | `scripts/run_sweep.py`                                 |
| Turn raw runs into JSON/charts/report/figures                            | `make analyze` / `charts` / `report` / `paper-figures` |
| Bless a run as official                                                  | `scripts/orchestration/run_promotion_orchestrator.py`  |

`run_benchmark.py` is a _dispatcher_: it discovers `task.toml` files, filters
them, and shells out to a per-session-type runner. `run_task.py` is the
_worker_ that actually builds the Docker sandbox, runs the agent, and scores.
The repo convention (CLAUDE.md) is: **always run benchmark tasks in parallel,
never sequentially** — `run_task.py` is single-task, so parallelism lives in
the caller (`run_benchmark.py -j`, `run_sweep.py`, or shell `&` + `wait` with
different accounts).

## Running one task: run_task.py

```bash
# Dry run: build the container and validate setup, no agent
python3 scripts/orchestration/run_task.py \
    benchmarks/customer_escalation/err-provenance-01/task.toml --dry-run

# Real run on account 2, mcp_only, repetition 1
python3 scripts/orchestration/run_task.py \
    benchmarks/customer_escalation/err-provenance-01/task.toml \
    --account 2 --mode mcp_only --rep 1
```

The positional argument is the **path to task.toml**. (The README's example
`run_task.py --task <id>` is stale — there is no `--task` flag, verified
2026-07-07 against the argparse block.)

Flags (verified against `scripts/orchestration/run_task.py` `main()`):

| Flag                                | Default    | Meaning                                               |
| ----------------------------------- | ---------- | ----------------------------------------------------- |
| `--source {mirror,upstream}`        | `mirror`   | Clone source for task repos                           |
| `--agent CMD`                       | `""`       | Agent command (e.g. `claude -p`). See default below   |
| `--timeout N`                       | 1800       | Max seconds for agent execution                       |
| `--build-timeout N`                 | 1800       | Max seconds for Docker image build                    |
| `--verifier-timeout N`              | 600        | Max seconds for verifier/scoring                      |
| `--memory MB`                       | 8192       | Container memory limit                                |
| `--output-dir PATH`                 | see below  | Where results land                                    |
| `--dry-run`                         | off        | Build + validate only, no agent                       |
| `--no-build`                        | off        | Reuse existing image                                  |
| `--keep-container`                  | off        | Keep container for debugging                          |
| `--account N`                       | none       | OAuth account; injects `CLAUDE_CODE_OAUTH_TOKEN`      |
| `--mode {baseline,mcp_only,hybrid}` | `baseline` | Tool-access mode                                      |
| `--max-concurrent-large N`          | 3          | **Accepted but not enforced** (help text says so)     |
| `--rep N`                           | none       | 1-based repetition; adds `rep<N>/` to output dir      |
| `--ablation-variant NAME`           | none       | Adds `-ablate-<variant>` to the image tag             |
| `--min-disk-gb G`                   | 10.0       | Disk preflight; raise when running many tasks at once |
| `-v/--verbose`                      | off        | Debug logging                                         |

**Default output dir** (when `--output-dir` is not given):
`results/runs/<task_id>/<mode>/` — plus `rep<N>/` when `--rep` is set. An
explicit `--output-dir` wins over everything.

**Default agent command**: when `--account` is set and `--agent` is empty,
run_task uses (verified constant `DEFAULT_OAUTH_AGENT_COMMAND`):

```
claude --dangerously-skip-permissions --max-turns 50 --verbose --output-format stream-json -p
```

In `mcp_only`/`hybrid` modes, ` --mcp-config /home/agent/.mcp.json` is
appended if not already present. With no `--account` and no `--agent`, no
agent runs (useful only with `--dry-run`).

**Exit code**: 0 iff the run succeeded (`result.success`), 1 otherwise. A
printed summary block shows task, mode, phase, image tag, output dir, timing,
and `task_score (passed/total checkpoints)`.

## Running a batch: run_benchmark.py

```bash
# All tasks in one suite, sequential, baseline
python3 scripts/run_benchmark.py benchmarks/customer_escalation/ --all

# Everything, parallel across accounts 1-5, one worker per account
python3 scripts/run_benchmark.py benchmarks/ --all --account 1-5 -j0

# 3 workers on accounts 1,3,5; medium difficulty; first 5 tasks only
python3 scripts/run_benchmark.py benchmarks/ --all --account 1,3,5 -j3 \
    --difficulty medium --limit 5

# Both arms of an experiment in one go, skipping already-green tasks
python3 scripts/run_benchmark.py benchmarks/ --all --modes baseline,mcp_only \
    --account 1-5 -j0 --skip-completed --budget-usd 50

# List what would run, without running (two equivalent safety valves)
python3 scripts/run_benchmark.py benchmarks/ --all --dry-run
python3 scripts/run_benchmark.py benchmarks/ --all --limit 0
```

Behavior (verified against `scripts/run_benchmark.py`, 900 lines):

- **Discovery**: positional path is a `task.toml` or a directory; directories
  are `rglob`'d for `task.toml`. Pointing at a directory requires `--all`
  unless the directory itself contains a `task.toml`.
- **Filters**: `--difficulty {medium,hard,expert}`, `--session-type`,
  `--task-type`, `--limit N`. `--limit 0` lists matches and exits.
- **Session-type routing** (`RUNNERS` map): `single` →
  `scripts/orchestration/run_task.py`, `chain` →
  `scripts/orchestration/chain_runner.py`, `event_replay` →
  `scripts/orchestration/event_replay.py`. `resume` is **skipped** with
  "not yet implemented" (a real accepted value, a real no-op — by design,
  see `eb-session-types`).
- **Passthrough** to runners: `--source`, `--agent`, `--timeout`,
  `--account`, `--mode` (always appended), `--dry-run`.
- **Accounts**: `--account` accepts `1`, `1-5`, `1,3,5`, `1-3,5`. With
  multiple accounts and `-j>1`, tasks are assigned **round-robin** to
  accounts. `-j0` = auto: one worker per account (minimum 1).
- **Per-task hard cap**: the dispatcher runs each task with
  `subprocess.run(..., timeout=3600)`. A passthrough `--timeout` larger than
  3600 is meaningless through this path — the dispatcher kills the runner at
  1 hour and records status `timeout`. For longer tasks, invoke
  `run_task.py` directly.
- **`--skip-completed`**: skips tasks whose
  `results/runs/<task_id>/<mode>/results.json` (or legacy
  `results/runs/<task_id>/results.json`, baseline only) parses and contains
  `"success": true`. **Trap**: the completed-check runs once, against
  `--mode` only (default `baseline`). In a `--modes a,b` multi-mode run it
  does NOT check per mode — a task green in baseline but never run in
  mcp_only is skipped for _both_ arms if `--mode` resolves to baseline.
  Verified in `main()`: `check_mode = args.mode` before the mode loop.
- **Multi-mode** (`--modes baseline,mcp_only,hybrid`): runs the full task
  list once per mode, passing `--output-dir results/runs/<task_id>/<mode>`
  to the runner. Statuses per task: `completed`, `error`, `timeout`,
  `skipped`, `dry-run`.
- **Summary**: written to `results/runs/<run_id>/summary.json` where
  `run_id` is a UTC timestamp `%Y%m%d_%H%M%S`. This is why timestamp
  directories sit next to task-id directories under `results/runs/`.
  Contains totals, `previously_completed`, `cumulative_cost_usd`,
  optional `budget_usd`, and the per-task result list.
- **Exit codes**: 0 normal, 1 no tasks found, **3 budget exceeded**.

### Budget watchdog (--budget-usd)

- `--budget-usd X` sets a cumulative cost limit; `--budget-warn-pct P`
  (default 80) logs a warning at P% of X.
- Cost per task is read _after the task finishes_ from its
  `results.json → tool_usage.cost_usd` (0.0 if missing).
- **Sequential mode** (`-j1` or default): budget is checked _before each
  task starts_; on breach the remaining tasks are skipped.
- **Parallel mode** (`-j>1`): all tasks of the current mode are submitted to
  the pool up front. On breach the dispatcher logs
  `STOPPED ... In-flight tasks will finish` — and in fact **every already
  submitted task of the current mode runs to completion** (there is no break
  out of the result loop and futures are not cancelled; verified in the
  `ProcessPoolExecutor` block). What the breach actually stops is any
  _subsequent mode_ in a `--modes` list. Treat `--budget-usd` in parallel
  mode as a soft, mode-granular brake, not a hard cost ceiling. Budget your
  worst case as `budget + (workers × max single-task cost)`.

### Known dispatcher gaps (as of 2026-07-07 — open, not fixed)

1. **event_replay tasks cannot be dispatched through run_benchmark.py.**
   The dispatcher always appends `--mode <mode>` to the runner command, but
   `scripts/orchestration/event_replay.py` does not define `--mode` and uses
   strict `parse_args()` — verified live: it exits with
   `error: unrecognized arguments: --mode baseline`. It also expects a task
   _directory_ positional while the dispatcher passes the `task.toml` _path_.
   Such tasks record status `error`. Run them directly (see
   `eb-session-types`). One active `event_replay` task exists
   (`benchmarks/incident_response/event-replay-click-ci-001`; a second is
   archived under `benchmarks/_archived/`).
2. **chain tasks silently ignore agent/account/timeout.** `chain_runner.py`
   accepts `--source/--agent/--timeout/--account/--dry-run` with the literal
   comment "accepted but not used here", and does accept `--mode`. So a
   chain task dispatched with `--account 3` will not use account 3's token
   the way `run_task.py` does. See `eb-session-types` for how chain runs
   actually execute.
3. **`--rep` is not plumbed through run_benchmark.py.** Repetition studies
   (the `rep1..rep3` trees on disk) are driven by direct `run_task.py --rep N`
   invocations, not the dispatcher.

## Full sweeps: run_sweep.py

```bash
# See what a full 3-mode sweep would do (prints commands, writes manifest)
python3 scripts/run_sweep.py --modes baseline,mcp_only,hybrid

# Manifest only
python3 scripts/run_sweep.py --manifest-only

# Actually execute, accounts 1-5
python3 scripts/run_sweep.py --execute --account 1-5
```

`scripts/run_sweep.py` orchestrates all tasks × modes, **skips task+mode
combos that already have scores**, and writes a manifest of every pair with
status to `configs/sweep_manifest.json` (`--output` to change). Default
`--account` is `1-5`. Without `--execute` it only prints the run commands —
safe to invoke. `--results-dir` (repeatable) adds extra directories to the
already-scored check.

## Where output lands: the results/ layout

Verified on disk 2026-07-07. Three per-task layouts coexist:

```
results/runs/<task_id>/...                      # legacy single-mode (oldest runs)
results/runs/<task_id>/<mode>/...               # mode-partitioned (current default)
results/runs/<task_id>/<mode>/rep<N>/...        # mode + repetition (rep studies)
```

Each run dir contains:

```
results.json        # the scored record (schema below)
config.json         # the TaskRunConfig used
task_metrics.json   # per-task metrics
agent_stdout.log    # agent stdout (host-side capture)
agent_stderr.log
agent_trace.jsonl   # streamed agent events
agent/              # stdout.log, stderr.log (in-container capture)
verifier/output.json
```

`results.json` top-level keys (verified from a real run):
`task_id, success, phase, error, failure_class, image_tag, scores, timing,
tool_usage, config, task_metadata`. Inside `scores`: `task_score`,
`all_passed`, `checkpoints_passed`, `checkpoints_total`, `repos`, and a
`checkpoints` list with per-checkpoint `name/weight/score/passed/duration_ms/
exit_code`. Inside `tool_usage`: `total_input_tokens, total_output_tokens,
cost_usd, num_turns, mcp_tool_calls`. How those scores are _produced_ is
`eb-checkpoint-scoring`'s territory; what `success`/`failure_class` may and
may not mean is `eb-scoring-integrity-doctrine`'s.

Special directories under `results/runs/` (as of 2026-07-07):

| Dir                                                                | What it is                                                                         |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| `<YYYYMMDD_HHMMSS>/`                                               | run_benchmark summary dirs (`summary.json` only)                                   |
| `_invalidated/`                                                    | runs pulled from the record (still contain results.json — see analysis trap below) |
| `_batch_summaries/`, `_baseline_backfill_*/`, `_p6ux4_rerun_logs/` | batch bookkeeping from past campaigns                                              |

Campaign dirs under `results/` (siblings of `runs/`): `mcp_batch/` … `mcp_batch_v7/`,
`smoke_*` (many), `mcp_lift_study/`, `phase1_pilot/`, `rescore_aq8e/`,
`rescore_uu17/`, `rerun_pt0n/`, `official_runs/`, `sample_runs/`,
`analysis/`. The `rescore_*`/`rerun_*` dirs are tied to specific past audit
beads — treat them as parked-not-dead; check the bead store before touching
(**PROVISIONAL pending Stephanie** — Q5 position: retired/rescore artifacts
are fenced off as parked, never declared dead).

## From raw runs to figures: the analysis pipeline

```bash
make analyze          # → results/analysis/score_analysis.json (always re-scans raw runs)
make charts           # analyze + PNGs → results/analysis/charts/
make report           # analyze + markdown → results/analysis/report.md
make paper-figures    # charts + report + cp charts/*.png → paper/figures/
make paper            # alias for paper-figures (paper/paper.md is HAND-WRITTEN)
make clean            # removes score_analysis.json, report.md, charts/ — never raw runs
```

`make paper-figures` is the single command that regenerates every figure used
in `paper/paper.md` (the Makefile's own "Phase 8 deliverable" note). The
paper text itself is never generated.

### Change gating for the analysis layer

`analyze_scores.py` ingestion is part of the gated scoring path
(eb-scoring-integrity-doctrine, "Doctrine checklist": scoring path =
run_task.py scoring functions, test_runner.sh, lib/eb_verify/, checks
templates, **or analyze_scores.py ingestion**). Any change to
`scripts/analyze_scores.py`, the dedup rule below, or the Makefile analysis
targets can silently move published numbers: treat it as
**HALT-branch-ready** — tests in the same commit, stop at branch-ready,
Stephanie approves before merge (mechanics: eb-git-and-dispatch-workflow).

### What `make analyze` actually computes (scripts/analyze_scores.py)

- **Input scan**: defaults to `results/runs/` **plus every
  `results/mcp_batch*` and `results/smoke_*` directory**; override/extend
  with repeatable `--results-dir`. It `rglob`s for `results.json`.
- **Row filter**: a results.json is dropped (with a logged warning) unless it
  has `task_id`, a non-empty `scores`, and `checkpoints_total > 0`.
- **Normalization**: `normalized_score = task_score / checkpoints_total`.
- **Mode inference**: `config.mode` inside the results.json wins; falls back
  to directory-name heuristics (`<mode>/` parent dir, `_hybrid`/`_mcp_only`
  suffixes, `mcp_batch*`/`smoke_*` name hints); final fallback `baseline`.
- **Deduplication — the big one**: per `(task_id, mode)` it keeps the run
  with the **highest normalized score**. Consequences, both verified:
  1. Reps are collapsed to **best-of**, not mean — `score_analysis.json` is
     not a variance-aware view (that is `reproducibility_check.py`'s job).
  2. **`results/runs/_invalidated/` is NOT excluded** — the scanner has no
     invalidation filter (zero matches for "invalid" in the script), so an
     invalidated run with a higher score can shadow the valid rerun of the
     same task+mode. Until a filter lands, either move invalidated runs out
     of `results/runs/` entirely or pass explicit `--results-dir` sets when
     the distinction matters. **Moving or removing run artifacts changes the
     input set of every future aggregate: it is an explicit, audited event**
     (record what moved, where, and why — the `aq8e`/`uu17` rescore-script
     pattern; see eb-scorer-guard-campaign Phase 5), never a silent cleanup.
     Treat surprising per-task winners with suspicion and check
     `source_path` in `per_task` output.
- **Output sections**: `by_mode`, `by_suite`, `by_difficulty`,
  `by_task_type`, `mcp_delta`, `calibration_bias`, `per_task` (each row
  carries `source_path` so you can trace any number to its file).
- **scipy is optional**: without it the Wilcoxon significance test is
  skipped with a note in the output — not an error.
- When reading `mcp_delta`: report whatever sign the data shows; the current
  recorded position is that no positive MCP lift may be stated as fact until
  an artifact proves it (**PROVISIONAL pending Stephanie** — Q4 position:
  prove the result rigorously whichever sign it has).

### Chart/report dependencies and the cost-report path trap

- `scripts/generate_charts.py` imports **matplotlib, seaborn, numpy**.
  As of 2026-07-07 none of these are in the checked-in `venv/` and none are
  declared in `lib/pyproject.toml` (its deps are only tomli + jsonschema).
  `make charts` therefore fails in a fresh clone until you
  `pip install matplotlib seaborn numpy`. `generate_report.py` and
  `analyze_scores.py` are stdlib-only (scipy optional).
- **Path mismatch to know about**: the Makefile looks for the optional cost
  report at `results/analysis/cost_report.json` and the reproducibility
  report at `results/analysis/reproducibility_report.json` (it passes them
  to charts/report only if they exist). But the producers default elsewhere:
  `scripts/cost_tracker.py --output` defaults to `results/cost_report.json`
  and `scripts/reproducibility_check.py --output` defaults to
  `results/reproducibility_report.json`. To feed the make pipeline:

```bash
python3 scripts/cost_tracker.py --output results/analysis/cost_report.json
python3 scripts/reproducibility_check.py --output results/analysis/reproducibility_report.json
make paper-figures
```

As of 2026-07-07 neither file exists at either location, so `make charts`
/ `make report` silently run without cost/repro sections — that is the
wildcard-conditional working as designed, not a failure.

## Promoting a run: RUN_PROMOTION

Full doc: `docs/RUN_PROMOTION.md`. Summary of the verified mechanics:

- One coordinator: `scripts/orchestration/run_promotion_orchestrator.py`.
  It promotes `results/runs/<run_id>/` → `results/official_runs/<run_id>/`
  through 9 steps: validate inputs → preflight → CRNT → expected-solutions →
  stage metrics/charts/report into `_staging/<run_id>/` → single-`os.rename`
  publish → registry update (`results/official_runs/_registry.json`,
  tmp+rename with `.bak` restore).
- **Atomic**: on failure every reversible step is rolled back and a forensic
  snapshot lands in `results/official_runs/_failures/<run_id>_<UTC>/`
  (`context.json`, `error.json`, `completed_steps.json`).

```bash
# Read-only validation — never writes staging or final
python3 scripts/orchestration/run_promotion_orchestrator.py \
    --run-id <run_id> --validate-only

# Plan without writing
python3 scripts/orchestration/run_promotion_orchestrator.py \
    --run-id <run_id> --dry-run

# Full promotion
python3 scripts/orchestration/run_promotion_orchestrator.py \
    --run-id <run_id> --target-state official

# Resume after a transient failure at step N (1-based; see _progress.json)
python3 scripts/orchestration/run_promotion_orchestrator.py \
    --run-id <run_id> --resume-from-step N
```

- The `<run_id>` is a directory name under `results/runs/` — for
  dispatcher-produced batches that is the timestamp id whose dir holds
  `summary.json`.
- Step 8 refuses to overwrite an existing `official_runs/<run_id>/`; re-promotion
  requires manually removing the old final dir first (registry entries are
  replaced, not duplicated).
- **Current state (verified 2026-07-07): no run has ever been promoted.**
  `results/official_runs/` contains only `_failures/` snapshots (from
  `does-not-exist` validation exercises); `_registry.json` does not exist
  yet. Promotion is built and documented but unexercised on real data —
  expect first-use friction and budget time to verify each step's output.
- Whether a run _deserves_ promotion is a scoring-integrity question
  (pristine verifier, no silent misscores) — gate on
  `eb-scoring-integrity-doctrine` before promoting anything.

## Pre-run and post-run checklists

Before launching a batch:

- [ ] `venv` active or `pip install -e lib/` done (see `eb-build-and-test`)
- [ ] Docker daemon up; disk headroom ≥ `--min-disk-gb` × concurrent tasks
- [ ] `--dry-run` (or `--limit 0`) first: confirm the task list is what you think
- [ ] MCP modes only: `SOURCEGRAPH_ACCESS_TOKEN` exported (run_task warns,
      and preflight gates — see `eb-mcp-modes`)
- [ ] Parallel: `--account` spread chosen; remember round-robin assignment
- [ ] Budget set with the parallel-mode caveat priced in
- [ ] Long tasks (>1h agent time): direct `run_task.py`, not the dispatcher

After the batch:

- [ ] Check `results/runs/<run_id>/summary.json` — `errors`/`timeout` counts
- [ ] Spot-check one `results.json` per mode: `config.mode` correct,
      `tool_usage.cost_usd` present, `failure_class` empty for successes
- [ ] `make analyze` and read `by_mode` counts — do run counts match what
      you launched? Missing rows mean dropped/filtered results.json files
- [ ] Anything invalidated: move it out of the scan path as an audited
      event with a recorded reason (dedup trap above)

## Provenance and maintenance

Authored 2026-07-07 against the repo state of that day (main, working copy).
Every command/flag was verified by reading the argparse blocks and Makefile,
inspecting `results/` on disk, and one live argparse check of
`event_replay.py`. Re-verify volatile claims:

```bash
# Dispatcher flags (parallelism, budget, modes, skip-completed)
python3 scripts/run_benchmark.py --help

# Worker flags (rep, ablation, output-dir default, account)
python3 scripts/orchestration/run_task.py --help 2>&1 | head -60

# Dispatcher's fixed 3600s per-task cap
grep -n "timeout=3600" scripts/run_benchmark.py

# skip-completed multi-mode trap still present?
grep -n "check_mode = args.mode" scripts/run_benchmark.py

# Parallel budget: still no future cancellation / loop break?
grep -n "In-flight tasks will finish" scripts/run_benchmark.py

# event_replay still rejects --mode? (expect: unrecognized arguments)
python3 scripts/orchestration/event_replay.py /nonexistent --mode baseline; true

# Default agent command
grep -n "DEFAULT_OAUTH_AGENT_COMMAND =" scripts/orchestration/run_task.py

# Output-dir layout incl. rep<N>
sed -n '1518,1530p' scripts/orchestration/run_task.py

# Analysis defaults, dedup rule, _invalidated non-filtering
grep -n "mcp_batch\|smoke_\|normalized_score > best" scripts/analyze_scores.py
grep -cn "invalid" scripts/analyze_scores.py   # 0 hits = trap still live

# Chart deps still missing from venv?
venv/bin/python -c "import matplotlib" 2>&1 | tail -1

# Cost/repro report path mismatch
grep -n "COST_REPORT\|REPRO_REPORT" Makefile
grep -n "results/cost_report.json" scripts/cost_tracker.py

# Promotion pipeline & current official_runs state
python3 scripts/orchestration/run_promotion_orchestrator.py --help | head -20
ls results/official_runs/    # only _failures/ = still no promoted run

# Makefile pipeline targets
make help
```
