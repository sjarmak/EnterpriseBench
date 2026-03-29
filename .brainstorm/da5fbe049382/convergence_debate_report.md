# Convergence Debate Report: EnterpriseBench Task Type Selection

**Session:** da5fbe049382
**Date:** 2026-03-29
**Debate Format:** 3 advocates (MCP-Maximalist, Enterprise-Realist, Feasibility-First), 2 rounds
**Input:** 30 brainstorm ideas for benchmark task types
**Output:** Recommended 10-task suite optimized for Sourcegraph MCP showcase in enterprise scenarios

## Debate Participants

| Advocate | Core Thesis | Selection Criterion |
|----------|-------------|---------------------|
| **MCP-Maximalist** | Prioritize tasks where Sourcegraph MCP advantage is largest and most measurable | MCP signal gap (tool delta) |
| **Enterprise-Realist** | Prioritize tasks representing actual enterprise workflow frequency distribution | Enterprise frequency x impact |
| **Feasibility-First** | Prioritize tasks with strongest ground truth and fastest shipping path | Ground truth quality, CSB reuse, verification complexity |

---

## 1. Resolved Points (Consensus)

### Unanimous Locks (all 3 advocates, both rounds)

These 5 task types were selected by all three advocates without challenge:

| # | Task Type | MCP Signal | Enterprise Freq | Feasibility | PRD Suite |
|---|-----------|-----------|-----------------|-------------|-----------|
| **#1** | Dependency Graph Traversal Races | ★★★★½ | Weekly-Monthly | F=4, Deterministic GT from OSV/NVD | dependency_management |
| **#5** | API Contract Boundary Analysis | ★★★★★ | Weekly | F=4, GT from real breaking-change PRs | dependency_management, feature_delivery |
| **#12** | Monorepo Package Boundary Referee | ★★★★½ | Daily | F=5, GT from semver/CHANGELOG | feature_delivery (monorepo stratum) |
| **#23** | Error Message Provenance Tracing | ★★★★ | Daily | F=5, GT from fix PRs | customer_escalation |
| **#25** | Database Schema Evolution Impact | ★★★★ | Monthly | F=5, GT from migration PRs | feature_delivery, technical_debt |

**Why these converged instantly:** Each scores highly on ALL three axes — strong MCP signal (cross-repo navigation, semantic search, call graph traversal), high enterprise frequency, and deterministic ground truth from real OSS artifacts.

### Converged After Round 2 (with design constraints)

These 3 task types converged with specific scoping:

| # | Task Type | Final Scope | Decisive Argument |
|---|-----------|-------------|-------------------|
| **#22** | Multi-Repo Refactor Orchestration | Verify topological ordering correctness (no broken intermediate states) + correct repo identification. Drop parallelization efficiency scoring. | MCP's ★★★★★ signal + PRD's multi-repo differentiator. Feasibility upgraded after accepting deterministic ordering verification. |
| **#13** | Dead Code / Feature Flag Necropsy | 2-5 tasks under technical_debt suite. Focus on projects with actual cleanup PRs (React, Angular, VS Code). | MCP's "prove absence" argument won: exhaustive reference search is uniquely MCP-enabled. Enterprise conceded after acknowledging the unique cognitive axis. |
| **#18** | Support Ticket Triage → **reframed as "Support Code Mapping"** | De-emphasize severity classification (weight 0.15). Primary checkpoint: identify the code paths that produce the reported behavior (weight 0.60). Use large codebases where navigation is non-trivial. | Feasibility's CSB reuse argument (30-50 adaptable tasks) combined with Enterprise's frequency argument. MCP upgraded after reframing to emphasize navigation over NL understanding. |

---

## 2. Refined Trade-offs (Partially Resolved)

### #9 Incident Replay — INCLUDED with simplified scope

**The tension:** Enterprise needs incident_response coverage (PRD suite). MCP says telemetry correlation is LLM reasoning, not navigation. Feasibility says authoring cost is 8-16hrs/task.

**Resolution:** Include as **simplified incident investigation** (not full event-replay):
- Provide codebase at buggy commit + error log/alert (not full telemetry stream)
- Focus on cross-service root cause tracing (the `investigate` multi-repo pattern)
- Skip event_replay machinery for v1
- 3-5 tasks, Phase 1 stretch goal
- This captures the incident_response workflow while keeping MCP signal (cross-service code tracing) and feasibility (error log + fix PR ground truth)

**What would tip this further:** If a prototype shows event-replay authoring can be done in <4hrs/task using public postmortem templates, expand to full telemetry format in Phase 2.

### #10 Permission/Access Audit — CONDITIONAL inclusion

**The tension:** Strong MCP signal (multi-layer policy chain) and enterprise realism (quarterly compliance), but mining yield uncertain.

**Resolution:** Conditional on mining validation:
- Attempt 2-day focused mining sprint on Keycloak, GitLab CE, Harbor, Casbin, OPA
- If 5+ viable tasks: include as security_operations coverage (3-5 tasks)
- If <5 tasks: replace with #24 Adversarial Sabotage Detection (planted bugs = guaranteed yield)
- Either way, security_operations gets dedicated coverage

