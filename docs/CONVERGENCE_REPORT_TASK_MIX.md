# Convergence Report: Task Mix Realignment

## Debate Summary

Three positions debated over 2 rounds:

- **Position A (Conversion-First)**: 70/30 conversion/net-new split, count monorepo, ~100 hours
- **Position B (Net-New Diversity)**: 25+ net-new across 5+ ecosystems, don't count monorepo, diversity floor
- **Position C (Phased Pragmatist)**: Fix infra first, phased execution, 45-50% is acceptable if validated

## 1. Resolved Points

### SG Indexing: Quality Gate, Not Phase Gate

**Consensus**: All three positions converged on this. Task authoring can proceed in parallel with SG indexing, but no task enters the final benchmark without at least one MCP-mode evaluation pass confirming the task discriminates between modes. Index repos needed by Phase 1 tasks first.

**Decisive argument**: Position C's original "hard blocker" was too conservative (you can author and baseline-test without SG), but Position A/B's "just work in parallel" was too casual. The quality gate framing satisfies both: speed without compromising validation.

### Cross-Repo Necessity Test (CRNT) for All Tasks

**Consensus**: All positions adopted a concrete, testable quality gate for multi-repo tasks (converted OR net-new):

1. **Information asymmetry**: Answer requires facts from 2+ repos not found in any single repo
2. **Checkpoint distribution**: At least one checkpoint anchored in each repo
3. **Ablation validation**: Remove one repo from sandbox; agent score must drop to ≤50-70% (positions differed on threshold — 50% from A, 70% from C; recommend **≤60%** as compromise)

**Decisive argument**: Position B's challenge ("what distinguishes real dual-repo from window dressing?") forced A and C to commit to testable criteria. This gate applies equally to conversions and net-new tasks.

### Cut 3 Coding-Ability Tasks Immediately

**Consensus**: beam-pipeline-builder-refac-001, ansible-abc-imports-fix-001, aspnetcore-code-review-001. No disagreement.

### Replace-Before-Cut Sequencing

**Consensus**: Never retire a single-repo task until its multi-repo replacement passes CRNT and has at least one MCP-mode evaluation run. All three positions endorsed this.

## 2. Refined Trade-offs

### Conversion Ceiling: 8-12 (Not 15)

Position A originally proposed 15 conversions. After challenges:

- Position C pointed out 5 task types have nothing to convert (zero multi-repo base) — those must be net-new
- Position B argued conversions that redesign the investigation path are "net-new wearing a conversion costume"
- Position A conceded to "12-15 that pass CRNT" and acknowledged 20-25 of 64 have natural extensions

**Refined estimate**: 8-12 genuine conversions that pass CRNT. The best candidates are tasks where the single-repo version already references external dependencies (error traces pointing to upstream libs, configs referencing external schemas). Remaining gap filled by net-new.

**What would tip the balance**: Run CRNT ablation on 5 pilot conversions. If 4/5 pass, the ceiling is closer to 12. If 2/5 pass, it's closer to 8.

### Net-New Task Count: 15-22

- Position B wanted 25+
- Position C wanted 15-20
- Position A wanted 7-8
- After debate: 15-22 net-new, depending on conversion ceiling

Combined with 8-12 conversions and 12 existing multi-repo + monorepo tasks, this reaches 47-58% multi-repo (exact number depends on monorepo accounting and total task count after retirements).

### Ecosystem Diversity: Floor Without Hard Cap

- Position B proposed 25% ecosystem cap — Position A challenged this as self-defeating for measurement power
- No resolution on the cap number, but convergence on the principle: **diversity floor, not ceiling**
- Minimum 5 ecosystem chains represented in multi-repo tasks
- K8s/gRPC ecosystem can exceed 25% if those tasks produce the best discrimination, but must not exceed 40%
- New tasks must introduce at least 3 non-Go ecosystems (Python, Java/Kotlin, Rust or cloud-native)

**What would tip the balance**: Empirical measurement of task discrimination by ecosystem. If Python ecosystem tasks discriminate as well as Go tasks, the cap argument strengthens. If they don't (due to lower codebase complexity), the measurement power argument wins.

### 55% Target: Aspirational Floor, Not Hard Constraint

- Position B treats 55% as a requirement
- Position C argues 45-50% with validation beats rushed 55%
- Position A says monorepo counting makes 55% achievable

