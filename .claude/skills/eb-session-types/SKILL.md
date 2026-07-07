---
name: eb-session-types
description: >
  EnterpriseBench session types: single, chain, event_replay, and resume.
  Load this when a task.toml has session_type != "single"; when working on
  chain_runner.py, event_replay.py, event_schema.py, action_scorer.py,
  session.py, milestone.py, or branch_manager.py; when run_benchmark.py skips
  a task with "not yet implemented" or "unknown session_type"; when authoring
  or debugging a multi-session (chain) task, an event-stream (event_replay)
  task, or a resume task; when you see events.jsonl / oracle_actions.jsonl /
  actions.jsonl files or eb-chain-* git branches; or when schema validation
  complains about session_count, events, or resume_state.
---

# EnterpriseBench Session Types

All facts verified against the repo at commit `7cfb8b0` on 2026-07-07. Run all
commands from the repo root.

**Definition.** A task's `session_type` (in `[task]` of its `task.toml`)
declares how many agent invocations the task takes and how state moves between
them. It is one of exactly four values (`schemas/task.schema.json`, `enum`):
`single`, `chain`, `event_replay`, `resume`.

## When NOT to use this skill

| You actually need                                                                      | Go to sibling                   |
| -------------------------------------------------------------------------------------- | ------------------------------- |
| Running one ordinary (single) task in Docker, sandbox internals, docker-cp traps       | `eb-sandbox-execution`          |
| How checkpoints become a number, the two-scorer split, judge cap                       | `eb-checkpoint-scoring`         |
| Writing a new task, `make verify` gates, difficulty strata                             | `eb-task-authoring`             |
| Campaign-level running (`run_benchmark.py` parallelism, accounts, budget) and analysis | `eb-run-and-analyze`            |
| Artifact validators (`lib/eb_verify/`)                                                 | `eb-verification-library`       |
| baseline / mcp_only / hybrid tool-access modes                                         | `eb-mcp-modes`                  |
| The score-is-only-valid-if rule and silent-misscore bug class                          | `eb-scoring-integrity-doctrine` |

This skill owns exactly one axis: what each `session_type` means, which runner
handles it, how state and scoring work per type, and the verified gaps.

## The four types at a glance (state of the repo, 2026-07-07)

| session_type   | Runner (via `scripts/run_benchmark.py` `RUNNERS` map) | State mechanism                               | Scoring                                                  | Active tasks                     | Maturity                                                                                         |
| -------------- | ----------------------------------------------------- | --------------------------------------------- | -------------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------ |
| `single`       | `scripts/orchestration/run_task.py`                   | none (one shot)                               | checkpoints via in-container `test.sh`                   | 178 of 180 (working tree)        | production                                                                                       |
| `chain`        | `scripts/orchestration/chain_runner.py`               | git branch handoff between sessions           | milestones between sessions + weighted final checkpoints | 1 (`chain-err-flask-import-001`) | prototype: simulation only, no real agent wired                                                  |
| `event_replay` | `scripts/orchestration/event_replay.py`               | `events.jsonl` in, `actions.jsonl` out        | 4-dimension action scorer vs oracle                      | 1 (`event-replay-click-ci-001`)  | offline scoring works; sandbox integration not implemented; dispatcher routing broken (see Bugs) |
| `resume`       | none — dispatcher skips                               | (design: pre-populated branch + progress doc) | (design: same as single)                                 | 0                                | accepted no-op skip; nothing implemented                                                         |

Counts verified 2026-07-07: `grep -rh 'session_type' benchmarks/
--include=task.toml` gives 2 chain, 2 event_replay, 207 single, 0 resume
across ALL of `benchmarks/`; excluding `_archived/` the active census is
178 single / 1 chain / 1 event_replay / 0 resume = 180 active (a
working-tree count — only 116 task.tomls are tracked at HEAD `7cfb8b0`; see
eb-orientation §3; the 112 in README/CLAUDE.md is stale). One chain
(`benchmarks/_archived/chain_example/`, task id
`dep-mgmt-proto-v2-chain-001`) and one event_replay
(`benchmarks/_archived/event_replay_example/`, task id
`ir-deploy-error-spike-001`) are archived. `docs/LEGACY_CSB_ASSESSMENT.md`
marks both archived examples "Retire" (template-only, not real tasks). Do not
resurrect them without checking the bead store and branch state first
(PROVISIONAL pending Stephanie: archived material is treated parked-not-dead,
per discovery Q5).

