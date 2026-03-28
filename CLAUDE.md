# EnterpriseBench

Evolution of CodeScaleBench (CSB, 275 tasks, unpublished) into a benchmark measuring **codebase understanding and context gathering** — how well agents find and comprehend the right code across large, distributed codebases. Sourcegraph MCP is a first-class showcase, but tool access is a controlled independent variable (baseline / MCP-only / hybrid).

## Project Status
Post-prototyping. Convergence report finalized from 6 prototypes and 2 structured debates. Entering Phase 1 implementation.

## Key Files
- `PRD.md` — product requirements document
- `docs/CONVERGENCE_REPORT.md` — converged architecture from debate synthesis (detailed design decisions)
- `docs/ARCHITECTURE.md` — system architecture and verification flow
- `schemas/task.schema.json` — task definition schema (includes tool_access, ground_truth, difficulty_stratum)
- `lib/eb_verify/` — centralized verification library (to be built)
- `benchmarks/` — task definitions organized by suite
- `scripts/` — task mining, sandbox management, orchestration
- `configs/` — run configurations

## CSB Foundation
- 275 existing tasks (220 Org + 55 SDLC) carry forward — fix, extend, don't rebuild
- 178 sg-evals mirrors from CSB, extended for multi-repo tasks
- Primary measurement: context retrieval quality (not code generation)
- Current curator F1=0.70 is insufficient — layered ground truth replaces single-source

## Task Suites
Tasks are organized by enterprise workflow cluster (not artificial SDLC/Org splits):
- `dependency_management` — upgrading, patching, propagating across dependency chains
- `incident_response` — alert triage, root cause across services, remediation, postmortem
- `platform_engineering` — CI/CD, IaC, deployment orchestration
- `security_operations` — vulnerability assessment, policy enforcement, forensics
- `customer_escalation` — issue reproduction, cross-service diagnosis, KB creation
- `feature_delivery` — PRD-to-implementation across repos, API design + consumer updates
- `technical_debt` — large-scale refactoring, migration, deprecation propagation

## Task Mix Gradient
- 15% calibration (single-repo, MCP bias check)
- 25% large single-repo
- 30% dual-repo
- 20% 3-5 repo
- 10% monorepo cross-package

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
- Single `eb_verify` library — no per-task verifier copies, ever
- Checkpoint-based partial scoring (2-5 checkpoints per task)
- Artifact-type-aware validation (code patches, configs, reports, scripts, etc.)
- Layered ground truth: deterministic + LLM curator + solve-verification

## Skills
- `/diverge` — multi-perspective research with independent agents
- `/diverge-prototype` — independent prototyping in isolated worktrees
- `/converge` — structured debate using Agent Teams

## Conventions
- All work on `main`
- Run prototypes before committing to architectural decisions
- Real OSS repos only — no synthetic/toy repositories
- Every task must be a realistic enterprise use case
