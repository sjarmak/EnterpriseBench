# CSB → EnterpriseBench Taxonomy Mapping

Generated from direct analysis of `~/CodeScaleBench/benchmarks/CANONICAL.json` (275 tasks)
and `~/CodeScaleBench/configs/task_type_taxonomy.json`.

---

## Mapping Rules

| CSB Suite | Task Count | EB Workflow Cluster | CSB Task Type | Rationale |
|-----------|-----------|---------------------|---------------|-----------|
| csb_org_compliance | 13 | security_operations | quality | Compliance audits (access logging, authorization events, CSP enforcement) — agent assesses code against security policies |
| csb_org_crossorg | 12 | customer_escalation | comprehension | Cross-org service discovery (gRPC service definitions, WebIDL/DOM bindings, shared style systems) — producing knowledge artifacts about external integration boundaries |
| csb_org_crossrepo | 11 | dependency_management | comprehension | Cross-repo dependency traces (GCC/LLVM pass registration chains, IR type chains) — blast-radius analysis and dependency chain understanding |
| csb_org_crossrepo_tracing | 11 | dependency_management | comprehension | Stack trace symbol resolution and config tracing across repos (rest.Config, ASan tracing across LLVM vs GCC) — how a shared library change propagates |
| csb_org_domain | 11 | feature_delivery | comprehension | Domain lineage traces (Kubernetes watch event path, LLVM optimization pipeline, Servo CSS integration) — architecture comprehension required before writing features |
| csb_org_incident | 13 | incident_response | quality | Incident debugging (Envoy connection pool exhaustion, Loki retry/timeout, etcd DialTimeout across K8s) — explicit incident triage category |
| csb_org_migration | 25 | technical_debt | implementation | Migration inventories (Envoy v2→v3 API, LLVM legacy→new pass manager, Kafka RecordAccumulator rename) — deprecation tracking and large-scale API removal |
| csb_org_onboarding | 11 | customer_escalation | comprehension | Onboarding comprehension (LLVM code-gen pipeline, SpiderMonkey JIT, Chromium multi-process arch) — knowledge artifacts for orienting new engineers or customer support |
| csb_org_org | 11 | feature_delivery | implementation | Agentic correctness tasks (implement Kafka consumer, K8s custom resource client, Envoy HTTP filter following ecosystem patterns) — feature implementation with codebase-pattern fidelity |
| csb_org_platform | 13 | platform_engineering | quality | Platform knowledge (deployment pattern discovery, CODEOWNERS infrastructure, deprecated struct fields audit) — CI/CD and infrastructure configuration understanding |
| csb_org_security | 13 | security_operations | quality | Vulnerability remediation (missing auth middleware, LLVM stack protection, Firefox NSS TLS audit) — security audit and hardening |
| csb_sdlc_debug | 5 | incident_response | quality | Fault localization (Linux ACPI backlight, HDA Intel suspend, iwlwifi PCI subdevice entries) — low-level bug diagnosis matching incident triage |
| csb_sdlc_design | 8 | feature_delivery | comprehension | Architecture design (Camel EIP routing, Django ORM query pipeline, Elasticsearch shard allocation design) — design work that precedes implementation |
| csb_sdlc_document | 4 | feature_delivery | comprehension | Documentation generation (Envoy migration guide, GDScript VM bytecode docs, gRPC C++ Channel API docs) — producing deliverables as part of a feature or release |
| csb_sdlc_feature | 23 | feature_delivery | implementation | Feature implementation (HyperLogLog in BusTub, Camel FIX protocol component, Cilium PolicyAuditLogger) — canonical feature delivery tasks |
| csb_sdlc_fix | 18 | incident_response | implementation | Bug investigation and fixes (Django select_for_update crash, element-web RoomHeaderButtons crash) — root-cause-then-fix pattern matches incident_response remediation |
| csb_sdlc_refactor | 16 | technical_debt | implementation | Code refactoring (Beam PipelineOptions Builder pattern, Cilium EndpointRegenerator extraction, Django RequestFactory rename) — paying down structural debt |
| csb_sdlc_secure | 5 | security_operations | quality | Security hardening and CVE triage (Ceph RGW S3 auth, curl SOCKS5 CVE, K8s RBAC flow analysis) — security_operations quality tasks |
| csb_sdlc_test | 12 | feature_delivery | quality | Test writing and code review (ASP.NET Core PR review, Bazel Starlark unit tests, cal.com code review) — testing is a delivery gate, not standalone technical debt |
| csb_sdlc_understand | 9 | customer_escalation | comprehension | Codebase orientation and architectural explanation (Argo CD sync strategies, Cilium eBPF node isolation, Cilium project structure) — knowledge-transfer artifacts useful in escalation contexts |

### Non-CSB Legacy Tasks (31 tasks in CANONICAL.json without csb_ origin_suite)

These tasks predate the CSB suite taxonomy and carry simplified subcategory labels.
They are included in the distribution totals below using the same mapping logic.

| Subcategory | Count | EB Cluster |
|-------------|-------|-----------|
| debug | 8 | incident_response |
| document | 7 | feature_delivery |
| fix | 1 | incident_response |
| refactor | 2 | technical_debt |
| security | 8 | security_operations |
| understand | 5 | customer_escalation |

