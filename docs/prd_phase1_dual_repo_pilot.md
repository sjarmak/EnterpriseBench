# PRD: Phase 1 Dual-Repo Pilot & First 4-Repo Task

> **Risk-annotated** — see Research Provenance for failure analysis from 3 independent research lenses.
> **Converged** — refined via structured debate (3 positions, 2 rounds). See [CONVERGENCE_REPORT_PHASE1_PILOT.md](CONVERGENCE_REPORT_PHASE1_PILOT.md) for full debate synthesis.
> **Premortem** — 5 failure lenses applied. See [premortem_phase1_dual_repo_pilot.md](premortem_phase1_dual_repo_pilot.md) for full risk registry.
> Top 3 risks: (1) repo_deps annotations disconnected from verifier behavior (Score 12), (2) required_files paths unverified at pinned SHAs (Score 12), (3) Docker tag collisions and output overwrites in ablation runs (Score 12). All have concrete mitigations — see P0/P1 items below.

## Problem Statement

EnterpriseBench's CRNT (Cross-Repo Necessity Test) validator is structurally incapable of catching "decorative" multi-repo tasks. The `map_checkpoints_to_repos` heuristic anchors all checkpoints to all repos when `ground_truth.required_files` reference both repos, meaning any well-formed dual-repo task trivially passes regardless of whether the second repo is genuinely necessary. This undermines the integrity of the entire multi-repo tier.

Meanwhile, the Phase 1 pilot (convert 5 single-repo tasks to dual-repo, author first 4-repo task) cannot proceed without a functioning quality gate. The "zero multi-repo" gap for 5 task types has been closed since the PRD was written, shifting pilot goals from coverage to **quality and ecosystem diversity**. The pilot must prove that converted tasks genuinely require cross-repo reasoning, not just reference files in two repos.

## Goals & Non-Goals

### Goals

- Fix CRNT to have real discriminative power (per-checkpoint repo anchoring)
- Convert 4 single-repo tasks to dual-repo with validated CRNT pass _(reduced from 5 per convergence — depth over breadth)_
- Run 3-mode evaluation (baseline/mcp_only/hybrid) on pilot tasks
- Establish tiered validation runbook: static CRNT (all tasks) + cognitive ablation (subset)
- Validate conversion difficulty spectrum (near-free / structural / novel) as reusable framework

### Non-Goals

