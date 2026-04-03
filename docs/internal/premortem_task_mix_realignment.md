# Premortem: Task Mix Realignment

Five independent failure analysts explored how this project could fail through different lenses. All five rated their failure mode as Critical severity; four of five rated likelihood as High. This is an unusually strong convergence signal — the project has significant structural risks that must be addressed before Phase 2 scaling.

## 1. Risk Registry

| #   | Failure Lens             | Severity     | Likelihood | Risk Score | Root Cause                                                                                                       | Top Mitigation                                                                             |
| --- | ------------------------ | ------------ | ---------- | ---------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| 1   | Technical Architecture   | Critical (4) | High (3)   | **12**     | 8GB memory limit untested for 3-5 repo tasks; 4-repo PoC is Nice-to-Have not Must-Have                           | Promote 4-repo PoC to Must-Have Phase 1 gate; build in week 1                              |
| 2   | Integration & Dependency | Critical (4) | High (3)   | **12**     | No version-pinning for SG API; no eager mirror creation; upstream tags assumed permanent                         | Eager mirror creation on task proposal; SG API version contract + smoke tests              |
| 3   | Operational              | Critical (4) | High (3)   | **12**     | No capacity model for images x modes x accounts x ablation; infra failures indistinguishable from agent failures | Infrastructure failure detection (exit codes); disk budget model; per-task timeout tiers   |
| 4   | Scale & Evolution        | Critical (4) | High (3)   | **12**     | Multi-repo maintenance is O(tasks x repos), not O(tasks); ground truth rot not budgeted                          | Cap distinct repos at 30-35; pin to SHAs with staleness alerts; budget 20% for maintenance |
| 5   | Scope & Measurement      | Critical (4) | Medium (2) | **8**      | CRNT is structural (score drops) not cognitive (reasoning required); never validated against mode discrimination | Validate CRNT predictive power in Phase 1 before scaling; add cognitive ablation layer     |

## 2. Cross-Cutting Themes

### Theme A: The SG Indexing Abyss (Lenses 1, 2, 3, 5)

Four of five failure narratives identify the 0/131 SG indexing state as a critical vulnerability. The "quality gate not phase gate" consensus from convergence sounds reasonable but creates a dangerous pattern: work accumulates behind an untested gate. If the gate itself is broken (SG API regression, capacity limits, indexing failures), months of work are invalidated simultaneously. The integration lens adds that SG API stability is assumed, not contracted — a silent regression could corrupt months of evaluation data.

**Combined severity**: If SG indexing fails or regresses, the entire benchmark's MCP measurement claim collapses. Every multi-repo task becomes baseline-only, defeating the project's purpose.

### Theme B: The 4-Repo Phantom (Lenses 1, 3, 4)

Three narratives independently conclude that 4+ repo tasks are likely infeasible with current infrastructure but are being deferred rather than tested. The PRD targets 20% "3-5 repo" tasks, but zero exist today. Memory limits (8GB), Docker image sizes (3-4GB projected), and CRNT ablation costs (N+1 runs per task) all compound at 4+ repos. All three recommend killing or gating the 4-repo tier immediately.

**Combined severity**: If 4-repo tasks can't work, 20% of the PRD target is unachievable, and the project will discover this late.

### Theme C: The Maintenance Spiral (Lenses 2, 4)

Two narratives identify ground truth rot as an unbudgeted existential risk. With 60 distinct repos across 7 ecosystems, upstream releases invalidate task ground truth at a rate of ~2-3 tasks/month. No automated staleness detection exists. The integration lens adds that upstream tag deletion can silently break mirror creation, and the scale lens quantifies the maintenance burden at O(tasks x repos).

**Combined severity**: Within 6 months, 10-15% of tasks will have stale ground truth, eroding benchmark credibility.

### Theme D: Infrastructure Failures Masquerading as Agent Failures (Lenses 1, 3)

Two narratives identify that `run_task.py` cannot distinguish OOM kills, disk exhaustion, and timeouts from genuine agent score=0 results. This means infrastructure regressions look like agent capability data, corrupting benchmark measurements silently. The operational lens found evidence this is already happening: `score=0.00 completed (30s)` entries in sweep logs are likely container launch failures.