---

## Distribution Analysis

| EB Cluster | CSB Tasks | Legacy Tasks | Total | % of 275 | Source CSB Suites |
|------------|-----------|-------------|-------|----------|-------------------|
| dependency_management | 22 | 0 | 22 | 8.0% | csb_org_crossrepo, csb_org_crossrepo_tracing |
| incident_response | 36 | 9 | 45 | 16.4% | csb_org_incident, csb_sdlc_debug, csb_sdlc_fix |
| platform_engineering | 13 | 0 | 13 | 4.7% | csb_org_platform |
| security_operations | 31 | 8 | 39 | 14.2% | csb_org_compliance, csb_org_security, csb_sdlc_secure |
| customer_escalation | 32 | 5 | 37 | 13.5% | csb_org_crossorg, csb_org_onboarding, csb_sdlc_understand |
| feature_delivery | 69 | 7 | 76 | 27.6% | csb_org_domain, csb_org_org, csb_sdlc_design, csb_sdlc_document, csb_sdlc_feature, csb_sdlc_test |
| technical_debt | 41 | 2 | 43 | 15.6% | csb_org_migration, csb_sdlc_refactor |
| **Total** | **244** | **31** | **275** | **100%** | |

---

## Ambiguous Mappings

Five suites had plausible mappings to multiple EB clusters. Decisions and rationale:

### 1. csb_org_migration → technical_debt (not dependency_management)
Tasks are "migration inventories" — cataloguing all call sites of a deprecated API before removal.
This is deprecation propagation work (technical_debt) rather than upgrading a dependency version
(dependency_management). The dependency_management cluster is for tasks where the change originates
in a dependency; migration tasks are driven by internal API owners removing legacy code.

### 2. csb_org_crossrepo + csb_org_crossrepo_tracing → dependency_management (not incident_response)
Both suites trace dependency chains and compute blast radius. While the same skill (cross-repo
tracing) is used in incidents, these tasks have no incident trigger — they are proactive dependency
analysis. They map more cleanly to dependency_management's "propagating changes across dependency
chains" than to incident triage.

### 3. csb_sdlc_fix → incident_response (not feature_delivery)
Fix tasks involve root-cause analysis followed by a targeted change — the same pattern as incident
remediation. They are distinguished from feature_delivery tasks (csb_sdlc_feature, csb_org_org)
which start from a PRD or design doc. The `bug_investigation` and `bug_fix` categories in CSB
metadata confirm the incident framing.

### 4. csb_org_domain → feature_delivery (not customer_escalation)
"Domain lineage" tasks trace execution paths (Kubernetes watch delivery, LLVM optimization
propagation) to build architectural understanding. This comprehension serves feature design
(knowing how the system works before adding to it) more directly than customer escalation
(which focuses on reproducing reported failures). Contrast with csb_org_onboarding, which
explicitly produces orientation artifacts for new team members.

### 5. csb_org_onboarding → customer_escalation (not feature_delivery)
Onboarding comprehension tasks ask the agent to explain complex subsystems (LLVM code-gen pipeline,
SpiderMonkey JIT, Chromium multi-process arch) as if orienting a new engineer. The output is a
knowledge artifact. This maps to customer_escalation's "KB article creation" scenario more than to
feature_delivery's "PRD-to-implementation" workflow. Note the overlap with csb_sdlc_understand,
which maps the same way.

---

## Gap Analysis

| EB Cluster | % | Status |
|------------|---|--------|
| platform_engineering | 4.7% | **Below 5% threshold** — Only csb_org_platform feeds this cluster; no SDLC analogue exists in CSB. New tasks should be seeded here during Phase 1 task authoring. |
| dependency_management | 8.0% | Slightly thin. csb_org_migration (25 tasks) was a natural candidate but maps better to technical_debt. Consider adding cross-language dependency upgrade tasks. |
| feature_delivery | 27.6% | Largest cluster. Within acceptable range (<30%), but watch as new tasks are authored — this cluster naturally attracts miscategorized comprehension tasks. |
| incident_response | 16.4% | Healthy. The fix + debug + org_incident combination provides good coverage. |
| security_operations | 14.2% | Healthy. Three distinct CSB suites (compliance, security, secure) with distinct perspectives. |
| technical_debt | 15.6% | Healthy. Migration inventory (25 tasks) and refactoring (18) give strong coverage. |
| customer_escalation | 13.5% | Adequate. Comprehension tasks dominate; needs more implementation-heavy escalation scenarios in Phase 1. |

### Recommended Actions
1. **platform_engineering gap**: Author 5–8 new tasks targeting CI/CD pipeline debugging,
   IaC drift detection, and deployment orchestration before the first benchmark run.
2. **customer_escalation quality**: Current tasks are comprehension-only; add tasks requiring
   reproduction scripts and KB article authoring (artifact type: `kb_article`).
3. **feature_delivery bloat risk**: Ensure csb_sdlc_design and csb_sdlc_document tasks are
   genuinely delivery-gated (have implementation checkpoints), not pure comprehension.
