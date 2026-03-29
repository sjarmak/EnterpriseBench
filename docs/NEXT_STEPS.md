# EnterpriseBench: Next Steps (Phase 1)

**Date**: 2026-03-28
**Status**: Prototyping complete, entering Phase 1 implementation
**Last commit**: `39dfc4e` — all 6 prototypes merged with security hardening, 172 tests passing

## What's Done

### Infrastructure (all merged, tested, committed)
- **eb_verify** (`lib/eb_verify/`) — verification library with plugin architecture, checkpoint runner, CLI, 7 artifact type validators, schema validator. Security-hardened (path traversal guards, symlink-safe reads, score clamping).
- **Sandbox builder** (`scripts/sandbox/`) — Dockerfile generator from task.toml, health checks, cross-repo test runner. Measured: 2-repo workspaces 11-33MB, images <1GB.
- **Session-chain orchestrator** (`scripts/orchestration/chain_runner.py`) — git-branch handoff between sessions, milestone verification, simulation mode.
- **Event-replay engine** (`scripts/orchestration/event_replay.py`) — events.jsonl schema, 4-dimension action scorer (correctness/completeness/timeliness/ordering).
- **Task mining pipeline** (`scripts/mining/`) — discovery, extraction, validation scripts. 3 real tasks mined from OSS breaking changes.
- **MCP mirror integration** (`scripts/infra/`) — sg-evals mirror creation, 3 Dockerfile modes (standard/sg_only/hybrid), MCP instruction generator.
- **Schema** (`schemas/task.schema.json`) — complete with tool_access, ground_truth, csb_lineage, difficulty_stratum, checkpoint timeout_seconds.
- **10+ real tasks** across 5 suites with instruction.md + instruction_mcp.md + task.toml.

### Architecture Decisions (from convergence debate)
- **Verification-first sequencing** — harden eb_verify before trusting scores
- **Schema includes MCP from day one** — tool_access field on every task
- **Session-chain in v1, event-replay in v1.1** — P3 simpler and has clear verification story
- **Selective MCP dual-mode** — only on Investigate/Propagate tasks (~40%), not full matrix
- **Publish target: ~30 tasks at week 8-9** — 20-25 single + 3-5 chain

## Phase 1: Foundation (Weeks 1-3)

### 1. Harden eb_verify Validators (Priority: HIGH)

The current validators do structure checks, not semantic correctness. Key gaps:

**`answer` validator** — needs oracle matching:
- Keyword matching against ground_truth.required_files
- Symbol matching (function names, class names)
- File path matching (did agent find the right files?)
- Configurable match thresholds per task

