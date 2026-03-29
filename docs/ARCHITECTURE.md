# EnterpriseBench Architecture

## Overview

EnterpriseBench evolves CodeScaleBench (275 tasks, 6 harnesses, Harbor contract) into a benchmark focused on **context retrieval quality** — measuring how well agents find and understand the right code across distributed codebases. Sourcegraph MCP is showcased through honest comparison as a controlled independent variable.

## Directory Structure

```
EnterpriseBench/
├── PRD.md                      # Product requirements (source of truth)
├── CLAUDE.md                   # Agent navigation guide
├── .claude/commands/           # Slash command skills
│   ├── diverge.md              # Multi-perspective research
│   ├── diverge-prototype.md    # Divergent prototyping in worktrees
│   └── converge.md             # Structured debate via Agent Teams
├── schemas/
│   └── task.schema.json        # Task definition schema
├── benchmarks/                 # Task definitions by suite (100 tasks)
│   ├── dependency_management/
│   ├── incident_response/
│   ├── platform_engineering/
│   ├── security_operations/
│   ├── customer_escalation/
│   ├── feature_delivery/
│   ├── technical_debt/
│   └── mined/                  # Mining candidate lists and provenance
├── lib/
│   └── eb_verify/              # Centralized verification library
├── scripts/
│   ├── mining/                 # Task sourcing from OSS history
│   ├── sandbox/                # Multi-repo sandbox management
│   └── orchestration/          # Session chaining, event replay
├── configs/                    # Run configurations
├── results/                    # Run results and sample outputs
│   └── sample_runs/            # Sample verification outputs by task type
└── docs/                       # Design docs, technical reports
```

## Key Design Principles

1. **One verifier library** — `eb_verify` is installed in every sandbox container. No copies.
2. **Real OSS only** — every task uses real open-source repositories with genuine dependency chains.
3. **Checkpoint scoring** — every task has 2-5 graduated checkpoints for partial credit.
4. **Artifact diversity** — tasks produce role-appropriate outputs, not just `answer.json`.
5. **Multi-repo default** — the sandbox supports 1-5 repos per task natively.
6. **Tool-independent ground truth** — curator never uses Sourcegraph or any evaluated tool.

## Ground Truth Architecture (Layered)

Three tiers replace the single-source curator (F1=0.70):

| Tier | Method | What It Covers | LLM? |
|------|--------|---------------|------|
| 1 — Deterministic | AST parsing, import graphs, dependency manifests (go.mod, package.json) | Structural dependencies, mechanically verifiable | No |
| 2 — LLM Curator | Semantic relevance analysis with cross-backend validation | Config files, docs, cross-cutting concerns | Yes |
| 3 — Solve-verification | Different model attempts task using ONLY curated context | Context sufficiency confirmation | Yes |

**QA overlay**: Confidence-weighted scoring, adversarial audit on sample, mutation testing on verifiers.

### Curator Best Practices
- Tool-independent generation (never uses Sourcegraph during ground truth creation)
- Cross-backend validation: local-only AND separate search backend, agreement >80% F1 = high confidence
- Two-tier annotation: every file labeled "required" or "sufficient"
- Chunk-level annotations: line ranges per file, not just paths
- Confidence metadata: each file carries confidence score + source

## Scoring Architecture

| Layer | Mechanism | Impact |
|-------|-----------|--------|
| Required files | Deterministic + curator agreement | Missing = significant penalty (binary match) |
| Sufficient files | Curator-identified, lower confidence | Missing = small penalty (soft matching) |
| Chunk-level | Line ranges within files | Block-level precision/recall |
| Checkpoints | 2-5 graduated per task | Partial credit for intermediate progress |

## Task Mix Gradient

| Stratum | Share | Description |
|---------|-------|-------------|
| calibration | 15% | Single-repo, small codebase. MCP advantage should be <0.05. Bias check. |
| large_single | 25% | Large single-repo tasks |
| dual_repo | 30% | Two connected repos |
| multi_repo | 20% | 3-5 repos with dependency chains |
| monorepo_cross_package | 10% | Cross-package within monorepo |

## MCP Integration (Three Modes)

Every task can run in three tool-access modes:

| Mode | Description | Dockerfile |
|------|-------------|-----------|
| baseline | No MCP tools, local search only | Standard |
| mcp_only | Mandatory Sourcegraph MCP | SG-Only |
| hybrid | Agent chooses tools freely | Hybrid (realistic) |

- 178 sg-evals mirrors from CSB, extended for multi-repo tasks
- Rich metadata captured per run: MCP tools called, frequency, latency, token cost
- 15% calibration tasks verify MCP bias < 0.05 on easy tasks

## QA Pipeline

- **Cross-stage integration tests**: Canary tasks run end-to-end on every change
- **Expanded fixture matrix**: 6 artifact types validated
- **Mutation testing**: Verifier scripts tested with known-good and known-bad submissions
- **Pre-flight checks**: Sandbox health, repo presence, clone integrity
- **Golden validation**: Reference solutions for regression detection

## Verification Flow

```
Agent completes task
  → Sandbox health check (all repos present, no clone failures)
  → For each checkpoint (ordered):
      → Run checkpoint verifier script
      → Collect pass/fail + score
  → For each required artifact:
      → Validate artifact type (syntax, linting, structure)
  → Compute weighted total score
  → Write reward.txt
```

## Session Types

| Type | Container Lifecycle | State Mechanism | Scoring |
|------|-------------------|-----------------|---------|
| single | One container, one run | N/A | Checkpoints at end |
| chain | N containers, sequential | Git branch between sessions | Milestones between + checkpoints at end |
| event_replay | One container, event stream | events.jsonl → actions.jsonl | Action correctness + timeliness |
| resume | One container, pre-populated branch | Git branch + progress doc | Checkpoints at end (same as single) |

## CSB Relationship

EnterpriseBench inherits and extends CSB infrastructure:
- 275 tasks (220 Org + 55 SDLC) carry forward
- 6 existing harnesses remain compatible
- Harbor contract for container orchestration
- Task taxonomy migrated from SDLC/Org splits to 7 enterprise workflow clusters
- Metadata consolidated from 8+ scattered files to single source of truth