**Refined position**: 45% strict multi-repo is the hard floor. 55% including monorepo_cross_package is the aspirational target. Report both numbers.

## 3. Emerged Positions

### Dual-Track Reporting for Monorepo

None of the original positions proposed this cleanly, but it emerged from debate: publish three numbers for every benchmark run:

- **Strict multi-repo** (dual_repo + tri_repo + multi_repo only)
- **Broad multi-repo** (strict + monorepo_cross_package with ≥3 package boundary crossings)
- **Non-calibration total**

This sidesteps the monorepo accounting argument entirely — benchmark consumers choose their denominator. Position B proposed it; A and C moved toward it.

### Functional Monorepo Test

Position C proposed: a monorepo task counts as "broad multi-repo" if it requires traversing 3+ distinct package boundaries with separate maintainers/APIs. This replaces arbitrary percentage haircuts with a testable criterion. All positions moved toward this.

### CRNT as Universal Quality Standard

What started as Position B's challenge to conversions became an agreed standard for ALL multi-repo tasks. This is the debate's most important output — a concrete, testable benchmark for whether a task genuinely requires cross-repo reasoning.

## 4. Strongest Arguments (Preserved)

| Position    | Strongest Argument                                                                                                                                                                                 |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A (Convert) | The Cross-Repo Necessity Test makes the conversion/net-new distinction irrelevant — what matters is whether the task passes CRNT, not how it was authored. Judge tasks by structure, not origin.   |
| B (Diverse) | "Remove the second repo and re-run — if all checkpoints still pass, the conversion is window dressing." This made the quality problem falsifiable and forced concrete criteria from all positions. |
| C (Phased)  | "45% multi-repo with validated quality beats rushed 55% with untested tasks." The benchmark's value comes from measurement power, not ratio arithmetic.                                            |

## 5. Recommended Path

### Phase 1: Infrastructure + Pilot Conversions (concurrent)

- **Fix SG indexing** for the 20-30 repos needed by existing multi-repo tasks + pilot conversions
- **Convert 5 pilot tasks** to dual-repo, applying CRNT ablation to validate the conversion pattern
- **Cut 3 coding-ability tasks** immediately
- **Deliverable**: Working MCP evaluation pipeline + CRNT-validated conversion pattern + data on conversion ceiling
- **Gate**: Phase 2 scope determined by pilot results (conversion pass rate, authoring hours, MCP discrimination)

### Phase 2: Scaled Authoring (conversion + net-new)

- **Convert 3-7 additional tasks** (total 8-12) — only those passing CRNT
- **Author 15-22 net-new multi-repo tasks** across 5+ ecosystems
  - Prioritize 5 task types with zero multi-repo representation (2-3 each)
  - ≥40% using "investigate" pattern
  - Minimum 3 non-Go ecosystem chains
  - 1-2 proof-of-concept 4-repo tasks
- **Quality gate per task**: CRNT ablation pass + at least one MCP-mode evaluation run
- **Deliverable**: 45-55% multi-repo (strict + broad), all 10 types covered

### Phase 3: Calibration & Retirement

- Retire single-repo tasks made redundant by multi-repo replacements
- Final ratio calibration based on discrimination data
- Publish dual-track multi-repo percentages

### Target Outcome

| Metric                                      | Floor           | Target          |
| ------------------------------------------- | --------------- | --------------- |
| Strict multi-repo (excl. monorepo)          | 45%             | 50%+            |
| Broad multi-repo (incl. qualified monorepo) | 50%             | 55%+            |
| Task types with ≥2 multi-repo tasks         | 10/10           | 10/10           |
| Ecosystem chains represented                | 5               | 7+              |
| Tasks passing CRNT                          | 100% multi-repo | 100% multi-repo |

## 6. Debate Highlights

- **advocate-convert**: Introduced the Cross-Repo Necessity Test (CRNT) with three concrete criteria (information asymmetry, checkpoint distribution, ablation validation). This became the universal quality standard adopted by all positions.
- **advocate-diverse**: Made the quality problem falsifiable with "remove the second repo and re-run." Forced the debate from abstract quality concerns to testable acceptance criteria. Also proposed dual-track reporting that resolved the monorepo impasse.
- **advocate-phased**: Reframed SG indexing from "blocker vs not" to "quality gate vs phase gate" — a distinction that unlocked parallel execution without compromising validation. Also correctly identified that Position A's conversion count was inflated by the type-coverage constraint.