**Combined severity**: Benchmark results become untrustworthy if infrastructure failures contaminate scoring data.

## 3. Mitigation Priority List

| Priority | Mitigation                                                               | Failure Modes Addressed       | Severity    | Cost           |
| -------- | ------------------------------------------------------------------------ | ----------------------------- | ----------- | -------------- |
| **1**    | Build 4-repo PoC in Phase 1 week 1 (2-day experiment)                    | Technical, Operational, Scale | Critical x3 | Low            |
| **2**    | Index 10-20 SG repos + run end-to-end MCP eval in Phase 1                | Technical, Integration, Scope | Critical x3 | Medium         |
| **3**    | Add infrastructure failure detection (exit codes, distinct from score=0) | Operational, Technical        | Critical x2 | Low            |
| **4**    | Eager mirror creation + pinned SHA manifest with staleness alerts        | Integration, Scale            | Critical x2 | Medium         |
| **5**    | Validate CRNT predicts mode discrimination on 5 pilot tasks              | Scope                         | Critical x1 | Medium         |
| **6**    | Disk budget model + pre-sweep capacity check                             | Operational, Scale            | Critical x2 | Low            |
| **7**    | SG API version contract + weekly smoke tests                             | Integration                   | Critical x1 | Low            |
| **8**    | Cap distinct repos at 30-35; reuse aggressively                          | Scale, Integration            | Critical x2 | Low (planning) |
| **9**    | Per-task timeout tiers (1800/2400/3000s by repo count)                   | Operational                   | Critical x1 | Low            |
| **10**   | Increase checkpoint granularity (min 4 for dual-repo, 6 for tri-repo)    | Scope                         | Critical x1 | Medium         |
| **11**   | Cap CRNT ablation to baseline-mode only (3x cost reduction)              | Operational, Scale            | Critical x2 | Low            |
| **12**   | Create Rust Dockerfile template before authoring Rust tasks              | Operational                   | Critical x1 | Low            |
| **13**   | Nightly CI for MCP mode discrimination trending                          | Integration, Scope            | Critical x2 | Medium         |
| **14**   | Budget 20% ongoing time for ground truth maintenance                     | Scale                         | Critical x1 | High (ongoing) |

## 4. Design Modification Recommendations

### Modification 1: Promote 4-Repo PoC to Must-Have Phase 1 Gate

**What to change**: Move "Build 1-2 proof-of-concept tasks with 4+ repos" from Nice-to-Have to Must-Have. Build it in week 1 of Phase 1. If it fails within 8GB memory, either raise the memory limit or kill the 4-repo tier entirely before committing authoring effort.
**Failure modes addressed**: Technical Architecture, Operational, Scale
**Expected effort**: 2 days

### Modification 2: Add "Infrastructure Validated" Gate Between Phases

**What to change**: Phase 2 must not begin until: (a) 4-repo PoC passes or tier is killed, (b) ≥20 repos SG-indexed with one end-to-end MCP eval, (c) CRNT ablation pipeline validated on all 5 pilot tasks, (d) CRNT predicts mode discrimination (hybrid > baseline) on pilot tasks. This replaces the soft "quality gate" with a hard phase gate for infrastructure — authoring can still proceed in parallel, but Phase 2 _scope_ is locked only after Phase 1 infrastructure validation.
**Failure modes addressed**: All five
**Expected effort**: 1 week (defining gate criteria + validation runs)

### Modification 3: Validate CRNT Predicts Mode Discrimination

**What to change**: In Phase 1, don't just check if pilot tasks pass CRNT — run full 3-mode agent evals and measure whether CRNT-passing tasks show statistically significant mode discrimination. If CRNT doesn't predict discrimination, redesign the quality gate before Phase 2. Add a cognitive ablation layer: run baseline agents on ablated tasks; if they score >30% on "removed repo" checkpoints, the cross-repo dependency is too shallow.
**Failure modes addressed**: Scope & Measurement
**Expected effort**: 1 week (eval runs + analysis)

