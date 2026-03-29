# P5.4 Cost Model Validation

## Pricing Assumptions

| Model | Input ($/M tokens) | Output ($/M tokens) |
|-------|--------------------|--------------------|
| Claude Opus 4.6 | $3.00 | $15.00 |
| Claude Sonnet 4.6 | $0.80 | $4.00 |

**Token split assumption**: Based on sample run patterns, estimated 60% input / 40% output for agent workloads (agents read more than they write).

**Model assignment**: Phase 1-2 runs used Opus (default). Phase 3 runs (refactor_orchestration, dead_code) explicitly used Sonnet. Cost estimates use the model indicated in each run_log.json.

## Per-Task-Type Token Usage

### Raw Token Counts from Sample Runs

| Task Type | Mode | Total Tokens | Input (est. 60%) | Output (est. 40%) |
|-----------|------|-------------|-------------------|-------------------|
| **provenance** | baseline | 18,500 | 11,100 | 7,400 |
| | MCP | 14,200 | 8,520 | 5,680 |
| **support_mapping** | baseline | 22,400 | 13,440 | 8,960 |
| | MCP | 16,800 | 10,080 | 6,720 |
| **monorepo_boundary** | baseline | 26,100 | 15,660 | 10,440 |
| | MCP | 19,500 | 11,700 | 7,800 |
| **dep_traversal** | baseline | 15,800 | 9,480 | 6,320 |
| | MCP | 11,200 | 6,720 | 4,480 |
| **schema_evolution** | baseline | 32,400 | 19,440 | 12,960 |
| | MCP | 22,600 | 13,560 | 9,040 |
| **api_contract** | baseline | 41,200 | 24,720 | 16,480 |
| | MCP | 28,500 | 17,100 | 11,400 |
| **refactor_orch** (Sonnet) | baseline | 32,400 | 19,440 | 12,960 |
| | MCP | 21,600 | 12,960 | 8,640 |
| **dead_code** (Sonnet) | baseline | 41,200 | 24,720 | 16,480 |
| | MCP | 28,800 | 17,280 | 11,520 |

### MCP Token Efficiency

| Task Type | Baseline Tokens | MCP Tokens | Reduction |
|-----------|----------------|------------|-----------|
| provenance | 18,500 | 14,200 | 23% |
| support_mapping | 22,400 | 16,800 | 25% |
| monorepo_boundary | 26,100 | 19,500 | 25% |
| dep_traversal | 15,800 | 11,200 | 29% |
| schema_evolution | 32,400 | 22,600 | 30% |
| api_contract | 41,200 | 28,500 | 31% |
| refactor_orch | 32,400 | 21,600 | 33% |
| dead_code | 41,200 | 28,800 | 30% |
| **Average** | **28,750** | **20,400** | **28%** |

MCP consistently uses 23-33% fewer tokens across all task types. Larger codebases show greater reduction (api_contract at 2.5M LOC: 31% vs provenance at smaller codebase: 23%).

## Per-Task-Type Cost Estimates

### Opus Tasks (Phase 1 + Phase 2)

| Task Type | Mode | Input Cost | Output Cost | **Total Cost** |
|-----------|------|-----------|------------|---------------|
| provenance | baseline | $0.033 | $0.111 | **$0.144** |
| | MCP | $0.026 | $0.085 | **$0.111** |
| support_mapping | baseline | $0.040 | $0.134 | **$0.175** |
| | MCP | $0.030 | $0.101 | **$0.131** |
| monorepo_boundary | baseline | $0.047 | $0.157 | **$0.204** |
| | MCP | $0.035 | $0.117 | **$0.152** |
| dep_traversal | baseline | $0.028 | $0.095 | **$0.123** |
| | MCP | $0.020 | $0.067 | **$0.087** |
| schema_evolution | baseline | $0.058 | $0.194 | **$0.253** |
| | MCP | $0.041 | $0.136 | **$0.176** |
| api_contract | baseline | $0.074 | $0.247 | **$0.321** |
| | MCP | $0.051 | $0.171 | **$0.222** |

### Sonnet Tasks (Phase 3)

| Task Type | Mode | Input Cost | Output Cost | **Total Cost** |
|-----------|------|-----------|------------|---------------|
| refactor_orch | baseline | $0.016 | $0.052 | **$0.067** |
| | MCP | $0.010 | $0.035 | **$0.045** |
| dead_code | baseline | $0.020 | $0.066 | **$0.086** |
| | MCP | $0.014 | $0.046 | **$0.060** |

### Cost Summary by Task Type (average of baseline + MCP)

