# EnterpriseBench

Evolution of CodeScaleBench (CSB, 275 tasks, unpublished) into a benchmark measuring **codebase understanding and context gathering** — how well agents find and comprehend the right code across large, distributed codebases. Sourcegraph MCP is a first-class showcase, but tool access is a controlled independent variable (baseline / MCP-only / hybrid).

## Project Status

Phase 6: Task mix realignment complete. 112 active benchmark tasks across 10 task types (28 archived), 50.9% strict multi-repo coverage, all types with 2+ multi-repo variants. 779+ tests passing, full verification pipeline operational.

## Key Files

- `docs/internal/PRD.md` — product requirements document
- `docs/CONVERGENCE_REPORT.md` — converged architecture from debate synthesis (detailed design decisions)
- `docs/ARCHITECTURE.md` — system architecture and verification flow
- `docs/TASK_TYPE_PRD.md` — 10 task type definitions with MCP signal ratings
- `docs/TASK_AUTHORING_GUIDE.md` — step-by-step guide for adding new tasks
- `schemas/task.schema.json` — task definition schema (includes tool_access, ground_truth, difficulty_stratum)
- `lib/eb_verify/` — centralized verification library with plugin architecture
- `lib/eb_verify/plugins/` — 9 artifact validators (answer, code_patch, config_validator, incident_report, runbook, security_assessment, reproduction_script, topological_order, call_graph)
- `benchmarks/` — 112 active task definitions organized by suite
- `benchmarks/_archived/` — 28 retired single-repo tasks (preserved for reference)
- `benchmarks/mined/` — mining candidate lists and provenance data
- `results/sample_runs/` — sample verification outputs by task type
- `scripts/` — task mining, sandbox management, orchestration
- `scripts/sandbox/templates/` — Dockerfile templates (Go, Java, Python multi-repo)
- `configs/` — run configurations
- `configs/repo_versions.json` — pinned SHA manifest for all task repos (staleness detection via `scripts/infra/check_repo_staleness.py`)
- `scripts/validation/task_mix_validator.py` — validates PRD task mix targets
- `scripts/validation/crnt_validator.py` — Cross-Repo Necessity Test for multi-repo tasks

## CSB Foundation

- 275 existing tasks (220 Org + 55 SDLC) carry forward — fix, extend, don't rebuild
- 178 sg-evals mirrors from CSB, extended for multi-repo tasks
- Primary measurement: context retrieval quality (not code generation)
- Layered ground truth (deterministic + LLM curator + solve-verification) replaces single-source

## Task Suites (112 active tasks)

Tasks are organized by enterprise workflow cluster (not artificial SDLC/Org splits):

- `dependency_management` (27) — dep_traversal, api_contract tasks
- `incident_response` (12) — incident_investigation tasks
- `platform_engineering` (10) — config_drift tasks
- `security_operations` (2) — vulnerability assessment, access control audit tasks
- `customer_escalation` (24) — error_provenance, support_code_mapping tasks
- `feature_delivery` (18) — monorepo_boundary, db_schema_evolution tasks
- `technical_debt` (19) — refactor_orchestration, dead_code_necropsy tasks

## Task Types (10)

api_contract, config_drift, db_schema_evolution, dead_code_necropsy, dependency_graph, error_provenance, incident_investigation, monorepo_boundary, refactor_orchestration, support_code_mapping

## Task Mix (actual)

- 12.5% calibration (14 tasks)
- 25.9% large single-repo (29 tasks)
- 25.0% dual-repo (28 tasks)
- 14.3% tri-repo (16 tasks)
- 11.6% multi-repo (13 tasks)
- 10.7% monorepo cross-package (12 tasks)
- Strict multi-repo (dual+tri+multi): 50.9%
- Validate with: `python scripts/validation/task_mix_validator.py`

## Multi-Repo Design

- Tasks use 1-5 real OSS repos connected by actual dependency chains
- Four atomic patterns: propagate, investigate, enforce, orchestrate
- Repos cloned into `/workspace/{repo-name}/` in sandbox
- Cross-repo integration tests via unified `test.sh`

## Session Types

- `single` — standard one-shot task
- `chain` — multi-session with git-branch state between sessions
- `event_replay` — agent responds to timestamped event stream
- `resume` — agent picks up partially completed work

## Verification

- Single `eb_verify` library with plugin architecture — no per-task verifier copies, ever
- 9 verifier plugins: answer, code_patch, config_validator, incident_report, runbook, security_assessment, reproduction_script, topological_order, call_graph
- Checkpoint-based partial scoring (2-5 checkpoints per task)
- Artifact-type-aware validation (code patches, configs, reports, scripts, etc.)
- Layered ground truth: deterministic + LLM curator + solve-verification
- 779+ tests across 19 test modules

## Skills

- `/diverge` — multi-perspective research with independent agents
- `/diverge-prototype` — independent prototyping in isolated worktrees
- `/converge` — structured debate using Agent Teams

## Conventions

- All work on `main`
- Run prototypes before committing to architectural decisions
- **Always run benchmark tasks in parallel** — never sequentially. Use `&` + `wait` with different accounts (1-5). Mode-suffixed image tags (`eb-task-mcp_only`) prevent Docker build collisions. CSB uses `PairScheduler` for this; EB's `run_task.py` is single-task, so the caller must parallelize.
- Real OSS repos only — no synthetic/toy repositories
- Every task must be a realistic enterprise use case
