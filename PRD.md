# PRD: EnterpriseBench

## Problem Statement

No existing benchmark evaluates coding agents the way enterprise developers actually work. SWE-bench tests single-file patches in single repos. ITBench tests SRE incident response in isolation. DevOps-Gym tests build/config tasks. None combine these into a cohesive evaluation that reflects reality: developers work across multiple interconnected repositories with real dependency chains, wear multiple hats across the SDLC, produce diverse artifacts (not just code patches), operate over multi-session horizons, and increasingly rely on agentic workflows (background agents, triggers, multi-session orchestration).

EnterpriseBench is a new, standalone benchmark (repo: `~/EnterpriseBench`) that learns from CodeScaleBench's successes — real OSS codebases, dual verification, MCP-benefit scoring, complexity metadata — without inheriting its limitations (duplicated verifiers, artificial SDLC/Org splits, uniform `answer.json` output, single-session-only architecture, "cross-repo" tasks that aren't actually cross-repo).

Every task in EnterpriseBench represents a realistic enterprise development use case. There are no arbitrary category boundaries — tasks are organized by suites that reflect natural workflow clusters, but any task may involve investigation, code changes, infrastructure modifications, documentation, and cross-repo coordination simultaneously, just as real work does.

## Goals & Non-Goals

### Goals
- A cohesive benchmark where every task is a realistic enterprise use case spanning one or more real OSS repositories with genuine dependency relationships
- Multi-repo as the default, not the exception — tasks use 1-5 real OSS repos connected by actual dependency chains (libraries, APIs, shared schemas)
- Role-fluid tasks that naturally blend SWE, SRE, DevOps, security, and support engineering work — no artificial role silos
- Diverse artifact outputs per task (code patches, CI configs, runbooks, incident reports, KB articles) with type-appropriate verification
- Multi-session task support via git-branch state, milestone checkpoints, and partial-credit scoring
- Event-replay infrastructure for background/trigger agent evaluation without live infrastructure
- "Resume from mess" tasks that test mid-project comprehension at single-session cost
- A single, centralized verification library from day one — no per-task verifier copies
- Graduated difficulty with checkpoint-based partial credit that produces signal even at high difficulty
- Repo metadata (LoC, complexity, dependency depth, framework/language) baked into task definitions for stratification and analysis

### Non-Goals
- Replacing CodeScaleBench (CSB continues as the single-repo, single-session benchmark)
- Building live infrastructure (K8s clusters, monitoring stacks) — use event-replay and simulated environments
- Multi-agent coordination benchmarks in v1 (defer until single-agent multi-session is validated)
- Supporting every agent framework — design for Claude Code and OpenHands initially, with an agent-agnostic task contract
- Exhaustive role coverage — prioritize the roles where multi-repo, multi-artifact work is most natural
- Synthetic or toy repositories — all tasks use real OSS codebases

## Task Philosophy

### No Artificial Splits
CSB's SDLC/Org distinction created tasks that tested one dimension in isolation. Real enterprise work doesn't decompose that way. An SRE responding to an incident must: investigate logs (understand), trace across services (cross-repo), write a fix (implement), update the runbook (document), and patch the CI pipeline to prevent recurrence (DevOps). EnterpriseBench tasks should capture this full arc, not slice it into separate "understand" and "fix" tasks.

### Suites as Workflow Clusters
Tasks are organized into suites that represent natural enterprise workflow clusters:

- **Dependency Management** — upgrading, patching, and propagating changes across dependency chains
- **Incident Response** — alert triage, root cause analysis across services, remediation, postmortem
- **Platform Engineering** — CI/CD pipelines, infrastructure-as-code, deployment orchestration
- **Security Operations** — vulnerability assessment across dependency trees, policy enforcement, forensics
- **Customer Escalation** — issue reproduction, cross-service diagnosis, knowledge base creation
- **Feature Delivery** — PRD-to-implementation across repos, API design and consumer updates
- **Technical Debt** — large-scale refactoring, migration, deprecation propagation

Each suite contains tasks at multiple difficulty levels. A task may belong to one primary suite but naturally touch concerns from others.

### Multi-Repo Through Real OSS Dependency Chains
Rather than artificially combining unrelated repos, tasks use real open-source dependency chains:
- Go: `grpc-go` → `etcd` → `kubernetes` (API client chain)
- Python: `requests` → `boto3` → `awscli` (HTTP library chain)
- Java: `protobuf-java` → `grpc-java` → `envoy-control-plane` (serialization chain)
- TypeScript: `typescript` → `eslint` → `next.js` (toolchain chain)
- Cross-language: `protobuf` schema → Go server → Python client → TypeScript frontend

Tasks are sourced from real historical breaking changes in these chains, where the "before" state is the task input and the historical fix is ground truth.