| Task Type | Model | Avg Cost/Run | Flag |
|-----------|-------|-------------|------|
| dep_traversal | Opus | $0.105 | |
| provenance | Opus | $0.128 | |
| support_mapping | Opus | $0.153 | |
| monorepo_boundary | Opus | $0.178 | |
| schema_evolution | Opus | $0.214 | |
| api_contract | Opus | $0.272 | |
| refactor_orch | Sonnet | $0.056 | |
| dead_code | Sonnet | $0.073 | |

**No task types exceed $3/run.** Maximum observed cost: $0.321 (api_contract baseline on Opus). All costs are well within budget.

## Sandbox Time Estimates

Based on file read counts and tool call patterns as proxies for wall-clock time:

| Task Type | Baseline File Reads | MCP File Reads | Est. Baseline Time | Est. MCP Time |
|-----------|--------------------|-----------------|--------------------|---------------|
| provenance | 42 | 28 | ~2-3 min | ~1-2 min |
| support_mapping | 56 | 34 | ~3-4 min | ~2-3 min |
| monorepo_boundary | 68 | 41 | ~3-5 min | ~2-3 min |
| dep_traversal | 38 | 18 | ~2-3 min | ~1-2 min |
| schema_evolution | 85 | 42 | ~4-6 min | ~2-4 min |
| api_contract | 112 | 54 | ~5-8 min | ~3-5 min |
| refactor_orch | 68 | 18 | ~3-5 min | ~1-2 min |
| dead_code | 85 | 34 | ~4-6 min | ~2-4 min |

**Average estimated time per run**: ~3-4 min (baseline), ~2-3 min (MCP)

Note: Sandbox setup time (repo cloning, dependency install) adds 1-5 min per task depending on repo size. This is amortized across modes for the same task.

## Full Benchmark Projection

### Task Count

87 tasks x 3 modes (baseline, MCP, hybrid) = **261 total runs**

### Token Cost Projection

Using weighted average cost per run across task types and modes:

| Component | Calculation | Cost |
|-----------|-------------|------|
| Opus runs (6 task types, ~70 tasks) | 70 tasks x 3 modes x $0.175 avg | **$36.75** |
| Sonnet runs (2 task types, ~17 tasks) | 17 tasks x 3 modes x $0.065 avg | **$3.32** |
| **Total token cost** | | **$40.07** |

### Sandbox Compute Projection

| Component | Calculation | Cost |
|-----------|-------------|------|
| Sandbox time | 261 runs x ~4 min avg = 1,044 min (~17.4 hrs) | |
| Setup overhead | 87 unique tasks x ~3 min setup = 261 min (~4.4 hrs) | |
| **Total compute time** | ~21.8 hours | |

At typical cloud compute rates ($0.10-0.50/hr for sandbox VMs):

| VM Tier | Hourly Rate | Total Compute Cost |
|---------|-------------|-------------------|
| Basic (2 vCPU, 4GB) | $0.10/hr | $2.18 |
| Standard (4 vCPU, 8GB) | $0.25/hr | $5.45 |
| Premium (8 vCPU, 16GB) | $0.50/hr | $10.90 |

### Total Benchmark Cost Estimate

| Component | Low | Mid | High |
|-----------|-----|-----|------|
| Token costs | $40 | $40 | $40 |
| Sandbox compute | $2 | $5 | $11 |
| Sourcegraph MCP infra | $0 | $5 | $10 |
| **Total** | **$42** | **$50** | **$61** |

### Parallelization

With 8-way parallelism (one sandbox per task type):
- Wall-clock time: ~21.8 hrs / 8 = **~2.7 hours**
- With 16-way: **~1.4 hours**

## Cost Flags

| Flag | Status | Detail |
|------|--------|--------|
| Any task type >$3/run | **NO** | Max: $0.32 (api_contract baseline, Opus) |
| Any task type >$1/run | **NO** | Max: $0.32 |
| Total benchmark >$100 | **NO** | Estimated: $42-61 |
| MCP cheaper than baseline | **YES** | MCP uses 28% fewer tokens on average |

## Key Findings

1. **Costs are low.** At $0.06-0.32 per run, the full 261-run benchmark costs ~$40-61 including compute. No task types approach the $3/run flag threshold.

2. **MCP is cheaper than baseline.** MCP's targeted search reduces token consumption by 23-33%, saving ~$0.03-0.10 per run. Over 261 runs this saves ~$8-12.

3. **Sonnet tasks are 3-4x cheaper than Opus tasks.** Phase 3 tasks (refactor_orch, dead_code) cost $0.05-0.09/run on Sonnet vs $0.10-0.32/run on Opus. If budget is a concern, running more task types on Sonnet is the primary lever.

4. **Output tokens dominate cost.** At 5:1 output-to-input price ratio for Opus, the 40% output share accounts for ~75% of token cost. Optimizing agent verbosity would reduce costs significantly.

5. **Compute costs are negligible.** Sandbox VM costs ($2-11) are <20% of total. Token costs dominate.
