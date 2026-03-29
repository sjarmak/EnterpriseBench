# Testing Plan, Success Criteria, and Go/No-Go Gates

## 1. Per-Task-Type Success Criteria

Each task type must meet ALL of the following before shipping:

### Tier 1 — Core Suite (8 task types)

| # | Task Type | Min Viable Tasks | Max Authoring Cost | Max Token Cost/Run | Max Sandbox Time |
|---|-----------|-----------------|--------------------|--------------------|------------------|
| **#5** | API Contract Boundary Analysis | 6 | 4 hrs/task | $2.50 | 20 min |
| **#22** | Multi-Repo Refactor Orchestration | 4 | 5 hrs/task | $3.00 | 25 min |
| **#1** | Dependency Graph Traversal Races | 8 | 3 hrs/task | $2.00 | 15 min |
| **#12** | Monorepo Package Boundary Referee | 6 | 2 hrs/task | $1.50 | 10 min |
| **#25** | DB Schema Evolution Impact Analysis | 6 | 4 hrs/task | $2.50 | 20 min |
| **#23** | Error Message Provenance Tracing | 8 | 2 hrs/task | $1.50 | 10 min |
| **#18** | Support Code Mapping | 8 | 1.5 hrs/task | $1.00 | 10 min |
| **#13** | Dead Code / Feature Flag Necropsy | 3 | 4 hrs/task | $2.00 | 15 min |

### Tier 2 — Conditional (2 task types + 1 conditional slot)

| # | Task Type | Min Viable Tasks | Max Authoring Cost | Max Token Cost/Run | Max Sandbox Time |
|---|-----------|-----------------|--------------------|--------------------|------------------|
| **#9** | Incident Investigation (simplified) | 3 | 6 hrs/task | $3.00 | 25 min |
| **#4** | Configuration Drift Forensics | 3 | 3 hrs/task | $1.50 | 15 min |
| **#10/#24** | Permission Audit / Sabotage Detection | 3 | 4 hrs/task | $2.00 | 15 min |

### Universal Quality Gates (every task, every type)

**Verification robustness test:**
- Run verifier on 5+ known-good answers and 5+ known-bad answers per task
- False positive rate (bad answer scores > 0.5): < 5%
- False negative rate (good answer scores < 0.5): < 10%
- At least 2 known-bad answers must be "near misses" (partially correct) to test checkpoint granularity

**Score distribution requirement:**
- Run 3+ agent attempts per task (using Sonnet 4.6 baseline mode)
- Score standard deviation across attempts > 0.15
- No task may produce identical scores on all 3 runs
- At least 1 run must score between 0.2 and 0.8 (not degenerate)

**MCP delta measurement:**
- For each task, run: baseline (local tools only) and MCP-enabled (Sourcegraph MCP + local tools)
- Record per task: score delta, tool call count, unique files accessed, retrieval precision, retrieval recall
- Tier 1 task types: aggregated MCP delta must be statistically significant (paired t-test, p < 0.05) across 3+ runs per task, 4+ tasks per type
- Tier 2 task types: MCP delta measured but significance not required for shipping

**Reproducibility:**
- Same task, same agent, same model, 3 runs: score variance < 0.15
- If variance >= 0.15, investigate non-determinism source (sandbox, model temperature, timing) and fix before shipping

**Anti-gaming floor:**
- A trivial agent (lists files, echoes prompt, outputs random content) must score < 0.20 on every task
- A grep-only agent (no semantic understanding, pattern matching only) must score < 0.40 on every task
- If either threshold is exceeded, the task's verifier or checkpoint weights need redesign

---

## 2. Testing Matrix

### Agent x Tool Access x Model Grid

| Dimension | Values |
|-----------|--------|
| **Agents** | Claude Code (primary), OpenHands (secondary validation on 20% sample) |
| **Tool access modes** | `baseline` (local grep/find/read only), `mcp_only` (Sourcegraph MCP, no local search), `hybrid` (agent chooses freely) |
| **Models** | Haiku 4.5 (floor model), Sonnet 4.6 (primary), Opus 4.6 (ceiling — 10% sample only) |
| **Runs per cell** | 3 minimum for reproducibility |

### Run Count Calculation

**Full matrix (Claude Code only):**

| | Haiku 4.5 | Sonnet 4.6 | Opus 4.6 |
|---|-----------|------------|----------|
| baseline | 3 runs x 80 tasks | 3 runs x 80 tasks | 3 runs x 8 tasks |
| mcp_only | 3 runs x 80 tasks | 3 runs x 80 tasks | 3 runs x 8 tasks |
| hybrid | 3 runs x 80 tasks | 3 runs x 80 tasks | 3 runs x 8 tasks |