### The Four Atomic Multi-Repo Patterns
Every multi-repo task is a composition of these patterns:
1. **Propagate** — change in repo A requires coordinated changes in repos B, C
2. **Investigate** — symptom in repo A, root cause in repo B
3. **Enforce** — consistent policy/patch across N repos
4. **Orchestrate** — coordinated build/deploy/test across repos in dependency order

## Requirements

### Must-Have

**M1. Centralized verification library (`eb_verify`)**
Single Python package installed in all task containers. Supports:
- Oracle matching (files, symbols, keywords — evolved from CSB's approach)
- Artifact validity (YAML/JSON/HCL syntax, linting via actionlint/kubeval/opa, script executability)
- Structural completeness rubrics (e.g., postmortem must contain: timeline, root cause, remediation)
- Patch applicability (`git apply --check`)
- Checkpoint-based partial scoring (per-milestone scores that compose into a total)
No per-task verifier copies. Ever.

**M2. Multi-repo sandbox infrastructure**
- `task.toml` supports `repos = [{url = "...", rev = "...", path = "repo-a"}]` array
- Dockerfile template clones all repos into `/workspace/{path}/`
- Sandbox health check: hard failure on clone failure (no silent fallback), marker file validation
- Cross-repo test runner: `test.sh` can `cd` between repos, run integration tests spanning repos
- Disk budget: validated for 2-3 repo tasks within Daytona sandbox limits (open question — prototype must answer this)

**M3. Task definition schema**
```toml
[task]
id = "dep-mgmt-grpc-proto-bump-001"
suite = "dependency_management"
difficulty = "hard"  # medium | hard | expert
estimated_duration_minutes = 45
session_type = "single"  # single | chain | event_replay | resume

[[repos]]
url = "github.com/grpc/grpc-go"
rev = "v1.59.0"
path = "grpc-go"

[[repos]]
url = "github.com/etcd-io/etcd"
rev = "v3.5.10"
path = "etcd"

[metadata]
languages = ["go"]
total_loc = 1_200_000
max_complexity = 42
dependency_depth = 2
frameworks = ["grpc", "protobuf"]

[[checkpoints]]
name = "identify_breaking_change"
weight = 0.25
verifier = "check_identification.sh"

[[checkpoints]]
name = "fix_grpc_go"
weight = 0.35
verifier = "check_grpc_fix.sh"

[[checkpoints]]
name = "fix_etcd_consumer"
weight = 0.40
verifier = "check_etcd_fix.sh"

[artifacts]
required = ["code_patch"]
optional = ["migration_guide.md"]
```

**M4. Diverse artifact output contracts**
Tasks specify which artifact types they require. The verification library validates each type appropriately:
- `code_patch` — diff applies cleanly, tests pass
- `config` — syntax valid, linter passes (type-specific: GHA, K8s, Terraform, etc.)
- `incident_report` — structured JSON with required fields (timeline, root cause, remediation, affected_services)
- `runbook` — markdown with required sections, referenced file paths exist
- `reproduction_script` — executable, produces expected error
- `kb_article` — covers required topics, code references are valid
- `security_assessment` — CVE mapping complete, prioritization reasonable
- `answer` — traditional oracle-matched response (for investigation-only tasks)

**M5. Initial task set: 80-100 tasks across all suites**
Distribution guided by enterprise workflow frequency, not equal splits:
- Dependency Management: 15-20 tasks
- Incident Response: 15-20 tasks
- Platform Engineering: 10-15 tasks
- Security Operations: 10-15 tasks
- Customer Escalation: 8-12 tasks
- Feature Delivery: 10-15 tasks
- Technical Debt: 8-12 tasks

Difficulty distribution: ~30% medium, ~50% hard, ~20% expert.

**M6. Graduated checkpoint scoring**
Every task has 2-5 checkpoints with weights summing to 1.0. Checkpoints are ordered by difficulty. Partial credit is the default — binary pass/fail is a special case (single checkpoint with weight 1.0).

### Should-Have

**S1. Session-chain tasks**
`session_type = "chain"` with `session_count` and per-session instructions. Git branch as inter-session state. Each session runs in a fresh container, receives previous session's committed branch. Milestone verifier runs between sessions. 10-15 tasks.

**S2. Event-replay tasks**
`session_type = "event_replay"` with `events.jsonl` containing timestamped simulated events (CI failures, error rate spikes, PR comments, deployment notifications). Agent reads event stream, writes `actions.jsonl`. Verifier scores against oracle actions. 5-10 tasks.

**S3. "Resume from mess" tasks**
`session_type = "resume"` with pre-generated intermediate state: a partially completed feature branch with good commits, wrong turns, and a progress document. Agent must assess what's done, what's wrong, what's missing, and complete the task. 10-15 tasks.

**S4. Historical breaking-change mining pipeline**
Semi-automated pipeline to discover verifiable multi-repo tasks from real OSS history:
1. Identify dependency pairs with known breaking changes (from changelogs, release notes, GitHub issues)
2. Pin "before" state of downstream repo
3. Verify that the historical fix commit is a valid ground truth
4. Generate task.toml + checkpoints + verifier

**S5. Repo metadata integration**
Every task carries machine-readable metadata (LoC, cyclomatic complexity, dependency depth, languages, frameworks). This enables:
- Stratified analysis (do agents perform differently on 100K LoC repos vs 1M?)
- Complexity-aware difficulty calibration
- Fair comparison across heterogeneous tasks

### Nice-to-Have

**N1. Multi-agent coordination tier**
Tasks explicitly designed for agent teams: decomposable work, conflict avoidance requirements, synthesis quality scoring.

**N2. PRD-to-implementation arc**
Full-cycle tasks: agent reads requirements doc → decomposes → implements across sessions → validates against acceptance criteria. The longest-horizon task type.

**N3. Cross-benchmark compatibility**
Adapters to run ITBench SRE scenarios and DevOps-Gym tasks through EnterpriseBench's harness for direct comparison.

**N4. Staleness detection**
CI job that periodically attempts to clone and build all pinned repo versions, flagging breakage before it affects benchmark runs.

## Design Decisions to Resolve via Prototyping

The following questions must be answered by the `/diverge-prototype` phase before finalizing the architecture:

**P1. Multi-repo sandbox feasibility**
- What is the disk footprint of 2-repo and 3-repo sandboxes for representative dependency chains?
- What is the clone + build time overhead vs. single-repo tasks?
- Does Daytona's sandbox limit accommodate this, or do we need a different runtime?

**P2. Verification architecture**
- Can a single `eb_verify` library handle all artifact types with a plugin architecture?
- What does the checkpoint verifier runner look like concretely?
- How much verifier code is needed per task vs. shared?

**P3. Session-chain orchestration**
- Git-branch handoff: what's the minimal orchestrator that chains N single-session Harbor runs?
- How much inter-session variance does this introduce? (Run same 2-session task 5x, measure score distribution)
- Is "resume from mess" a viable alternative that produces equivalent signal?

**P4. Event-replay infrastructure**
- What schema for `events.jsonl` is general enough for CI, monitoring, and PR events?
- How does the agent interact with the event stream? (Read file? Streaming stdin? Polling?)
- How do you score action timeliness, not just correctness?

**P5. Task sourcing from real OSS**
- For 3 candidate dependency chains, can we extract a verifiable task with ground truth in <4 hours of expert effort?
- What's the false-positive rate (historical changes that look like good tasks but aren't verifiable)?

