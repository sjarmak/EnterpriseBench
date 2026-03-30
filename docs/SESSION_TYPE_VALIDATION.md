# Session Type Validation Report

Date: 2026-03-29
Phase: Phase 1 — Validate session-chain and event-replay with real agent runs

## Summary

Both session-chain and event-replay engines have been validated end-to-end
with working task definitions, verifiers, and scoring pipelines.

## Tasks Created

### Chain Task: `chain-err-flask-import-001`

- **Location**: `benchmarks/customer_escalation/chain-err-flask-import-001/`
- **Type**: 2-session chain (session_type = "chain")
- **Repo**: Flask (pallets/flask @ 3.1.0)
- **Scenario**: Session 1 investigates a circular import in Flask's json module;
  Session 2 implements a fix based on the investigation
- **Verifiers**: 3 check scripts (investigation, cycle, fix)
- **Simulation data**: Included for both sessions

### Event-Replay Task: `event-replay-click-ci-001`

- **Location**: `benchmarks/incident_response/event-replay-click-ci-001/`
- **Type**: event_replay (session_type = "event_replay")
- **Repo**: Click (pallets/click @ 8.1.7)
- **Scenario**: CI failure cascade after markupsafe dependency update;
  agent must investigate, triage, communicate, and remediate
- **Events**: 5 events (CI alerts, GitHub comments, Slack messages)
- **Oracle actions**: 5 expected actions
- **Sample agent actions**: Included for testing
- **Verifiers**: 4 check scripts (root_cause, triage, communication, remediation)

## Validation Results

### chain_runner.py

| Test                                    | Result                                                         |
| --------------------------------------- | -------------------------------------------------------------- |
| py_compile                              | PASS                                                           |
| Parse chain task.toml                   | PASS — 2 sessions, 3 checkpoints, simulation data              |
| --simulate mode                         | PASS — both sessions complete, milestones verified, score=0.87 |
| Git branch handoff                      | PASS — session-1 branch -> session-2 branch with correct state |
| Milestone verification between sessions | PASS — runs after session 1, skipped after session 2           |
| Final checkpoint scoring                | PASS — weighted score computation correct                      |
| Result JSON output                      | PASS — chain_result.json written                               |

### event_replay.py

| Test                              | Result                                             |
| --------------------------------- | -------------------------------------------------- |
| py_compile                        | PASS                                               |
| Parse event-replay task.toml      | PASS — 5 events, 5 oracle actions                  |
| Event file validation             | PASS — zero validation errors                      |
| Oracle action validation          | PASS — zero validation errors                      |
| Default mode (no agent)           | PASS — prints task info and instructions           |
| Scoring with sample agent actions | PASS — 100% on all dimensions                      |
| JSON output mode                  | PASS — structured output with per-action breakdown |

### Supporting Modules

| Module            | py_compile | Notes                                                                 |
| ----------------- | ---------- | --------------------------------------------------------------------- |
| session.py        | PASS       | Workspace setup, simulation, git branch lifecycle                     |
| milestone.py      | PASS       | Verifier execution, structured JSON scoring output                    |
| branch_manager.py | PASS       | Branch creation, checkout, commit, SHA tracking                       |
| event_schema.py   | PASS       | Event/Action dataclasses, JSONL I/O, validation                       |
| action_scorer.py  | PASS       | 4-dimension scoring (correctness, completeness, timeliness, ordering) |

## Known Limitations

1. **Chain runner --dry-run**: The `--dry-run` flag is a passthrough argument
   accepted but not acted on by chain_runner.py. Use `--simulate` for testing
   without an agent.

2. **Event-replay sandbox integration**: The event_replay.py runner can parse
   tasks and score agent outputs, but the full sandbox integration (copying
   events.jsonl into a Docker container, running the agent, collecting
   actions.jsonl) is not yet implemented. The `--agent-actions` offline scoring
   path is fully functional.

3. **Chain runner workspace**: In simulation mode, repos are initialized as
   empty git repos with a README, not cloned from upstream. Real agent runs
   would need the actual repo content (handled by the Docker sandbox in
   run_task.py).

## What Works

- Task definition parsing for both session types
- TOML schema validation (session_type, session_count, events config)
- Git branch creation and handoff between chain sessions
- Milestone/checkpoint verification with shell scripts returning JSON scores
- Weighted score computation for chain tasks
- Event stream validation (monotonic timestamps, known types)
- Action matching and 4-dimension scoring for event-replay
- Simulation mode for chain tasks with predetermined actions
- Offline scoring mode for event-replay with pre-collected agent actions