Design intent vs reality: `docs/internal/PRD.md` targets 10-15 chain, 5-10
event_replay, and 10-15 resume tasks; `docs/TASK_TYPE_PRD.md:773` defers
event_replay authoring to Phase 2 ("authoring cost too high for Phase 1").
Those targets are aspirational — the shipped counts are the table above.

## How dispatch works

`scripts/run_benchmark.py` parses every `task.toml`, reads
`task.session_type` (default `"single"` when absent), and routes:

```python
RUNNERS = {
    "single":       scripts/orchestration/run_task.py,
    "chain":        scripts/orchestration/chain_runner.py,
    "event_replay": scripts/orchestration/event_replay.py,
}
```

- `resume` → logged `[skip] ... session_type 'resume' not yet implemented`,
  result status `skipped`. This is accepted behavior, not a bug.
- Any other unknown value → `[skip] ... unknown session_type`, status `skipped`.
- Each runner is invoked as
  `python3 <runner> <path/to/task.toml> <passthrough flags>` with a hardcoded
  3600 s subprocess timeout per task.
- `run_task.py` itself hard-rejects non-single tasks
  (`scripts/orchestration/run_task.py:194-199`): "run_task.py only handles
  single-session tasks ... Use chain_runner.py for chains." So you cannot
  accidentally score a chain task through the single-task path.

Useful filters (verified):

```bash
# List tasks by session type without running anything
python3 scripts/run_benchmark.py benchmarks/ --all --session-type chain --limit 0
# Dry-run shows the exact runner command that would execute
python3 scripts/run_benchmark.py benchmarks/ --all --session-type event_replay --dry-run
```

## single

The default and the only production-scored path. One agent invocation in one
Docker sandbox; artifacts scored by the in-container `test.sh`. Everything
about it lives in `eb-sandbox-execution` (execution) and
`eb-checkpoint-scoring` (scoring). Nothing more here — one home per fact.

## chain

Multi-session task: N sequential agent sessions over the same workspace, with
a **git branch as the inter-session handoff**. Modules, all under
`scripts/orchestration/`:

| Module              | Role                                                                                         |
| ------------------- | -------------------------------------------------------------------------------------------- |
| `chain_runner.py`   | parses the task, loops sessions, aggregates score, writes `chain_result.json`                |
| `session.py`        | one session lifecycle: setup workspace → run agent/simulate → commit                         |
| `branch_manager.py` | branch naming, checkout, commit; branch = `eb-chain-{task_id}-session-{N}`                   |
| `milestone.py`      | runs between-session verifier scripts, parses `{"score": float, "message": str}` from stdout |

### task.toml anatomy (from the one active chain task)

`benchmarks/customer_escalation/chain-err-flask-import-001/task.toml`:

- `[task]` has `session_type = "chain"` and `session_count = 2`.
  `session_count` is REQUIRED for chain and FORBIDDEN otherwise
  (`lib/eb_verify/schema_validator.py` Rule 2, an iff rule); schema bounds it
  1-10. `chain_runner.parse_chain_task` errors if `session_count` does not
  equal the number of `[[sessions]]` entries.
- One `[[sessions]]` block per session, each with a `prompt` and optional
  `[[sessions.milestones]]` entries (`name` + `verifier`, a script path
  relative to the task dir; path-escape is rejected).
- `[[checkpoints]]` are the FINAL checkpoints, run once after the last
  session, with explicit `weight` values.
- Optional `[simulation.session_N]` blocks with
  `actions = [{repo, file, content}, ...]` drive `--simulate` mode.
- Note: `[[sessions]]` is not declared in `schemas/task.schema.json` (no
  `"sessions"` property; the schema has no `additionalProperties: false`, so
  it passes validation as an extra key).

### Execution flow

1. Session 1: workspace repos are set up, branch
   `eb-chain-<task_id>-session-1` is created.
