# PRD: EnterpriseBench Task Mix Realignment

> **Risk-annotated** — see [premortem_task_mix_realignment.md](premortem_task_mix_realignment.md) for full failure analysis.
> Top 3 risks: (1) 8GB memory limit untested for 3-5 repo tier, (2) SG indexing at 0% with no API stability contract, (3) Ground truth rot at O(tasks x repos) not budgeted.
> See also: [CONVERGENCE_REPORT_TASK_MIX.md](../CONVERGENCE_REPORT_TASK_MIX.md) for debate synthesis.

## Problem Statement

EnterpriseBench's task portfolio is severely misaligned with PRD targets. The benchmark measures cross-repo context retrieval, but 64% of non-calibration tasks are single-repo — over 2.5x the 25% target. Meanwhile, multi-repo tasks (the benchmark's differentiator) cover only 24% vs the 55% target. Worse, 5 of 10 task types have zero multi-repo representation, meaning the benchmark cannot measure cross-repo retrieval for half its task taxonomy.

The good news: only 3 tasks (3%) actually test coding ability instead of retrieval. The problem is not task quality contamination — it's structural underinvestment in multi-repo variants for task types that naturally span repositories in enterprise settings (error provenance, config drift, schema evolution, support mapping, dead code analysis).

## Goals & Non-Goals

### Goals

- Reach PRD target mix: 15% calibration, 25% large-single, 55% multi-repo
- Every task type has at least 2 multi-repo variants
- Diversify ecosystem coverage beyond K8s/gRPC/etcd monoculture
- Validate 4-5 repo sandbox infrastructure with proof-of-concept tasks
- Unblock MCP-mode evaluation by resolving SG indexing debt

### Non-Goals

- Rewriting existing high-quality single-repo tasks (only cut or convert)
- Changing the verification plugin architecture
- Adding new task types beyond the existing 10
- Building synthetic/toy repositories

## Requirements

_Updated after structured convergence debate — see [docs/CONVERGENCE_REPORT_TASK_MIX.md](docs/CONVERGENCE_REPORT_TASK_MIX.md)_

### Must-Have

- Requirement: Fix Sourcegraph indexing — prioritize repos needed by existing + Phase 1 multi-repo tasks
  - Acceptance: `jq '[.[] | select(._indexed == true)] | length' configs/sg_indexing_list.json` returns 131+
  - Note: Quality gate, not phase gate — authoring proceeds in parallel, but no task ships without MCP-mode eval pass

- Requirement: All multi-repo tasks (converted AND net-new) must pass Cross-Repo Necessity Test (CRNT)
  - Acceptance: For each multi-repo task, ablation test (remove one repo) results in agent score ≤60% on checkpoints. At least one checkpoint anchored in each repo. Answer requires facts from 2+ repos not found in any single repo.

- Requirement: Create multi-repo variants for 5 task types currently at zero (config_drift, db_schema_evolution, dead_code_necropsy, error_provenance, support_code_mapping) — minimum 2 per type
  - Acceptance: `find benchmarks/ -name task.toml | xargs grep -l 'stratum.*=.*"dual_repo\|tri_repo\|multi_repo"'` returns files for all 5 types

- Requirement: Cut 3 coding-ability tasks (beam-pipeline-builder-refac-001, ansible-abc-imports-fix-001, aspnetcore-code-review-001)
  - Acceptance: These task directories no longer exist under benchmarks/

- Requirement: Reach ≥45% strict multi-repo (dual_repo + tri_repo + multi_repo, excluding monorepo)
  - Acceptance: Strict multi-repo tasks ≥ 45% of total task count

- Requirement: All new multi-repo tasks use real OSS repos with actual dependency chains
  - Acceptance: Every new task.toml lists repos that exist on GitHub and have a real dependency relationship documented in ground_truth

- Requirement: Replace-before-cut — never retire a single-repo task until its multi-repo replacement passes CRNT and has ≥1 MCP-mode eval run
  - Acceptance: No task type drops below its current task count at any point during realignment