**P6. Cost model**
- Token cost for representative single-session, session-chain, and event-replay tasks
- Sandbox cost (disk, compute, time) per task type
- Total benchmark run cost estimate at 80-100 tasks

## Prototype Success Criteria

Each prototype in the `/diverge-prototype` phase should measure against these criteria:

1. **Feasibility**: Does it work at all? Can you get a multi-repo task running end-to-end?
2. **Reproducibility**: Same task, same agent, 3 runs → score variance < 0.15
3. **Signal quality**: Does the checkpoint scoring produce a distribution with meaningful spread (not all-zero or all-one)?
4. **Cost efficiency**: Is the cost/signal ratio acceptable? (Defined as: total tokens × sandbox-minutes per meaningful score point)
5. **Authoring effort**: How many expert-hours to create one task of each type?
6. **Verification robustness**: Does the verifier correctly reject wrong answers and accept correct ones across 5+ edge cases?

## Research Provenance

Synthesized from 5 independent research agents (via `/diverge`):

1. **Prior Art** — no benchmark tests cross-repo modification; ITBench SRE (11.4% resolution) and DevOps-Gym (700+ tasks) are closest analogs for role-specific work; SWE-EVO is hardest single-session benchmark (21% for GPT-5)
2. **First-Principles** — 4 atomic multi-repo patterns (propagate, investigate, enforce, orchestrate); atom/molecule/organism task hierarchy; docker-compose already exists in CSB but unused for cross-repo
3. **Enterprise Roles** — artifact diversity is the critical missing dimension; Support Engineering is highest-value underserved role; 20 concrete task specs designed across 4 roles
4. **Long-Horizon** — git-branch as inter-session state; event-replay for trigger tasks; "resume from mess" as cheap multi-session proxy; Claude Tasks API has session-chaining primitives
5. **Failure Modes** — verifier consolidation is prerequisite; silent clone failures corrupt data; 90.5% "hard" provides no stratification; `answer.json` gaming vector exists

**Key convergence**: All 5 found current cross-repo tasks aren't genuinely multi-repo. All agreed 2-3 repos is the practical sweet spot. Centralized verification is unanimously a prerequisite.

**Key divergence**: Full multi-session vs. cheap proxies (both valuable, different purposes). Whether to prioritize repo count or artifact diversity (resolution: artifact diversity within multi-repo tasks).