2. Agent (or simulation) works; ALL repos get `git add -A` +
   `git commit --allow-empty` on the session branch.
3. Milestones for that session run (skipped after the final session).
   A failed session aborts the chain.
4. Session N>1: checks out `...session-(N-1)`, branches `...session-N`, so
   each session inherits the previous session's committed state.
5. After the last session, final checkpoints run and a total score is
   computed.

### Chain scoring (differs from single-task production scoring)

`chain_runner._compute_total_score`: final checkpoints use their DECLARED
`weight` from task.toml; inter-session milestones get a fixed small weight of
0.1 each; total = weighted mean. This is a third weighting scheme, distinct
from both the equal-weighted production single-task path and the
weight-normalized library `CheckpointRunner` (see `eb-checkpoint-scoring` for
that split). Which scheme the project consolidates on is an open decision —
do not "fix" chain weighting to match either sibling without a ruling
(PROVISIONAL pending Stephanie: two-scorer future, discovery Q3).

### Runbook (verified commands)

```bash
# Both invocation forms work (scripts/ resolves as a namespace package):
python3 scripts/orchestration/chain_runner.py --help
python3 -m scripts.orchestration.chain_runner --help

# Simulation run (no agent, uses [simulation.*] actions from task.toml):
python3 scripts/orchestration/chain_runner.py \
  benchmarks/customer_escalation/chain-err-flask-import-001/task.toml --simulate
```

CAUTION: any chain_runner invocation (simulate or not) writes
`chain_result.json` INTO THE TASK DIRECTORY (`<task_dir>/chain_result.json`),
i.e. into the benchmarks tree, and creates a temp workspace under
`/tmp` (`eb-chain-<task_id>-*`) unless `--workspace` is given. Don't commit
the result file. `docs/SESSION_TYPE_VALIDATION.md` (2026-03-29) records a
simulate run scoring 0.87 on this task; not re-run this session.

### Chain maturity — read before trusting a chain "result"

Verified in source, all three also acknowledged in
`docs/SESSION_TYPE_VALIDATION.md` "Known Limitations":

1. **No real agent is wired.** `chain_runner.main()` never passes an
   `agent_callable`, and `run_session` falls back to `simulate_agent_work`
   whenever `agent_callable is None` — so a run WITHOUT `--simulate` still
   does simulated work (it writes a default
   `session_N_output.md` marker instead of the task.toml simulation actions).
   There is no un-simulated chain execution path today.
2. **Session-1 repos are `git init` stubs, not clones.** `session.py:
setup_workspace` creates an empty repo with a README ("Simulated repo for
   <task>"); the comment says production would clone the pinned rev. No Docker
   container is involved anywhere in chain_runner, despite
   `docs/ARCHITECTURE.md`'s "N containers, sequential" row (design intent,
   not implemented).