**`code_patch` validator** — needs real patch verification:
- `git apply --check` to verify patch applies cleanly
- Optional test execution (run checkpoint's test command)
- Diff size reasonableness check

**`config` validator** — needs HCL support:
- Currently handles JSON/YAML/TOML
- Add HCL parsing for Terraform tasks
- Add actionlint for GitHub Actions YAML
- Add kubeval for Kubernetes manifests

**`incident_report` validator** — needs semantic checks:
- Required sections completeness (timeline, root_cause, remediation)
- Cross-reference validation (mentioned services exist in task repos)
- Timeline ordering check

**Test gaps to fill**:
- `verifier_output.schema.json` requires `passed` but runner derives it from score — reconcile
- `kb_article` and `migration_guide` in schema enum but no validators — implement or remove
- Add real timeout test (not mocked) for checkpoint runner

**Files**: `lib/eb_verify/plugins/*.py`, `lib/eb_verify/runner.py`, `tests/test_plugins.py`

### 2. Mine 15-20 More Tasks (Priority: HIGH, parallel with #1)

Current: 13 tasks (10 migrated from CSB + 3 mined from OSS). Target: 30 for v1.

**Focus suites** (per PRD task distribution):
- dependency_management: need 10-15 more (strongest mining pipeline)
- incident_response: need 8-10 more
- security_operations: need 3-5 more

**Mining process** (scripts are ready):
1. `python3 scripts/mining/mine_breaking_changes.py` — find candidates
2. `python3 scripts/mining/extract_task.py` — generate task.toml
3. `python3 scripts/mining/validate_candidate.py` — check viability
4. Manually write instruction.md and instruction_mcp.md per task
5. Annotate `tool_access.expected_mcp_benefit` on each task

**Target dependency chains** (from MINING_LOG.md):
- Go: grpc-go→etcd, kubernetes client-go changes
- Python: urllib3→requests→boto3, Django breaking changes
- TypeScript: eslint→typescript-eslint, webpack→next.js
- Java: protobuf-java→grpc-java (cross-language)

**Each mined task needs**: task.toml, instruction.md, instruction_mcp.md, checkpoint verifier scripts (checks/*.sh), ground_truth section populated.

**Effort**: ~1.5-2 hours per viable task at 60% candidate-to-task conversion.

### 3. Finalize Sandbox for Real Runs (Priority: MEDIUM)

The sandbox builder generates Dockerfiles but hasn't been tested end-to-end with a real agent run.

- Wire sandbox_builder.py to actually build and run a container
- Integrate eb_verify installation into the sandbox Dockerfile
- Test: build sandbox for EXAMPLE_TASK.toml, run a mock agent, score with eb_verify
- Validate the 3 Dockerfile modes (standard/sg_only/hybrid) all build correctly
- Set up sg-evals mirrors for the first 5 tasks on demo.sourcegraph.com

**Files**: `scripts/sandbox/sandbox_builder.py`, `scripts/sandbox/dockerfile_generator.py`

## Phase 2: Core Benchmark (Weeks 4-7)

### 4. Session-Chain Integration
- Build 3-5 chain tasks (2-session: investigate → implement)
- Test real git-branch handoff (not just simulation mode)
- Wire milestone verification between sessions
- Validate scoring: milestones + final checkpoints

### 5. MCP Dual-Mode First Runs
- Create sg-evals mirrors for 5-8 Investigate/Propagate pattern tasks
- Run same tasks in standard and sg_only modes
- Measure: score delta, tool call count, token cost
- Record tool_usage metadata in result artifacts

### 6. Scale to 30 Tasks
- Continue mining to reach 25 single-session + 5 chain tasks
- Ensure coverage across all 7 suites
- Difficulty distribution: ~30% medium, ~50% hard, ~20% expert
- Task mix gradient: 15% calibration, 25% large_single, 30% dual_repo, 20% multi_repo

## Phase 3: Publish (Week 8-9)

### 7. Benchmark Validation
- Run full benchmark with Claude Code + OpenHands
- Verify reproducibility: same task, same agent, 3 runs → score variance < 0.15
- Check signal quality: checkpoint scores have meaningful spread
- MCP benefit analysis on the Investigate/Propagate subset

### 8. Paper & Release
- Write paper: "EnterpriseBench: Multi-Repo, Multi-Session Benchmark with Tool-Access Measurement"
- Package benchmark for external use
- Release task definitions + verification library

## Key Files Reference

| Component | Path |
|---|---|
| PRD | `PRD.md` |
| Architecture | `docs/ARCHITECTURE.md` |
| Convergence report | `docs/CONVERGENCE_REPORT.md` |
| Task schema | `schemas/task.schema.json` |
| Verifier output schema | `schemas/verifier_output.schema.json` |
| eb_verify library | `lib/eb_verify/` |
| Sandbox scripts | `scripts/sandbox/` |
| Mining pipeline | `scripts/mining/` |
| Session orchestration | `scripts/orchestration/` |
| MCP infrastructure | `scripts/infra/` |
| CSB migration | `scripts/migrate_csb_task.py` |
| Example tasks | `benchmarks/EXAMPLE_TASK.toml`, `benchmarks/EXAMPLE_CHAIN_TASK.toml` |
| Real tasks | `benchmarks/{suite}/{task-id}/` |
| Mined tasks | `benchmarks/mined/` |
| Test suite | `tests/` (172 tests passing) |

## Sourcegraph MCP Setup

- Instance: `demo.sourcegraph.com`
- Mirror org: `sg-evals` on GitHub
- Mirror naming: `sg-evals/{repo-name}--{rev}`
- MCP endpoint: `https://demo.sourcegraph.com/.api/mcp`
- Config: `claude mcp add --transport http sg https://demo.sourcegraph.com/.api/mcp`
- Auth: `SOURCEGRAPH_ACCESS_TOKEN` env var

## CodeScaleBench Reference

The sibling project at `~/CodeScaleBench` contains:
- 275 existing tasks (220 Org + 55 SDLC)
- 178 sg-evals mirrors already created
- Working MCP agent implementations in `agents/mcp_agents.py`
- Harness infrastructure in `agents/harnesses/base.py`
- Mirror creation scripts in `scripts/infra/`
- Task-to-mirror mappings in `configs/runs/`
