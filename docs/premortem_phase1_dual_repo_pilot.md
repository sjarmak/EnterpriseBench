# Premortem: Phase 1 Dual-Repo Pilot

> 5 independent failure lenses, synthesized 2026-04-03.

## 1. Risk Registry

| #   | Failure Lens             | Severity     | Likelihood | Score  | Root Cause                                                                                                    | Top Mitigation                                                               |
| --- | ------------------------ | ------------ | ---------- | ------ | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1   | Technical Architecture   | Critical (4) | High (3)   | **12** | `repo_deps` annotations are disconnected from verifier logic — validator checks metadata, not actual behavior | Require verifier-level enforcement: CI runs each verifier in ablated sandbox |
| 2   | Integration & Dependency | Critical (4) | High (3)   | **12** | No automated verification that pinned SHAs exist, required_files resolve, or cross-repo APIs match            | Implement `--verify-files` in CI; pin knftables SHA immediately              |
| 3   | Operational              | Critical (4) | High (3)   | **12** | Output directory has no rep/variant slot; Docker tags don't include ablation variant                          | Add rep index + ablation variant to output paths and image tags              |
| 4   | Scope & Requirements     | Critical (4) | Medium (2) | **8**  | Pilot validates CRNT protocol but not conversion viability (mode discrimination)                              | Add mode discrimination gate: 2/4 tasks must show effect size d>0.5          |
| 5   | Scale & Evolution        | High (3)     | High (3)   | **9**  | Per-ecosystem discovery cost never measured; staleness maintenance not budgeted                               | Ecosystem bootstrapping spike (1 week per target ecosystem) before Phase 2   |

## 2. Cross-Cutting Themes

### Theme A: Annotation-Reality Gap (Lenses 1, 2)

Both the technical and integration lenses independently identified the same structural vulnerability: **the pilot relies on human-authored metadata (repo_deps annotations, required_files paths) that is never mechanically verified against the actual codebase or verifier behavior**. The technical lens showed repo_deps can be wrong relative to what verifiers actually check. The integration lens showed required_files paths can be wrong relative to what actually exists at pinned SHAs. Both are instances of the same root cause: metadata is treated as ground truth without validation.