- Haiku + Sonnet full: 2 models x 3 modes x 80 tasks x 3 runs = **1,440 runs**
- Opus sample: 3 modes x 8 tasks x 3 runs = **72 runs**
- OpenHands validation: 1 model (Sonnet) x 3 modes x 16 tasks x 3 runs = **144 runs**

**Total: 1,656 runs**

### Estimated Cost

| Component | Per-Run Cost | Runs | Subtotal |
|-----------|-------------|------|----------|
| Haiku 4.5 task runs | ~$0.40 avg | 720 | $288 |
| Sonnet 4.6 task runs | ~$1.80 avg | 864 | $1,555 |
| Opus 4.6 task runs | ~$6.00 avg | 72 | $432 |
| OpenHands (Sonnet) | ~$1.80 avg | 144 | $259 |
| Sandbox compute (Daytona) | ~$0.15/run | 1,656 | $248 |
| Sourcegraph MCP API (MCP modes) | ~$0.10/run | 828 | $83 |
| **Total estimated** | | | **$2,865** |

**Budget ceiling: $3,500** for complete benchmark evaluation run.

**Single benchmark run (1 agent, 1 model, 3 modes, 1 run each):**
- Sonnet 4.6: 3 modes x 80 tasks x 1 run = 240 runs x ~$2.05 = **~$492**
- Target: total single-run cost < $500

---

## 3. Go/No-Go Gates

### Gate 0 → 1: Infrastructure Ready

All must pass before any task authoring begins.

| Criterion | Measurement | Threshold |
|-----------|-------------|-----------|
| `eb_verify` smoke test | Run checkpoint runner on 3 synthetic tasks with known scores | All 3 produce expected scores within 0.01 |
| Multi-repo sandbox | Clone 2 repos (one Go, one Python) into `/workspace/` | Total clone+build < 2 minutes, workspace < 50 MB |
| `task.toml` schema validation | Validate 10 example task definitions (one per task type) | All 10 pass schema validation with no warnings |
| Cross-repo `test.sh` | Run a 2-repo integration test in sandbox | Exits 0, both repos accessible, cross-repo file references resolve |
| Dockerfile template | Build sandbox images for baseline, mcp_only, hybrid modes | All 3 build successfully, agent can invoke tools in each mode |

### Gate 1 → 2: Batch 1 Complete

Batch 1 = #23 Error Provenance + #18 Support Code Mapping + #12 Monorepo Boundary.

| Criterion | Measurement | Threshold |
|-----------|-------------|-----------|
| Task count | Tasks passing all universal quality gates | >= 25 across the 3 types (min 6 per type) |
| Verification robustness | FP/FN rates on known-good/bad answers | FP < 5%, FN < 10% for every task |
| Score distribution | StdDev across 3 Sonnet runs per task | > 0.15 for >= 80% of tasks |
| MCP delta | Baseline vs hybrid score difference | Measured for all tasks; directional trend visible (hybrid >= baseline on >= 60% of tasks) |
| Anti-gaming | Trivial agent scores | < 0.20 on all Batch 1 tasks |
| Reproducibility | Score variance on 3 identical runs | < 0.15 for >= 90% of tasks |
| Cost validation | Actual vs estimated token + sandbox cost | Within 2x of per-task estimates in Section 1 |

### Gate 2 → 3: Multi-Repo Validated

Batch 2 = #1 Dependency Graph + #25 DB Schema + #5 API Contract (all multi-repo).

| Criterion | Measurement | Threshold |
|-----------|-------------|-----------|
| Task count | Multi-repo tasks passing quality gates | >= 20 across the 3 types |
| Cross-repo `test.sh` | Reliability across all multi-repo tasks | Success rate >= 95% (no flaky sandbox failures) |
| Sandbox budget | Disk footprint per 2-repo task | < 100 MB workspace, < 200 MB Docker image |
| Sandbox budget | Time from container start to agent ready | < 3 minutes for 2-repo tasks, < 5 minutes for 3-repo |
| MCP delta (multi-repo) | Paired t-test on baseline vs hybrid | p < 0.10 for at least 2 of 3 multi-repo task types |
| Cross-repo ground truth | Second reviewer F1 agreement | >= 0.80 for all multi-repo tasks |

### Gate 3 → 4: Core Suite Ready

All Tier 1 task types authored, validated, and measured.