3. **`--dry-run`, `--source`, `--agent`, `--timeout`, `--account` are parsed
   but ignored** (commented "accepted but not used here" — they exist so
   run_benchmark passthrough doesn't crash argparse). `--mode` IS accepted and
   propagated to each `SessionConfig` (test:
   `tests/test_chain_runner_mode.py`, the only dedicated session-type test
   module in `tests/`).

## event_replay

The agent is on-call: it reads a stream of timestamped events and must emit
actions. File-based contract (no streaming; `event_replay.py` module
docstring calls file-based "the pragmatic v1"):

| File                   | Who writes it | Content                                                                                             |
| ---------------------- | ------------- | --------------------------------------------------------------------------------------------------- |
| `events.jsonl`         | task author   | one Event per line: `timestamp_ms, event_type, category, source, severity, summary[, payload, id]`  |
| `oracle_actions.jsonl` | task author   | ground-truth Actions: `timestamp_ms, action_type, target, description[, triggered_by, payload, id]` |
| `actions.jsonl`        | agent         | same Action schema, timestamps self-reported by the agent                                           |

Schemas and validation live in `scripts/orchestration/event_schema.py`:
categories `cicd|monitoring|collaboration|infrastructure`; severities
`info|warning|critical|fatal`; event timestamps must be monotonically
non-decreasing; unknown `event_type` is a warning (schema is extensible), but
unknown `action_type` is an error. The nine valid action types:
`investigate, escalate, remediate, communicate, deploy, rollback, triage,
monitor, no_op`.

`[task]` must carry `session_type = "event_replay"` and the file MUST have an
`[events]` section (`event_file`, `oracle_actions`) — required iff
event_replay (`lib/eb_verify/schema_validator.py` Rule 3). Paths are relative
to the task dir.

### Scoring: 4 dimensions (`scripts/orchestration/action_scorer.py`)

Defaults from `ScoringConfig` (per-task override is a code-level parameter;
no task.toml knob exists today):

| Dimension    | Default weight | How computed                                                                                                              |
| ------------ | -------------- | ------------------------------------------------------------------------------------------------------------------------- |
| correctness  | 0.35           | fraction of oracle actions matched (greedy first-match, `type_and_target` by default, target compared case-insensitively) |
| completeness | 0.30           | identical value to correctness in the current greedy scheme (kept conceptually separate)                                  |
| timeliness   | 0.25           | full credit ≤ 60 s after the triggering event (via `triggered_by` ids, else oracle timestamp), linear decay to 0 at 300 s |
| ordering     | 0.10           | fraction of matched pairs in oracle order (Kendall-tau style)                                                             |

Unmatched agent actions are counted (`extra_actions`) but NOT penalized in
the total. Missed oracle actions get 0 correctness and 0 timeliness.

### Runbook (verified: these exact commands ran clean this session)

```bash
# Validate an event stream
python3 scripts/orchestration/event_schema.py events \
  benchmarks/incident_response/event-replay-click-ci-001/events.jsonl   # -> "OK"

# Offline-score a pre-collected actions file (NOTE: positional arg is the task DIR)
python3 scripts/orchestration/event_replay.py \
  benchmarks/incident_response/event-replay-click-ci-001 \
  --agent-actions benchmarks/incident_response/event-replay-click-ci-001/sample_agent_actions.jsonl
# -> report; the shipped sample scores 100% on all four dimensions
# Add --json [--pretty] for machine-readable output. Writes nothing to disk.

# Raw scorer, bypassing task.toml:
python3 scripts/orchestration/action_scorer.py <events.jsonl> <oracle.jsonl> <agent.jsonl> [--pretty]
```

Without `--agent-actions`, `event_replay.py` only prints task info and
"sandbox integration not yet implemented" — there is NO path today that
launches an agent, copies `events.jsonl` into a container, or collects
`actions.jsonl`. Offline scoring is the only functional mode.

The active task also declares four `[[checkpoints]]` with `checks/*.sh`
verifiers, but `event_replay.py` never executes checkpoints (no reference in
the file), and `run_task.py` refuses non-single tasks — so those checkpoint
scripts are currently dead weight for this session type (reviewer note: no
other executor of them was found, but this was not exhaustively proven).

## resume

Design (from `docs/internal/PRD.md:169` and `schemas/task.schema.json`
`resume_state`): the agent inherits a pre-generated branch containing partial
progress — good commits, wrong turns — plus a `progress_doc` left by the
"previous developer", and must assess and finish the work. `resume_state`
needs `branch` and `progress_doc`; the section is required iff
`session_type = "resume"` (schema_validator Rule 4 — a `single` task carrying
`resume_state` fails validation).

Reality: zero resume tasks exist anywhere in `benchmarks/`, no runner exists,
and `run_benchmark.py` deliberately skips them ("not yet implemented"). The
skip is an ACCEPTED no-op — do not report it as a bug, and do not delete the
`resume` enum value or the skip branch: schema, dispatcher, and
`lib/eb_verify/schema_validator.py` tests (`tests/test_schema_validator.py`)
all encode it as a reserved, validated-but-unrunnable type.

## Verified bugs and traps (2026-07-07, all confirmed against HEAD `7cfb8b0`)

These are open findings, not documented anywhere else in the repo except as
noted. Fixing any of them is a change to scoring-adjacent machinery: ship
tests with the fix and treat it as needing Stephanie's sign-off (PROVISIONAL
pending Stephanie: conservative HALT gating for scoring-path-adjacent
changes, discovery Q5).