- Requirement: Build 4-repo PoC in Phase 1 week 1 to validate infrastructure feasibility _(promoted from Nice-to-Have per premortem Risk #1)_
  - Acceptance: 4-repo task (containerd/runc/moby + K8s or equivalent) either runs within 8GB/3000s OR the 4-repo tier is killed and PRD targets adjusted
  - Note: This is a 2-day kill-or-proceed gate. If it fails, cap at 3-repo max and redistribute the 20% "3-5 repo" target.

- Requirement: Distinguish infrastructure failures from agent failures in run*task.py *(per premortem Risk #3)\_
  - Acceptance: OOM (exit 137), disk full, and timeout (exit 124) produce `infra_error` status, not `score=0.00 completed`

- Requirement: Implement eager mirror creation + pinned SHA manifest with staleness detection _(per premortem Risk #2, #4)_
  - Acceptance: `repo_versions.json` exists with SHA + last-verified date for all repos; weekly CI flags repos >6 months behind HEAD

- Requirement: Validate CRNT predicts mode discrimination before Phase 2 scaling _(per premortem Risk #5)_
  - Acceptance: 5 pilot tasks run in all 3 modes; CRNT-passing tasks show mean(hybrid) - mean(baseline) > 0 with p<0.1

### Should-Have

- Requirement: Reach ≥55% broad multi-repo (strict + monorepo_cross_package with ≥3 package boundary crossings)
  - Acceptance: Broad multi-repo tasks ≥ 55% of total task count
  - Note: Report both strict and broad percentages — let benchmark consumers choose denominator

- Requirement: At least 40% of new multi-repo tasks use the "investigate" atomic pattern
  - Acceptance: `grep -l 'pattern.*investigate' benchmarks/*/task.toml` returns >= 40% of new task count

- Requirement: New tasks span at least 5 distinct ecosystem chains; no single ecosystem >40% of multi-repo tasks
  - Acceptance: New tasks collectively reference repos from >= 5 technology ecosystems; K8s/gRPC ecosystem ≤40%

- Requirement: Phase 1 pilot — convert 5 tasks to dual-repo and run CRNT ablation to calibrate conversion ceiling
  - Acceptance: 5 pilot conversions tested; pass rate determines Phase 2 conversion count (8-12 total if ≥4/5 pass, ≤8 if <4/5 pass)

- Requirement: Author 15-22 net-new multi-repo tasks across diverse ecosystems
  - Acceptance: Net-new tasks cover ≥3 non-Go ecosystem chains (Python, Java/Kotlin, Rust or cloud-native)

- Requirement: Fix chain_runner.py to accept --mode argument for multi-session tasks
  - Acceptance: `python scripts/chain_runner.py --mode hybrid --help` does not error

### Nice-to-Have

- ~~Requirement: Build 1-2 proof-of-concept tasks with 4+ repos~~ **PROMOTED to Must-Have** per premortem (Risk #1, Score 12). See Must-Have section.

- Requirement: Reduce error_provenance and support_code_mapping single-repo counts by converting to dual-repo
  - Acceptance: These types have >= 30% multi-repo representation

## Design Considerations

### Replace-in-place vs Cut-and-add

Risk analysis strongly favors creating multi-repo replacements BEFORE cutting single-repo tasks. Five task types exist only in large_single stratum — cutting them first creates coverage holes. The recommended sequence: (1) author multi-repo variants, (2) validate they pass verification, (3) retire redundant single-repo versions.

### Monorepo accounting

The 12 monorepo_cross_package tasks (Babel, pnpm, Next.js, rustc) are functionally equivalent to multi-repo — they trace dependencies across package boundaries with the same cognitive challenge. Counting them toward the 55% target reduces the gap from 30 to 18 new tasks. The PRD's own mix gradient includes "10% monorepo cross-package" within the multi-repo 55%, supporting this accounting.

### Ecosystem diversity vs infrastructure safety

Existing multi-repo tasks heavily reuse K8s/gRPC/etcd repos (20+ tasks). New tasks should diversify into Python (Django/Wagtail, Flask/Werkzeug, Celery/Kombu), Java (Spring/Kafka, Jackson/Spring Boot), Rust (tokio/hyper/axum), and cloud-native (Prometheus/Alertmanager/Grafana) ecosystems. However, reusing existing repo mirrors reduces infrastructure risk. Balance: 60% new ecosystems, 40% extensions of existing ones.

### "Investigate" pattern gap

The investigate pattern (symptom in one repo, root cause in another) is the most enterprise-realistic but accounts for <10% of existing multi-repo tasks. Most use "propagate" or "orchestrate." New tasks should weight toward investigate — it's where MCP's cross-repo search provides the most dramatic advantage and where agents are most likely to fail.

### 4-5 repo feasibility

Zero tasks currently use 4+ repos. Docker image sizes are manageable (projected 1.5-2.5GB) but workspace sizes for 4-5 large repos (K8s + Envoy + Istio = 650MB+) may stress the 8GB memory limit. Build a proof-of-concept before committing to the 20% "3-5 repo" tier.

## Proposed Task Additions (32 tasks)

### By type (multi-repo only)

| Task Type              | Count | Key Ecosystems                                                                                       |
| ---------------------- | ----- | ---------------------------------------------------------------------------------------------------- |
| api_contract           | 3     | protobuf/gRPC/Python, FastAPI/httpx, Envoy/Istio/go-control-plane                                    |
| config_drift           | 4     | ArgoCD/argo-helm, Terraform core/provider, Kustomize/ArgoCD/Flux, Prometheus/Thanos                  |
| db_schema_evolution    | 3     | Django/Wagtail, Sentry/Relay, Supabase/PostgREST/GoTrue                                              |
| dead_code_necropsy     | 3     | React/Relay, K8s/client-go, Angular/Components                                                       |
| dependency_graph       | 3     | Jackson/Spring/Boot, OpenSSL/curl/git, boto3/aws-cli/s3transfer                                      |
| error_provenance       | 5     | Docker CLI/moby, Terraform/provider-aws, Grafana/Prometheus, Celery/kombu, requests/urllib3          |
| incident_investigation | 5     | Istio/Envoy, Prometheus/Alertmanager, containerd/runc/moby, Kafka/Connect-JDBC, Flux/helm-controller |
| refactor_orchestration | 3     | Spring Framework/Boot/Kafka, tokio/hyper/axum, Babel/webpack/Next.js                                 |
| support_code_mapping   | 3     | Grafana/Prometheus, Ansible/Jinja, Flask/Werkzeug                                                    |

### Resulting mix (at ~129 tasks, before cuts)

- Calibration: 12 (9%)
- Large single: ~60 (47%)
- Multi-repo: ~57 (44%) — still short of 55%, indicating further single-repo retirement needed

### After retiring ~25 single-repo tasks

- Total: ~104 tasks
- Calibration: 12 (12%)
- Large single: ~35 (34%)
- Multi-repo: ~57 (55%) — target achieved

## Open Questions

1. **SG demo instance capacity** — Can it handle 200+ repo indexes? Need to check quota/rate limits before authoring tasks that depend on MCP mode. _(Unresolved — must test empirically)_
2. ~~**Monorepo accounting decision**~~ — **RESOLVED**: Report dual-track (strict multi-repo and broad multi-repo). Monorepo tasks count toward "broad" if they traverse ≥3 package boundaries with separate maintainers/APIs.
3. **Small repo policy** — Some proposed pairs (Flask/Werkzeug ~50K LoC) are smaller individually. Debate leaned toward "combination compensates" but no hard criterion set. _(Partially resolved)_
4. ~~**Authoring velocity**~~ — **RESOLVED**: Phased approach. Phase 1: 5 pilot conversions + SG indexing (concurrent). Phase 2: 8-12 total conversions + 15-22 net-new, scope gated by Phase 1 data. Total ~120-180 hours.
5. **4-repo proof-of-concept** — Which ecosystem chain should be the first 4+ repo test? containerd/runc/moby + K8s is the most natural candidate. _(Unresolved)_
6. **CRNT ablation threshold** — Debate settled on ≤60% as compromise between Position A's 50% and Position C's 70%. Needs empirical validation. _(New from convergence)_
7. **Ecosystem discrimination data** — Do Python/Java ecosystem tasks discriminate between agents as well as Go tasks? Unknown until Phase 2 tasks are built. _(New from convergence)_

## Research Provenance

Three independent research lenses contributed:

| Lens                        | Key Contribution                                                            | Confidence  |
| --------------------------- | --------------------------------------------------------------------------- | ----------- |
| Task Audit & Classification | Classified all 100 tasks; only 3 CUT candidates; 6/10 types at 0 multi-repo | High        |
| Multi-Repo Task Design      | 32 concrete task proposals across 7 new ecosystem chains                    | Medium-High |
| Feasibility & Risk          | SG indexing blocker, Docker sizing, chain_runner bug, authoring cost        | Medium-High |

**Convergence**: All three agreed on the 3 CUT candidates, the 5-type multi-repo gap, and the SG indexing blocker.

**Divergence**: Ecosystem diversity (new chains vs reuse existing) and cut timing (before vs after replacements ready). Risk agent's "replace-in-place" argument prevailed.