- Converting all single-repo tasks (this is a 4-task pilot)
- Adding new task types
- Changing the verification plugin architecture
- Building new sandbox templates beyond the validated go_4repo_poc
- Reaching PRD mix targets (that's Phase 2)
- Authoring the 4-repo task _(deferred from pilot per convergence — orthogonal to CRNT validation, sandbox already proven)_

## Requirements

### Must-Have

- Requirement: Add `repo_deps` array field to checkpoint definitions in task schema
  - Acceptance: `jq '.properties.checkpoints.items.properties.repo_deps' schemas/task.schema.json` returns a valid array-of-strings schema definition

- Requirement: Update CRNT validator to use per-checkpoint repo_deps when present
  - Acceptance: For a dual-repo task with checkpoint A (repo_deps=["repo1"]) and checkpoint B (repo_deps=["repo2"]), removing repo1 yields max_score = weight(B)/(weight(A)+weight(B)), not 0.0. Run: `python scripts/validation/crnt_validator.py benchmarks/incident_response/incident-investigation-dual-*` produces differentiated per-repo ablation scores

- Requirement: Convert 4 single-repo tasks to dual-repo, each passing static CRNT with max_ablated_score ≤ 60%
  - Acceptance: `python scripts/validation/crnt_validator.py <task_dir>` returns `pass: true` for all 4 converted tasks, AND at least one checkpoint is anchored to each repo individually
  - Note: Reduced from 5 per convergence debate — depth over breadth

- Requirement: Pilot conversion candidates (converged priority order):
  1. `incident-investigation-004` (moby→moby+containerd) — near-free, **cognitive ablation YES**
  2. `err-provenance-02` (K8s nftables→K8s+knftables) — vendored dep split, static CRNT only
  3. `support-mapping-004` (Grafana alerts→Grafana+Alertmanager) — novel chain, **cognitive ablation YES**
  4. `config-drift-004` (ArgoCD redis-ha→ArgoCD+upstream chart) — ecosystem diversity, static CRNT only
  - Acceptance: All 4 converted tasks exist under `benchmarks/`, each with `difficulty_stratum = "dual_repo"` and `tool_access` configured for all 3 modes

- Requirement: Run cognitive ablation on tasks 1 and 3 (easiest + hardest conversions)
  - Acceptance: Agent scores ≤ 30% on checkpoints anchored to the removed repo. 3 reps per ablation condition. Results logged to `results/crnt_ablation/` with per-checkpoint scores. Total: 12 runs.
  - Note: Stricter threshold (30% vs 60%) catches training-prior leakage per convergence

- Requirement: Run all 4 pilot tasks in all 3 modes (full, non-ablated), 3 reps each
  - Acceptance: Results in `results/phase1_pilot/`, with per-task per-mode scores. Statistical test (paired) on mean(hybrid) vs mean(baseline) reported. Total: 36 runs.

- Requirement: Total pilot budget ≤ 48 agent runs (~$100-240)
  - Acceptance: Run log in `results/phase1_pilot/run_manifest.json` shows ≤ 48 entries

### Should-Have

- Requirement: Implement cognitive ablation script for reuse in Phase 2
  - Acceptance: Script `scripts/validation/run_crnt_ablation.sh <task_dir>` builds ablated Docker image, runs agent, reports per-checkpoint scores. Used by must-have ablation runs above.

- Requirement: Add `required_files` existence verification to staleness checker
  - Acceptance: `python scripts/infra/check_repo_staleness.py --verify-files` reports any `required_files` paths that don't exist at pinned revision

- Requirement: Author 4-repo incident_investigation task post-pilot using validated go_4repo_poc sandbox
  - Acceptance: Task directory at `benchmarks/incident_response/incident-investigation-quad-containerd-001/`, passes static CRNT, all 4 repos contribute unique checkpoints
  - Note: Deferred from must-have per convergence — orthogonal to CRNT protocol validation. CRI/seccomp scenario recommended (kubelet→containerd→runc→moby seccomp profile chain).

### Must-Have (from premortem — P0)

- Requirement: Pin knftables SHA from K8s v1.33.0-alpha.2 `vendor/modules.txt`; verify dandydeveloper/charts is still accessible
  - Acceptance: knftables entry in `configs/repo_versions.json` with SHA matching vendored version; dandydeveloper/charts cloned or mirrored
  - Risk: Integration failure #2 — unpinned repos break ground truth silently

- Requirement: Add rep index and ablation variant to output paths and Docker image tags
  - Acceptance: Output layout is `results/runs/<task_id>/<mode>/rep<N>/`; ablation images tagged `eb-{task_id}-ablate-{excluded_repo}`
  - Risk: Operational failure #3 — concurrent runs overwrite results

### Should-Have (from premortem — P1)

- Requirement: Implement `--verify-files` on `check_repo_staleness.py` and run in CI on PRs touching `benchmarks/` or `configs/`
  - Acceptance: CI step clones each referenced repo at pinned SHA and asserts every `required_files` path exists
  - Risk: Integration failure #2, Evolution failure #5

- Requirement: Write `run_pilot.py` batch orchestrator with rep tracking, account assignment, and retry
  - Acceptance: `python scripts/orchestration/run_pilot.py --manifest pilot_manifest.json` executes all 48 runs with parallel account scheduling and produces summary CSV
  - Risk: Operational failure #3

- Requirement: Add verifier grounding test — run each verifier in ablated sandbox, confirm it fails on removed-repo checkpoints
  - Acceptance: `scripts/validation/verify_grounding.py <task_dir>` returns pass only if verifiers fail when their declared repo is absent
  - Risk: Technical failure #1 — repo_deps annotations disconnected from verifier behavior

- Requirement: Add mode discrimination gate: at least 2/4 tasks show mean(hybrid) > mean(baseline) with Cohen's d > 0.5
  - Acceptance: Phase 2 scaling blocked until this gate passes; if conversions fail but net-new tasks pass, pivot to net-new only
  - Risk: Scope failure #4 — conversions pass CRNT but don't discriminate

### Nice-to-Have

- Requirement: Power analysis for mode discrimination test to determine if 4 tasks x 3 reps is sufficient for p<0.1
  - Acceptance: Analysis document estimating required effect size and sample size, with recommendation for Phase 2 run count

- Requirement: Ecosystem bootstrapping spike — 1 dual-repo task per target ecosystem before Phase 2 commitment
  - Acceptance: Measured discovery hours for Python/Django, Java/Spring, Rust/tokio; per-ecosystem quotas set for Phase 2
  - Risk: Evolution failure #5 — ecosystem discovery cost unknown

- Requirement: Ground truth repair automation via `git log --follow` rename tracking
  - Acceptance: `check_repo_staleness.py --auto-repair` produces patches for simple file renames
  - Risk: Evolution failure #5 — maintenance outpaces authoring

## Design Considerations

### CRNT: Tiered Validation (RESOLVED per convergence)

**Decision**: Two-tier approach. Static CRNT (per-checkpoint repo_deps, ≤60% aggregate) gates ALL tasks at zero cost. Cognitive ablation (≤30% on removed-repo checkpoints) validates a SUBSET — the easiest and hardest conversions — to catch training-prior leakage that static analysis cannot detect. If cognitive ablation reveals >50% prior-leakage rate, expand to all tasks before Phase 2.

### Conversion Strategy: Vendored Dependencies

The highest-fidelity conversions are tasks that already trace into vendored dependencies (e.g., `err-provenance-02` traces into `vendor/sigs.k8s.io/knftables/`). Splitting the vendored code to its real upstream repo is low-effort and high-validity because the cross-repo dependency is already structurally present — it's just artificially contained. This pattern should be preferred over designing novel cross-repo scenarios.

### 4-Repo Ground Truth Fragility

Ground truth maintenance scales with repo count. The 4-repo task pins files across 4 repos (kubernetes, containerd, runc, moby). If any repo refactors the relevant path, ground truth breaks. Mitigation: choose stable, well-established code paths (CRI interface in kubelet, seccomp profile handling) that haven't changed significantly across versions. Add version-specific `required_files` comments noting the pinned revision.

### Statistical Power Concern (RESOLVED per convergence)

4 tasks × 3 reps is unlikely to reach p<0.1 for mode discrimination. **Decision**: the pilot's primary goal is protocol validation, not statistical proof. Report results regardless. If variance is high (CV>0.5), add 2 more reps on noisiest tasks before Phase 2 conclusions. Phase 2 scales to sufficient sample size.

### Ecosystem Concentration

Adding the 4-repo containerd/runc/moby/kubernetes task deepens K8s ecosystem concentration (already 21% of multi-repo tasks). Dual-repo conversions should deliberately diversify: Grafana+Alertmanager (observability), React+Next.js (frontend), ArgoCD+upstream (GitOps). Target ≤ 35% K8s ecosystem after pilot.

## Open Questions

1. **knftables repo viability**: ~5K LoC, may violate enterprise-scale policy. Does "combination compensates" clause apply when paired with kubernetes?
2. ~~**CRI API compatibility**~~: Deferred — 4-repo task moved to post-pilot.
3. **MCP-mode ablation**: Removing a repo from Docker has no effect in mcp_only mode (agent searches remotely). Need SG mirror exclusion for MCP ablation — is this supported?
4. **CRNT false positive rate**: Has any existing dual-repo task ever failed CRNT? If zero, the current validator has been a rubber stamp since inception. _(Run the updated validator on existing tasks to answer this.)_
5. ~~**Ablation run cost**~~: **RESOLVED** per convergence. 48 total runs (~$100-240). Cognitive ablation on 2 tasks (12 runs) + 3-mode evaluation on 4 tasks (36 runs).

## Research Provenance

Three independent research lenses contributed:

| Lens                                | Key Contribution                                                                                                                                                       | Confidence  |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| Task Selection & Dependency Mapping | Identified vendored-dep splitting as fastest conversion path; confirmed zero-multi-repo gap already closed; ranked 5 conversion candidates with real dependency chains | Medium-High |
| CRNT Protocol & Ablation Design     | Exposed CRNT validator as rubber stamp; designed two-layer ablation protocol with cost model (75 runs, $150-375); flagged statistical power limitation                 | Medium-High |
| Failure Modes & 4-Repo Design       | Proposed CRI/seccomp 4-repo scenario with specific file paths; found incident-investigation-004 as near-free conversion; identified ground truth fragility scaling     | Medium-High |

**Convergence**: All three agents independently identified the CRNT validator's lack of discriminative power as the #1 structural risk. All agreed per-checkpoint repo anchoring is the critical schema change.

**Divergence**: Static-only vs static+cognitive ablation (cost vs thoroughness). OOM vs seccomp scenario for 4-repo task (generic vs specific). Whether 5 tasks is sufficient sample size for mode discrimination.

**Top 3 Risks**:

1. **CRNT rubber stamp** (Score: Critical) — validator trivially passes all dual-repo tasks. Fix: per-checkpoint repo_deps field. Unfixed: every conversion is unvalidated.
2. **Statistical underpowerment** (Score: High) — 5 tasks x 3 reps unlikely to reach p<0.1. Mitigation: treat pilot as protocol validation, not statistical proof. Phase 2 scales.
3. **Ground truth fragility at 4-repo scale** (Score: Medium) — 4 repos x version bumps = quadratic maintenance. Mitigation: pin to stable interfaces, add file existence verification to staleness checker.