### #4 Configuration Drift — INCLUDED as last priority

**The tension:** Low MCP signal (MCP says greppable) vs high feasibility and platform_engineering coverage.

**Resolution:** Include with constraints:
- Scope to COMPLEX drift only: multi-layer Helm chart hierarchies, Terraform module chains, Kustomize overlays
- NOT simple "find the different config value" tasks
- 3-5 tasks filling platform_engineering suite
- This is the lowest-priority inclusion — first to cut if suite becomes too large

---

## 3. Rejected Ideas (Resolved)

### Rejected by majority (2-to-1 or unanimous)

| # | Idea | Rejected Because | Strongest Dissent |
|---|------|-----------------|-------------------|
| **#14** | Cross-Language FFI Bridge | Niche (Enterprise + Feasibility), mining yield <10 | MCP: "Most visually compelling demo of MCP value" — valid but enterprise credibility > demo value |
| **#30** | Observability Gap Analysis | Subjective verification, MCP dropped it | MCP: "Real call graph analysis need" — but many-valid-answers problem kills verification |
| **#2** | Git Archaeology | Low MCP signal, uncertain mining yield | Enterprise: "Temporal understanding is valuable" — but git bisect is the actual tool used |
| **#6** | Onboarding Simulation | No deterministic ground truth | Enterprise: "Every new hire does this" — true but unverifiable |
| **#7** | Release Changelog | Derivative of #12, increasingly automated | — |
| **#8** | Migration Pathfinder | Reasoning-heavy, captured by #22 | Enterprise: "High impact" — but overlaps with refactor orchestration |
| **#11** | Test Gap Cartography | Risk ranking is subjective, coverage tools exist | — |
| **#15** | CI Pipeline Optimization | Non-deterministic verification ("optimal" is subjective) | — |
| **#16** | Ecosystem Health Dashboard | F=2, synthesis task, no deterministic verification | — |
| **#17** | Regression Bisection | Academic framing, overlaps with #2 | MCP: "Beat O(log n) is interesting" — but not enterprise |
| **#19** | ADR Reconstruction | F=2, intent reconstruction is unverifiable | MCP: N=5 novelty — "Hidden Gem" deferred to Phase 3 |
| **#20** | Compliance Regulation Mapping | Requires legal domain expertise, F=3 | Enterprise: "GDPR mapping is real" — but ground truth requires compliance experts |
| **#21** | Performance Cliff Prediction | Predicting dynamic behavior from static analysis is a research problem | MCP: "Catches what reviewers miss" — but that's an LLM reasoning test |
| **#24** | Adversarial Sabotage Detection | Manual bug planting, low CSB reuse | Backup for #10 if mining fails |
| **#26** | Concurrency Bug Recognition | Specialized, rare, hard to mine | MCP: "Different cognitive operation" — true but too narrow |
| **#27** | Build System Dependency Puzzle | Sandbox feasibility (Bazel bootstrap), narrow applicability | — |
| **#28** | Tribal Knowledge Extraction | F=2, LLM-judge-only verification | "Hidden Gem" deferred to Phase 3 |
| **#29** | Cross-Project Design Pattern | Subjective, rare workflow | — |
| **#3** | Living Documentation Sync | Verification is fuzzy ("inconsistency" is subjective) | Enterprise: "Real workflow" — but #23 covers the code-finding component better |

---

## 4. Strongest Arguments (Per Advocate)

**MCP-Maximalist:** *"Tasks like #5 and #22 cannot be solved by clever prompt engineering alone. Either you found all the affected consumers across repos, or you didn't. The scoring is structural, not semantic."* — This argument locked in the anti-gaming principle: the best tasks produce measurable deltas attributable to tools, not models.

**Enterprise-Realist:** *"MCP value should emerge NATURALLY from realistic tasks, not be engineered by selecting MCP-friendly tasks. If MCP doesn't help much with support triage, that's a valid benchmark finding."* — This argument, quoting the PRD directly, prevented cherry-picking and kept the benchmark honest.

**Feasibility-First:** *"A benchmark task is only as good as its verification. If you can't deterministically check whether the agent got it right, you don't have a benchmark — you have a vibes check."* — This argument killed 8+ ideas that sounded brilliant but had no path to deterministic ground truth.

---

## 5. Recommended Suite: 10 Task Types

### Tier 1 — Core Suite (8 task types, ship in Phase 1)