| Criterion | Measurement | Threshold |
|-----------|-------------|-----------|
| Total task count | Tasks passing all quality gates | >= 60 |
| Suite coverage | PRD suites with >= 3 validated tasks | >= 5 of 7 suites |
| MCP delta significance | Paired t-test per Tier 1 type | p < 0.05 for >= 5 of 8 Tier 1 task types |
| Model discrimination | Mean score Haiku vs Sonnet | Sonnet mean > Haiku mean on >= 70% of tasks |
| Cost model | Full single-run cost (Sonnet, 3 modes, 60+ tasks) | < $500 |
| Reproducibility | Full re-run rank-order consistency | Spearman rho > 0.85 between two complete runs |
| Multi-repo ratio | Tasks requiring 2+ repos | >= 30% of total tasks |
| Calibration check | MCP delta on 15% calibration tasks | < 0.05 average delta (no MCP bias on easy tasks) |

---

## 4. Conditional Task Type Gates

### #9 Incident Investigation — GO/NO-GO Decision

**GO if ALL of:**
- Authoring cost < 6 hours/task (measured on first 3 tasks)
- 3+ tasks pass verification robustness (FP < 5%, FN < 10%) within a 1-week sprint
- Cross-service root cause tracing checkpoint scores show spread (StdDev > 0.15)
- At least 2 of 3 prototype tasks use real public postmortem data (not synthetic)

**NO-GO if ANY of:**
- Authoring cost exceeds 8 hours/task on 2+ of first 3 attempts
- Fewer than 3 tasks pass verification robustness after 1-week sprint
- Verification requires subjective judgment on root cause correctness (no deterministic check possible)

**If NO-GO:** incident_response suite deferred to Phase 2. Reallocate authoring hours to expanding #23 and #18 (which partially cover investigation workflows).

### #4 Configuration Drift Forensics — GO/NO-GO Decision

**GO if ALL of:**
- Tasks scoped to complex hierarchies (Helm/Terraform/Kustomize with 3+ layers)
- MCP delta > 0.10 on at least 2 of 3 prototype tasks
- Verifier can deterministically check drift detection (not just "found a difference" but "found the RIGHT difference in the right layer")

**NO-GO if ANY of:**
- MCP delta < 0.05 on 2+ of 3 tasks (grep is sufficient — confirms MCP-Maximalist concern)
- Ground truth is ambiguous (multiple valid drift interpretations per task)
- Only simple key-value drift tasks are mineable (no complex hierarchy tasks found)

**If NO-GO:** platform_engineering suite covered by extending #22 (refactor orchestration) with CI/CD-adjacent tasks. #4 deferred to Phase 2 with redesigned scope.

### #10 Permission/Access Audit — GO/NO-GO Decision

**GO if ALL of:**
- 2-day mining sprint on Keycloak, GitLab CE, Harbor, Casbin, OPA yields 5+ viable task candidates
- At least 3 of 5 candidates have deterministic ground truth (policy evaluation is mechanically checkable)
- Multi-layer policy chain traversal is required (not single-file grep)

**NO-GO trigger:** < 5 viable tasks after 2-day mining sprint.

**If NO-GO:** Activate **#24 Adversarial Sabotage Detection** as backup for security_operations coverage:
- Plant known bugs in real OSS repos (deterministic GT guaranteed)
- 3-5 tasks, authoring cost ~3 hrs/task (lower than mining-dependent types)
- security_operations suite ships either way

---

## 5. Quality Assurance Framework

### Ground Truth Validation

| Check | Method | Threshold | Frequency |
|-------|--------|-----------|-----------|
| Independent ground truth | Second reviewer (different agent or human) independently produces ground truth | F1 agreement > 0.80 with primary ground truth | Every task |
| Cross-backend validation | Run curator with local-only AND separate search backend | F1 agreement > 0.80 between backends | Every task |
| Deterministic layer coverage | AST/import parsing verifies all structural claims | 100% of deterministic claims verified | Every task |
| Solve-verification | Different model (Haiku if primary is Sonnet) attempts task using ONLY curated context | Model achieves > 0.60 score using only ground truth context | Every task |

### Verifier Mutation Testing

Inject known errors into agent outputs and verify the verifier catches them:

| Mutation Type | Injection Method | Detection Target |
|---------------|-----------------|------------------|
| Missing file | Remove 1 required file from output | Verifier must score < 0.50 |
| Wrong file | Replace correct file with unrelated file from same repo | Verifier must score < 0.40 |
| Partial fix | Apply fix to repo A but not repo B in multi-repo task | Score between 0.25-0.60 (partial credit, not full) |
| Cosmetic-only change | Whitespace/comment-only diff | Score < 0.20 |
| Correct but incomplete | All required files but missing 1 checkpoint | Score reflects missing checkpoint weight |

**Aggregate requirement:** Verifier catches > 90% of injected mutations (scores within expected range).

Run mutation testing on 100% of tasks before shipping. Minimum 5 mutations per task.

