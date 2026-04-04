# Convergence Report: Phase 1 Dual-Repo Pilot Validation Strategy

> Produced by structured debate (3 positions, 2 rounds) on 2026-04-03.

## 1. Resolved Points

**Per-checkpoint `repo_deps` is a must-have schema change (unanimous).** All three positions agreed that the current CRNT validator is a rubber stamp and that per-checkpoint repo dependency annotations are the minimum viable fix. This was never contested across two rounds. **Decision: implement `repo_deps` before any conversion work begins.**

**The 4-repo task should be deferred from the pilot scope (Position C, conceded by A).** The 4-repo task introduces orthogonal problems (CRI compatibility, ground truth fragility at 4-repo scale, Go sandbox template validation) that confound the pilot's core question: "does CRNT discriminate?" The 4-repo sandbox is already validated (192 MiB, 29s build). Authoring the actual task can proceed independently after the pilot validates the CRNT protocol. **Decision: defer 4-repo task authoring to post-pilot. Keep the validated Dockerfile.**

**Cognitive ablation should run on a subset, not all tasks (emerged compromise).** Position B's argument that static analysis can't catch training-prior leakage was compelling — Position A conceded this is a real blind spot. But Position C's budget math showed that running full cognitive ablation on fewer tasks gives more signal per dollar than thin ablation across all tasks. **Decision: run cognitive ablation on 2 of the pilot tasks (the "near-free" conversion and the "novel" conversion — representing the easiest and hardest CRNT challenges).**

## 2. Refined Trade-offs

### Pilot scope: 3 tasks vs 5 tasks

**Tension**: Position C argued 3 tasks with full depth > 5 tasks with thin validation. Position A wanted 5 for ecosystem diversity. Position B wanted all 5 with cognitive ablation.

**Resolution**: **4 tasks** — a compromise. Three dual-repo conversions covering the difficulty spectrum (near-free, structural, novel) plus one additional conversion for ecosystem diversity. The 4th task gets static CRNT only (no cognitive ablation) since the protocol will already be validated on the first 3.

- Task 1: `incident-investigation-004` (moby+containerd) — near-free, cognitive ablation YES
- Task 2: `err-provenance-02` (K8s+knftables) — vendored dep split, static CRNT only
- Task 3: `support-mapping-004` (Grafana+Alertmanager) — novel chain, cognitive ablation YES
- Task 4: `config-drift-004` (ArgoCD+upstream) — ecosystem diversity, static CRNT only

**What would tip the balance**: If cognitive ablation on tasks 1 and 3 reveals that training-prior leakage is common (>50% of ablated checkpoints score above threshold), expand cognitive ablation to all 4 tasks before proceeding to Phase 2.

### Ablation threshold: 30% vs 60%

**Tension**: The PRD specifies ≤60% aggregate score for CRNT pass. Position B argued for ≤30% on checkpoints specifically anchored to the removed repo (stricter). Position A accepted 60% as sufficient.

**Resolution**: **Two thresholds**. Static CRNT uses ≤60% aggregate (existing PRD criterion). Cognitive ablation uses ≤30% on removed-repo-anchored checkpoints (stricter, catches prior leakage). If an agent scores 40% on repo-B checkpoints without repo B present, the task is suspect even if aggregate stays under 60%.

### Repetitions per condition

**Tension**: PRD suggests 3 reps. Position C argued for 5 to get variance estimates.

**Resolution**: **3 reps for cognitive ablation** (expensive, 2 tasks × 2 ablations × 3 reps = 12 runs), **3 reps for 3-mode evaluation** (4 tasks × 3 modes × 3 reps = 36 runs). Total: 48 runs. Within the $150-375 budget. If variance is high, add 2 more reps on the noisiest tasks before Phase 2.

## 3. Emerged Positions

**"Tiered validation" — the compromise nobody started with.** Static CRNT gates ALL tasks (zero cost). Cognitive ablation validates a SUBSET (the hardest and easiest conversions). This emerged from the debate as all three positions shifted: A accepted cognitive ablation is valuable; B accepted it doesn't need to run on every task; C accepted 4 tasks is viable if depth is maintained where it matters. The tier structure is:

| Tier               | Gate                                          | Applies to                        | Cost    |
| ------------------ | --------------------------------------------- | --------------------------------- | ------- |
| Static CRNT        | Per-checkpoint repo_deps, max_ablated ≤ 60%   | All 4 pilot tasks                 | 0 runs  |
| Cognitive ablation | Agent score ≤ 30% on removed-repo checkpoints | 2 pilot tasks (easiest + hardest) | 12 runs |
| 3-mode evaluation  | Report mean(hybrid) - mean(baseline)          | All 4 pilot tasks                 | 36 runs |

**"Conversion difficulty spectrum" as a reusable framework.** Position C's framing of near-free/structural/novel as conversion categories was adopted by all. This becomes the classification system for Phase 2 conversions: estimate difficulty tier before authoring, which determines validation depth.

## 4. Strongest Arguments (preserved)

**Position A**: "Per-checkpoint repo_deps forces task authors to think carefully about which checkpoints depend on which repos. This design-time discipline is more valuable than post-hoc testing because it prevents bad tasks from being authored in the first place." — This is the argument that won the "static CRNT first" framing even as cognitive ablation was added.

**Position B**: "The whole point of EB is measuring context retrieval; if the agent can retrieve the answer from training memory instead of the repo, the task is broken. Static analysis cannot detect this by definition." — This is the argument that made cognitive ablation non-negotiable for at least a subset of tasks.

**Position C**: "Budget math: 3 tasks × full depth = same 75 runs, far more signal per task." — This reframing from "how many tasks?" to "how much signal per task?" shifted the entire debate toward the tiered compromise.

## 5. Recommended Path

1. **Week 1**: Implement `repo_deps` schema change + CRNT validator update. Zero agent runs needed.
2. **Week 1-2**: Convert 4 tasks (parallel authoring). Each must pass static CRNT before proceeding.
3. **Week 2**: Run cognitive ablation on tasks 1 and 3 (12 runs). If either fails (agent scores >30% on removed-repo checkpoints), investigate and redesign before continuing.
4. **Week 2-3**: Run 3-mode evaluation on all 4 tasks (36 runs). Report statistical results.
5. **Post-pilot**: If protocol validated, proceed to Phase 2. Author 4-repo task using validated Dockerfile. Scale cognitive ablation based on pilot failure rate.

**Revisit triggers**:

- If cognitive ablation reveals >50% prior-leakage rate → expand ablation to all tasks, reconsider task design approach
- If mode discrimination shows p>0.3 → investigate whether tasks are too easy, not whether protocol is broken
- If 3 reps show high variance (CV>0.5) → add 2 reps before Phase 2 conclusions

## 6. Debate Highlights

**Position A (Static CRNT First)**: Strongest contribution was establishing that design-time discipline (forcing authors to annotate repo_deps) prevents bad tasks upstream, reducing reliance on expensive downstream validation.

**Position B (Cognitive Ablation Required)**: Strongest contribution was the irreducible argument that static analysis cannot detect training-prior leakage — the one failure mode that would silently invalidate the entire benchmark.

**Position C (Minimal Viable Pilot)**: Strongest contribution was the budget math reframe and the conversion difficulty spectrum, both of which structured the final compromise.