### Modification 4: Cap Distinct Repos at 30-35 and Implement Freshness Infrastructure

**What to change**: Instead of 60 distinct repos across 7 ecosystems, constrain to 30-35 repos with aggressive reuse. Create `repo_versions.json` manifest with pinned SHAs and "last verified" dates. Weekly CI checks for staleness. Eager mirror creation (mirrors built at task proposal time, not shipping time). Budget 20% of ongoing time for ground truth maintenance.
**Failure modes addressed**: Scale & Evolution, Integration & Dependency
**Expected effort**: 3 days (manifest + CI job) + ongoing 20%

### Modification 5: Distinguish Infrastructure Failures from Agent Failures

**What to change**: Tag container exits with distinct codes in `run_task.py`: OOM (137), disk full, timeout (124) vs clean exit. Report `infra_error` separately from `score=0.00`. Add a pre-sweep disk check that aborts if available space < 2x estimated sweep size. Implement aggressive `docker image prune` between sweep batches.
**Failure modes addressed**: Operational, Technical Architecture
**Expected effort**: 1-2 days

## 5. Full Failure Narratives

### Narrative 1: Technical Architecture Failure

**Severity: Critical | Likelihood: High | Score: 12**

The project collapsed under 8GB Docker memory limits when scaling to 3-5 repo tasks. OOMKill became the dominant failure mode for 40% of 3+ repo tasks. The CRNT ablation protocol multiplied the problem (N+1 runs per task). Meanwhile, 0/131 SG repos indexed meant the MCP quality gate was untestable. The replace-before-cut policy prevented any task retirement. Project shipped at 35% multi-repo.

Root cause: 8GB memory limit inherited from CodeScaleBench without validation for multi-repo workloads.

### Narrative 2: Integration & Dependency Failure

**Severity: Critical | Likelihood: High | Score: 12**

Sourcegraph shipped a breaking API change that silently corrupted MCP search results for 2 months. Simultaneously, 3 upstream repos deleted pinned tags, blocking 8 of 32 proposed tasks. The deferred "quality gate" approach maximized blast radius — months of MCP eval data was invalidated at once. Project shipped at 38% multi-repo with questionable MCP validation.

Root cause: External dependencies (SG API stability, Git tag permanence) treated as stable infrastructure rather than actively managed risks.

### Narrative 3: Operational Failure

**Severity: Critical | Likelihood: High | Score: 12**

Docker storage ballooned past 80GB. Containers failed with "No space left on device" errors reported as score=0.00 — indistinguishable from agent failures. Java tasks exceeded build time budgets. The 4-repo PoC OOM-killed. CRNT ablation became prohibitively expensive (12 container runs per 3-repo task validation). 7 authored tasks couldn't pass operational reliability gates. Project shipped at 41% multi-repo.

Root cause: No operational capacity model for the expanded task portfolio.

### Narrative 4: Scope & Measurement Failure

**Severity: Critical | Likelihood: Medium | Score: 8**

CRNT passed tasks where the second repo contributed only shallow, easily-guessable context. Agents could infer missing facts from training priors. New Python/Java ecosystem tasks showed 15-20% lower mode discrimination than Go tasks. 2-checkpoint tasks made CRNT trivially satisfiable. The benchmark hit numeric targets but failed to discriminate between retrieval strategies. Goodhart's Law case study.

Root cause: CRNT defined as structural (score drops) not cognitive (reasoning required), locked in before empirical validation.

### Narrative 5: Scale & Evolution Failure

**Severity: Critical | Likelihood: High | Score: 8**

Multi-repo task authoring averaged 5-6 hours (vs 3-4 estimated). 11 repos shipped breaking releases within 3 months, invalidating ground truth. The 4-repo PoC consumed 3 weeks of optimization for 2 fragile tasks. Full sweeps cost $1,500-2,500 per run. Authors stopped running MCP evals during development. 14 tasks (13%) had stale ground truth by month 6. The benchmark was larger, more expensive, and less trustworthy than what it replaced.

Root cause: Maintenance burden is O(tasks x repos), not O(tasks); ground truth rot was not budgeted.