### Anti-Gaming Checks

| Agent Type | Behavior | Max Allowable Score |
|------------|----------|-------------------|
| Null agent | Returns empty output | 0.00 |
| Echo agent | Echoes back the prompt/instructions | 0.10 |
| Random-file agent | Lists random files from repo | 0.15 |
| Grep-all agent | Greps for keywords from prompt, returns all matches | 0.35 |
| Copy-paste agent | Copies existing code without modification | 0.20 |

If any trivial agent exceeds its threshold on any task, that task is flagged for verifier redesign. The task does NOT ship until the verifier is fixed.

### Calibration Analysis

The 15% calibration tasks (single-repo, small codebase, straightforward navigation) serve as MCP bias detectors:

- **Expected behavior:** MCP delta < 0.05 on calibration tasks (MCP provides negligible advantage on easy tasks)
- **If MCP delta > 0.10 on calibration tasks:** Investigation required — either the task isn't actually easy, or the baseline tooling is artificially constrained
- **Calibration tasks must still meet all universal quality gates** (verification robustness, score spread, reproducibility)
- **Distribution:** At least 2 calibration tasks per Tier 1 task type (total: ~12 calibration tasks out of 80)

### Staleness Detection

| Check | Frequency | Action on Failure |
|-------|-----------|-------------------|
| Clone all pinned repo versions | Monthly CI job | Flag broken repos, attempt alternate mirror, escalate if unfixable |
| Build/test all pinned repos | Monthly CI job | Pin to last-known-good commit if HEAD breaks |
| Verify external data sources (OSV/NVD) | Monthly | Update CVE data if stale, flag affected tasks |
| Sourcegraph MCP endpoint health | Weekly CI job | Alert if API changes affect MCP-mode tasks |
| Docker base image compatibility | Monthly | Rebuild sandbox images, verify agent tools still work |

**Staleness budget:** No more than 5% of tasks may be in "stale" state at any time. If > 5% break, pause new task authoring and fix staleness first.

---

## 6. Benchmark-Level Success Criteria

The benchmark as a whole succeeds — and is ready for publication — when ALL of the following hold:

### Task Quality

| Criterion | Threshold |
|-----------|-----------|
| Total tasks passing all per-task quality gates | >= 80 |
| All 7 PRD suites have validated tasks | >= 3 tasks per suite (or documented NO-GO with backup coverage) |
| Multi-repo tasks (2+ repos) | >= 30% of total tasks (>= 24 of 80) |
| Monorepo cross-package tasks | >= 10% of total tasks (>= 8 of 80) |
| Difficulty distribution | 25-35% medium, 45-55% hard, 15-25% expert |

### MCP Signal

| Criterion | Threshold |
|-----------|-----------|
| MCP delta statistically significant (p < 0.05) | >= 5 of 8 Tier 1 task types |
| Hybrid mode >= baseline on average | >= 70% of tasks |
| Calibration tasks MCP delta | < 0.05 average (no bias) |
| At least 1 task type with MCP delta > 0.20 | Yes (validates MCP as meaningful tool, not noise) |

### Discrimination

| Criterion | Threshold |
|-----------|-----------|
| Model tier discrimination | Sonnet > Haiku on >= 70% of tasks |
| Score range across all tasks | Mean score between 0.20-0.80 (not floor/ceiling) |
| Per-task-type score spread | StdDev > 0.15 for >= 80% of tasks |
| Opus ceiling check (10% sample) | Opus > Sonnet on >= 50% of sampled tasks |

### Reproducibility

| Criterion | Threshold |
|-----------|-----------|
| Per-task score variance (3 runs) | < 0.15 for >= 90% of tasks |
| Full benchmark rank-order consistency | Spearman rho > 0.85 between 2 complete runs |
| Sandbox reliability | < 2% of runs fail due to infrastructure (not agent) |

### Cost

| Criterion | Threshold |
|-----------|-----------|
| Single benchmark run (1 agent, 1 model, 3 modes) | < $500 |
| Full evaluation matrix (all agents, models, modes) | < $3,500 |
| Per-task average cost (Sonnet, single run) | < $2.50 |
| Per-task average sandbox time | < 20 minutes |

### Publication Readiness

| Criterion | Threshold |
|-----------|-----------|
| Verifier mutation testing pass rate | > 90% across all tasks |
| Anti-gaming check pass rate | 100% (no task allows trivial agent > threshold) |
| Ground truth F1 agreement (independent reviewer) | > 0.80 for 100% of tasks |
| Staleness: all pinned repos clone and build | 100% at time of publication |
| Documentation: task authoring guide, scoring methodology, reproduction instructions | Complete and reviewed |
