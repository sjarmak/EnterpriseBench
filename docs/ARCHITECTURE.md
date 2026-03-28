# EnterpriseBench Architecture

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
├── benchmarks/                 # Task definitions by suite
│   ├── dependency_management/
│   ├── incident_response/
│   ├── platform_engineering/
│   ├── security_operations/
│   ├── customer_escalation/
│   ├── feature_delivery/
│   └── technical_debt/
├── lib/
│   └── eb_verify/              # Centralized verification library
├── scripts/
│   ├── mining/                 # Task sourcing from OSS history
│   ├── sandbox/                # Multi-repo sandbox management
│   └── orchestration/          # Session chaining, event replay
├── configs/                    # Run configurations
└── docs/                       # Design docs, technical reports
```

## Key Design Principles

1. **One verifier library** — `eb_verify` is installed in every sandbox container. No copies.
2. **Real OSS only** — every task uses real open-source repositories with genuine dependency chains.
3. **Checkpoint scoring** — every task has 2-5 graduated checkpoints for partial credit.
4. **Artifact diversity** — tasks produce role-appropriate outputs, not just `answer.json`.
5. **Multi-repo default** — the sandbox supports 1-5 repos per task natively.

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
```