1. **run_benchmark → event_replay dispatch is broken twice over.**
   `run_benchmark.py` invokes every runner with the `task.toml` PATH plus a
   `--mode <mode>` flag (`collect_passthrough_args` always appends `--mode`).
   But `event_replay.py` (a) has no `--mode` argument — verified:
   `python3 scripts/orchestration/event_replay.py <task.toml> --mode baseline`
   exits with `error: unrecognized arguments: --mode baseline` — and (b)
   expects a task DIRECTORY positional, so even with `--mode` fixed,
   `load_task_config` would look for `<task.toml>/task.toml` and raise
   FileNotFoundError. Consequence: a real (non-dry-run) dispatch of an
   event_replay task through run_benchmark records status `error`; only
   direct invocation with the task dir works. (`docs/
internal/prd_task_mix_realignment.md:89` records the same class of bug for
   chain_runner's missing `--mode`, which HAS since been fixed — the
   event_replay side was not.)
2. **Multi-mode chain dispatch fails on `--output-dir`.** With `--modes` (or
   len(modes)>1), run_benchmark appends `--output-dir <path>` for each task;
   `chain_runner.py` and `event_replay.py` accept no such flag → argparse
   exit 2. Only `run_task.py` (single) accepts `--output-dir`.
3. **Chain results bypass the results tree.** `chain_runner` writes
   `chain_result.json` into the task's benchmark directory, not
   `results/runs/<task_id>/...`; run_benchmark's score-reading loop does check
   `task_dir/results.json` as a fallback but chain writes a different
   filename, so a chain TaskResult's `score` stays `None` even on success.
4. **A "real" chain run silently simulates** (see Chain maturity #1). Any
   chain score produced today measures the simulation harness, not an agent.
   Never publish chain numbers as agent results — that would be a
   silent-misscore of the exact class `eb-scoring-integrity-doctrine` exists
   to prevent.

## Validation gates relevant to this axis

```bash
make verify-tasks   # scripts/validate_tasks_preflight.py — JSON-schema pass over every task
make verify         # verify-mix + verify-tasks + verify-crnt
```

The session-type iff rules (session_count↔chain, events↔event_replay,
resume_state↔resume) live in `lib/eb_verify/schema_validator.py`
(`_validate_semantic_layer`) with tests in `tests/test_schema_validator.py`.
`scripts/validation/task_mix_validator.py` and `crnt_validator.py` contain no
`session_type` handling — the mix and CRNT gates are session-type-agnostic.

## Provenance and maintenance

Authored 2026-07-07 against commit `7cfb8b0` (retiring-fellow campaign;
positions marked PROVISIONAL follow the recorded provisional answers to
discovery questions Q3 and Q5 and are revisable by Stephanie). Facts most
likely to drift, with one-line re-verification commands (run from repo root):

```bash
# Runner map + resume skip still as documented
grep -n "RUNNERS\|not yet implemented" scripts/run_benchmark.py | head

# Session-type census (active vs archived)
grep -rl 'session_type = "chain"\|session_type = "event_replay"\|session_type = "resume"' benchmarks/ --include=task.toml

# run_task still rejects non-single
grep -n "only handles single-session" scripts/orchestration/run_task.py

# event_replay still lacks --mode / still takes a dir (bug #1 fixed when this changes)
python3 scripts/orchestration/event_replay.py --help | grep -c "mode"   # 0 = still broken

# chain_runner still never passes a real agent (bug #4 fixed when this changes)
grep -n "agent_callable" scripts/orchestration/chain_runner.py

# Chain weighting scheme (final weights + 0.1 milestone weight)
grep -n "w = 0.1" scripts/orchestration/chain_runner.py

# Scorer defaults
grep -n "weight_correctness\|timeliness_full_credit_ms" scripts/orchestration/action_scorer.py

# iff rules still enforced
grep -n "Rule [234]" lib/eb_verify/schema_validator.py

# Offline scoring still green
python3 scripts/orchestration/event_replay.py benchmarks/incident_response/event-replay-click-ci-001 \
  --agent-actions benchmarks/incident_response/event-replay-click-ci-001/sample_agent_actions.jsonl --json | head -c 200
```