| Priority | # | Task Type | MCP Signal | PRD Suite | Tasks | Ground Truth |
|----------|---|-----------|-----------|-----------|-------|-------------|
| 1 | **#5** | API Contract Boundary Analysis | ★★★★★ | dependency_management | 8-10 | Breaking-change PRs across CNCF repos |
| 2 | **#22** | Multi-Repo Refactor Orchestration | ★★★★★ | technical_debt | 5-8 | Actual PR merge order in cross-repo refactors |
| 3 | **#1** | Dependency Graph Traversal Races | ★★★★½ | dependency_management, security_operations | 10-12 | OSV/NVD CVE affected-package lists + import graphs |
| 4 | **#12** | Monorepo Package Boundary Referee | ★★★★½ | feature_delivery | 8-10 | Semver bumps + CHANGELOG entries |
| 5 | **#25** | DB Schema Evolution Impact Analysis | ★★★★ | feature_delivery | 8-10 | Migration PR file lists |
| 6 | **#23** | Error Message Provenance Tracing | ★★★★ | customer_escalation | 10-12 | Fix PR changed files |
| 7 | **#18** | Support Code Mapping | ★★★½ | customer_escalation | 10-15 | Issue labels + linked fix PRs (highest CSB reuse) |
| 8 | **#13** | Dead Code / Feature Flag Necropsy | ★★★★ | technical_debt | 3-5 | Cleanup PR diffs |

### Tier 2 — Stretch (2 task types, conditional on validation)

| Priority | # | Task Type | MCP Signal | PRD Suite | Tasks | Condition |
|----------|---|-----------|-----------|-----------|-------|-----------|
| 9 | **#9** | Incident Investigation (simplified) | ★★★ | incident_response | 3-5 | Authoring cost <6hrs/task using postmortem templates |
| 10 | **#4** | Configuration Drift Forensics | ★★★ | platform_engineering | 3-5 | Scope to complex hierarchies only |

### Conditional Slot

| # | Task Type | PRD Suite | Condition |
|---|-----------|-----------|-----------|
| **#10** | Permission/Access Audit | security_operations | Mining yields 5+ viable tasks in 2-day sprint |
| **#24** | Adversarial Sabotage Detection (backup) | security_operations | If #10 mining fails |

### Suite Coverage Summary

| PRD Suite | Coverage | Task Types |
|-----------|----------|-----------|
| dependency_management | Strong | #1, #5 |
| incident_response | Conditional | #9 (simplified) |
| platform_engineering | Conditional | #4 |
| security_operations | Conditional | #1 (secondary), #10 or #24 |
| customer_escalation | Strong | #18, #23 |
| feature_delivery | Strong | #5 (secondary), #12, #25 |
| technical_debt | Strong | #13, #22 |

### Total Task Count Estimate: 68-92 tasks

This aligns with the PRD target of 80-100 tasks.

---

## 6. Implementation Order

### Batch 1 — Zero new infrastructure (answer verifier only)
1. **#23** Error Message Provenance — simplest structure, pure "find the code"
2. **#18** Support Code Mapping — highest CSB reuse (30-50 adaptable tasks)
3. **#12** Monorepo Package Boundary — deterministic semver GT, trivial mining

### Batch 2 — Multi-repo sandbox (already prototyped)
4. **#1** Dependency Graph Traversal — single-repo first, then multi-repo
5. **#25** DB Schema Evolution — migration PR mining
6. **#5** API Contract Boundary — multi-repo proto/API changes

### Batch 3 — Deeper authoring effort
7. **#22** Multi-Repo Refactor Orchestration — refactor mining + ordering verification
8. **#13** Dead Code Necropsy — cleanup PR mining

### Batch 4 — Conditional/stretch
9. **#9** Incident Investigation — simplified postmortem-based tasks
10. **#4** Config Drift — complex hierarchy drift tasks
11. **#10** or **#24** — pending mining validation

---

## 7. Debate Highlights

**Most decisive moment:** Feasibility-First's upgrade of #22 from "reject" to "yes" after MCP-Maximalist proposed deterministic ordering verification. This broke a 1-1 deadlock and made #22 unanimous.

**Strongest concession:** MCP-Maximalist dropping #30 (Observability) and acknowledging the subjective verification problem. Showed willingness to cut weak picks.

**Best synthesis:** Enterprise-Realist proposing to embed observability concerns within #9 incident tasks rather than as a standalone type. Reduced suite size while preserving signal.

**Most creative reframe:** Feasibility-First reframing #18 from "Support Ticket Triage" to "Support Code Mapping" — de-emphasizing NL classification, emphasizing codebase navigation. Resolved the MCP signal concern while keeping the enterprise workflow.

**Preserved dissent:** MCP-Maximalist's case for #14 FFI Bridge (cross-language symbol resolution as "most visually compelling MCP demo") was rejected 2-to-1 but the underlying need — a task with dramatic, undeniable MCP delta — is addressed by #5 API Contract Analysis, which tests cross-boundary navigation in an enterprise-realistic wrapper.

---

## 8. Phase 2+ Candidates (Deferred, Not Rejected)

These ideas were too ambitious for Phase 1 but should be revisited:

| # | Idea | When to Revisit | Trigger |
|---|------|----------------|---------|
| **#19** | ADR Reconstruction | Phase 3 | If LLM-judge verification matures |
| **#28** | Tribal Knowledge Extraction | Phase 3 | If PR comment corpus becomes mineable |
| **#14** | FFI Bridge Comprehension | Phase 2 | If cross-language Sourcegraph indexing improves |
| **#20** | Compliance Regulation Mapping | Phase 2 | If legal/compliance domain expertise is available |
| **#24** | Adversarial Sabotage Detection | Phase 1 backup | If #10 mining fails |