**Combined severity**: If both manifest (likely, since they're independent failure modes), the entire pilot dataset is unreliable — CRNT passes tasks with wrong annotations, and evaluation runs against wrong file paths.

**Unified mitigation**: Build a single CI gate that (a) clones every referenced repo at its pinned SHA, (b) verifies all required_files paths exist, and (c) runs each verifier in an ablated sandbox to confirm repo_deps are accurate. Cost: ~2 days implementation, runs in <10 minutes per task.

### Theme B: Missing Orchestration Layer (Lenses 3, 5)

The operational and evolution lenses both identified that **no orchestration exists between run_task.py (single-task) and the 48-run pilot**. The operational lens found concrete bugs (tag collisions, output overwrites, disk exhaustion). The evolution lens found the same gap at Phase 2 scale (no batch runner, no staleness-aware scheduling). Both assume "the caller will parallelize" but no caller has been written.

**Combined severity**: Without a batch orchestrator, every pilot run batch will require manual coordination, increasing the probability of the operational bugs being triggered.

### Theme C: Protocol Validation ≠ Product Validation (Lenses 4, 5)

The scope and evolution lenses both identified that **validating CRNT works is different from validating that converted tasks measure what the benchmark claims**. The scope lens showed conversions may pass CRNT but fail to discriminate between tool-access modes. The evolution lens showed the conversion difficulty spectrum doesn't transfer across ecosystems. Both point to the same gap: the pilot answers "does the validator work?" but not "does the approach work?"

## 3. Mitigation Priority List

| Priority | Mitigation                                                                                | Failure Modes Addressed          | Effort               |
| -------- | ----------------------------------------------------------------------------------------- | -------------------------------- | -------------------- |
| **P0**   | Pin knftables SHA from K8s vendor/modules.txt; verify dandydeveloper/charts accessibility | Integration (#2)                 | 1 hour               |
| **P0**   | Add rep index + ablation variant to output paths and Docker image tags                    | Operational (#3)                 | 2 hours              |
| **P1**   | Implement `--verify-files` on check_repo_staleness.py; run in CI                          | Integration (#2), Evolution (#5) | 1 day                |
| **P1**   | Wire `config.build_timeout` to `_docker_build`; fix disk space pre-flight for concurrency | Operational (#3)                 | 3 hours              |
| **P1**   | Write `run_pilot.py` batch orchestrator with rep tracking and retry                       | Operational (#3), Evolution (#5) | 1-2 days             |
| **P2**   | Add verifier grounding test: run verifier in ablated sandbox, confirm it fails            | Technical (#1)                   | 1-2 days             |
| **P2**   | Add mode discrimination gate to pilot acceptance criteria (effect size d>0.5)             | Scope (#4)                       | Design only          |
| **P2**   | Ecosystem bootstrapping spike: 1 task per target ecosystem before Phase 2 commit          | Evolution (#5)                   | 1 week per ecosystem |
| **P3**   | Ground truth repair automation (git log --follow for renames)                             | Evolution (#5)                   | 2-3 days             |
| **P3**   | Staleness budget hard gate in task_mix_validator                                          | Evolution (#5)                   | 3 hours              |

## 4. Design Modification Recommendations

### Mod 1: Verifier Grounding Gate (addresses #1, #2)

**Change**: For each checkpoint with `repo_deps`, add a CI step that runs the verifier with a known-good answer but the declared repo absent. The verifier must fail. If it passes, the `repo_deps` annotation is incorrect.

**Why**: Closes the annotation-reality gap identified by lenses 1 and 2. Makes `repo_deps` a testable claim rather than an untestable assertion. This is the single highest-value change because it transforms static CRNT from metadata validation into behavioral validation — at build time, not runtime.

**Effort**: 1-2 days. Requires a "golden answer" fixture per checkpoint (can be derived from ground truth).

### Mod 2: Batch Orchestrator with Rep Tracking (addresses #3, #5)

**Change**: Write `run_pilot.py` that takes a run manifest (task × mode × rep × ablation_variant), assigns runs to accounts, manages parallelism, partitions output directories, and produces a summary CSV. Image tags include ablation variant. Disk pre-flight scales with concurrency.

**Why**: Eliminates the three most likely operational failures (tag collision, output overwrite, disk exhaustion) and creates reusable infrastructure for Phase 2. Without this, the 48-run pilot requires manual coordination.

**Effort**: 1-2 days.

### Mod 3: Mode Discrimination as Pilot Gate (addresses #4)

**Change**: Add acceptance criterion: at least 2 of 4 converted tasks must show mean(hybrid) > mean(baseline) with Cohen's d > 0.5 before Phase 2 begins. If conversions fail but net-new tasks pass, pivot Phase 2 to net-new authoring only.

**Why**: Prevents the "structurally valid but empirically useless" failure mode where the benchmark hits 55% multi-repo but half the tasks don't discriminate. The pilot should answer "do conversions work?" not just "does CRNT work?"

**Effort**: Design change only (add acceptance criterion to PRD). Evaluation data comes from existing 36-run plan.

### Mod 4: Pre-Flight Dependency Verification (addresses #2)

**Change**: Before any pilot task is authored, verify: (a) all repos exist and are clonable at pinned SHAs, (b) all required_files paths resolve, (c) cross-repo function signatures match at pinned versions. Implement as `scripts/validation/verify_task_deps.py`.

**Why**: Catches the integration failures (wrong paths, archived repos, vendored version mismatch) at authoring time rather than evaluation time.

**Effort**: 1 day.

### Mod 5: Ecosystem Bootstrapping Spike (addresses #5)

**Change**: Before committing to Phase 2 scope, spend 1 week per target ecosystem (Python/Django, Java/Spring, Rust/tokio) attempting to author 1 dual-repo task. Measure actual discovery hours. Use results to set per-ecosystem quotas for Phase 2.

**Why**: The pilot validated CRNT in the K8s ecosystem only. Ecosystem bootstrapping cost is the primary unknown for Phase 2 scaling. One week of discovery is cheaper than committing to 15-22 tasks and stalling at 3.

**Effort**: 1 week per ecosystem (3 weeks total for 3 ecosystems).

## 5. Full Failure Narratives

_(Included by reference — delivered by 5 independent agents during premortem exercise. See teammate messages in conversation history.)_

| Lens                     | Agent              | Key Quote                                                                                                                                                   |
| ------------------------ | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Technical Architecture   | fail-1-technical   | "The new system replaced a mechanical heuristic with an unvalidated human assertion — a strictly worse epistemic foundation dressed up as precision."       |
| Integration & Dependency | fail-2-integration | "We treated dependency chain validation as a design-time activity rather than an automated build-time gate."                                                |
| Operational              | fail-3-operational | "Ablated Docker images used the same tag as prior full-sandbox builds, so Docker's build cache returned the non-ablated image."                             |
| Scope & Requirements     | fail-4-scope       | "Converted tasks inherit the reasoning structure of their single-repo originals. The second repo adds a lookup step, not a cross-repo reasoning challenge." |
| Scale & Evolution        | fail-5-evolution   | "The team spends increasing effort maintaining existing tasks and decreasing effort creating new ones, never reaching the 55% target."                      |
