# EnterpriseBench

Benchmark for evaluating coding agents on realistic enterprise development workflows: multi-repo, multi-session, role-fluid tasks using real OSS dependency chains.

## Project Status
Early-stage. PRD is finalized. Prototyping phase is next.

## Key Files
- `PRD.md` — product requirements document (source of truth for what we're building)
- `schemas/task.schema.json` — task definition schema
- `lib/eb_verify/` — centralized verification library (to be built)
- `benchmarks/` — task definitions organized by suite
- `scripts/` — task mining, sandbox management, orchestration
- `configs/` — run configurations
- `docs/` — design docs, technical reports

## Task Suites
Tasks are organized by enterprise workflow cluster (not artificial SDLC/Org splits):
- `dependency_management` — upgrading, patching, propagating across dependency chains
- `incident_response` — alert triage, root cause across services, remediation, postmortem
- `platform_engineering` — CI/CD, IaC, deployment orchestration
- `security_operations` — vulnerability assessment, policy enforcement, forensics
- `customer_escalation` — issue reproduction, cross-service diagnosis, KB creation
- `feature_delivery` — PRD-to-implementation across repos, API design + consumer updates
- `technical_debt` — large-scale refactoring, migration, deprecation propagation

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

## Skills
- `/diverge` — multi-perspective research with independent agents
- `/diverge-prototype` — independent prototyping in isolated worktrees
- `/converge` — structured debate using Agent Teams

## Conventions
- All work on `main`
- Run prototypes before committing to architectural decisions
- Real OSS repos only — no synthetic/toy repositories
- Every task must be a realistic enterprise use case
