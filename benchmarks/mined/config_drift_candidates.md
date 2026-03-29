# Configuration Drift Forensics Candidates

Mined candidates for `config-drift-*` tasks. Each candidate represents a multi-layer
configuration hierarchy where values diverge across layers (Helm value overrides,
template helpers, subchart dependencies, or multi-environment configs).

**Go/no-go criteria:** >= 5 candidates with >= 3-layer config hierarchy.

---

## bitnami/charts (4 candidates)

### Candidate 1: Spring Cloud Dataflow — External RabbitMQ Configuration Inconsistencies

- **PR:** [#24493](https://github.com/bitnami/charts/pull/24493) — "Address external RabbitMQ inconsistencies"
- **Merged:** 2024-03-18
- **Chart:** `bitnami/spring-cloud-dataflow`
- **Files changed (7):** `Chart.yaml`, `README.md`, `templates/NOTES.txt`, `templates/_helpers.tpl`, `templates/externalrabbitmq-secrets.yaml`, `templates/skipper/configmap.yaml`, `values.yaml`
- **Config layers (4):**
  1. `values.yaml` — defines `externalRabbitmq.host`, `externalRabbitmq.port`, `externalRabbitmq.password`, `externalRabbitmq.existingSecret`
  2. `templates/_helpers.tpl` — helper templates resolving RabbitMQ connection parameters from values
  3. `templates/externalrabbitmq-secrets.yaml` — secret template consuming password config
  4. `templates/skipper/configmap.yaml` — Spring Cloud Skipper config consuming RabbitMQ connection info
- **Drift pattern:** External RabbitMQ secret key parameter was missing from values.yaml, causing templates to reference undefined keys. Password and erlangCookie were required even when using external RabbitMQ with existing secrets. Inconsistency between how external DB and external RabbitMQ were configured.
- **Difficulty:** Hard — 4-layer override chain (values → helpers → secrets → configmap), subchart interaction with external service config
- **Why interesting:** Agent must trace the config value flow from `values.yaml` through Helm template helpers to multiple consuming templates, understanding that the external RabbitMQ configuration path diverges from the embedded subchart path and identifying where the inconsistencies break the override chain.

### Candidate 2: Consul — serfLAN/serfWAN Port Mismatch in Headless Service

- **PR:** [#33114](https://github.com/bitnami/charts/pull/33114) — "Fix mismatched serfLAN and serfWAN ports in consul-headless-service"
- **Merged:** 2025-04-30
- **Chart:** `bitnami/consul`
- **Files changed (3):** `CHANGELOG.md`, `Chart.yaml`, `templates/consul-headless-service.yaml`
- **Config layers (3):**
  1. `values.yaml` — defines `containerPorts.serfLAN` and `containerPorts.serfWAN` values
  2. `templates/statefulset.yaml` — uses `containerPorts.serfLAN` and `containerPorts.serfWAN` for container ports
  3. `templates/consul-headless-service.yaml` — should map ports consistently but used `serfWAN` value for `serflan-udp` port name
- **Drift pattern:** In v11.1.0, serfWAN ports were added but the headless service template incorrectly used `{{ .Values.containerPorts.serfWAN }}` for the `serflan-udp` port instead of `{{ .Values.containerPorts.serfLAN }}`. This created a mismatch between the values defined and the service template consuming them, breaking Helm upgrades from 11.0.x to 11.1.x.
- **Difficulty:** Medium — 3-layer (values → statefulset → headless-service), clear port mapping drift
- **Why interesting:** Demonstrates how a new feature addition (serfWAN) can introduce cross-template drift when copy-paste creates incorrect value references. Agent must trace port value flow from values.yaml through both the statefulset and headless service templates to find the inconsistency.

### Candidate 3: Redis — Password Generation Drift Across Template Includes

- **PR:** [#36231](https://github.com/bitnami/charts/pull/36231) — "Fix service binding password mismatch"
- **Merged:** 2025-09-12
- **Chart:** `bitnami/redis`
- **Files changed (3):** `CHANGELOG.md`, `Chart.yaml`, `templates/_helpers.tpl`
- **Config layers (4):**
  1. `values.yaml` — defines `auth.password`, `global.redis.password`, `serviceBindings.enabled`
  2. `templates/_helpers.tpl` — `redis.password` helper template that generates or resolves password
  3. Multiple consuming templates — `templates/secret.yaml`, `templates/health-configmap.yaml`, `templates/master/application.yaml` all call `{{ include "redis.password" }}`
  4. `ServiceBinding` resource — consumes the password for external service binding
- **Drift pattern:** The `redis.password` helper was called via `{{ include }}` in multiple templates. Since Helm's `include` re-evaluates the template each time, when no password was explicitly set, each invocation generated a DIFFERENT random password. This caused the secret, configmap, and service binding to contain different passwords — a silent config drift that only manifested at runtime.
- **Difficulty:** Hard — 4-layer (values → helper → multiple templates → service binding), requires understanding Helm template evaluation semantics
- **Why interesting:** This is a subtle drift caused by Helm's `include` evaluation model rather than a simple typo. Agent must understand that Helm re-evaluates `include` calls independently, making the password helper non-idempotent when generating random values. The fix stores the generated value back into `.Values` for reuse.

### Candidate 4: APISIX — Context Variable Inconsistency in DataPlane Templates

- **PR:** [#36252](https://github.com/bitnami/charts/pull/36252) — "Fixed bug caused by inconsistent usage of context with dataPlane.extraEnvVars"
- **Merged:** 2025-10-08
- **Chart:** `bitnami/apisix`
- **Files changed (3):** `CHANGELOG.md`, `Chart.yaml`, `templates/_helpers.tpl`
- **Config layers (3):**
  1. `values.yaml` — defines `dataPlane.extraEnvVars` with potential Helm template expressions
  2. `templates/_helpers.tpl` — `tplrender` named template that renders values with context
  3. `templates/data-plane/deployment.yaml` — init containers using `extraEnvVars` with inconsistent context passing to `tplrender`
- **Drift pattern:** The `tplrender` helper template requires a `context` variable to properly evaluate Helm templating expressions in user-provided values. Some init container invocations passed the context correctly while others did not, causing `extraEnvVars` with Helm expressions to render correctly in some containers but fail in others.
- **Difficulty:** Medium — 3-layer (values → helper → deployment template), template context propagation drift
- **Why interesting:** Agent must trace how the `tplrender` helper is called from different locations in the deployment template and identify which calls are missing the context parameter. This tests understanding of Helm's template scoping and context propagation.

---

## argoproj/argo-cd (2 candidates)

### Candidate 5: ArgoCD — Nested Redis-HA Chart Values SecurityContext Drift

- **PR:** [#22035](https://github.com/argoproj/argo-cd/pull/22035) — "fix: removed null security context from values.yaml to placate helm 3.17.1"
- **Merged:** 2025-02-26
- **Files changed (1):** `manifests/ha/base/redis-ha/chart/values.yaml`
- **Config layers (3):**
  1. `manifests/ha/base/redis-ha/chart/Chart.yaml` — defines the redis-ha subchart dependency
  2. `manifests/ha/base/redis-ha/chart/values.yaml` — ArgoCD's override values for the redis-ha subchart
  3. Upstream redis-ha chart defaults — the base chart's own values.yaml with securityContext defaults
- **Drift pattern:** ArgoCD's redis-ha values override set `securityContext: null` which was invalid YAML/Helm. When Helm 3.17.1 tightened validation, this null value created a diff between the rendered manifests and the expected state, causing CI failures. The fix removed the null overrides to let the upstream defaults apply.
- **Difficulty:** Medium — 3-layer (upstream defaults → ArgoCD overrides → rendered manifest), Helm version-sensitive behavior
- **Why interesting:** Tests whether agent can navigate the multi-layer Helm value precedence chain and understand how null overrides interact with upstream defaults differently across Helm versions.

### Candidate 6: ArgoCD — ignoreDifferences Normalization Drift in Sync Comparison

- **PR:** [#26994](https://github.com/argoproj/argo-cd/pull/26994) — "fix: skip target normalization merge patch for resources without matching ignoreDifferences"
- **Merged:** 2025-03-xx
- **Config layers (3+):**
  1. Application manifest — defines `spec.ignoreDifferences` configuration
  2. ArgoCD ConfigMap (`argocd-cm`) — defines global `resource.customizations.ignoreDifferences` overrides
  3. Controller normalization logic — applies merge patches based on ignoreDifferences config
  4. Live cluster state — actual resource state that may diverge from desired
- **Drift pattern:** The ArgoCD controller applied normalization merge patches to ALL resources during sync comparison, even those without matching `ignoreDifferences` entries. This caused phantom diffs between the desired and live state, making resources appear out-of-sync when they were actually in-sync.
- **Difficulty:** Expert — 3+ layers (app manifest → configmap → controller logic → live state), requires understanding GitOps sync semantics
- **Why interesting:** This is a meta-drift problem — the tool designed to detect and reconcile drift was itself introducing false drift signals due to over-broad normalization application. Agent must understand the ArgoCD sync comparison pipeline and how `ignoreDifferences` flows through multiple configuration layers.

---

## Go/No-Go Assessment

**Result: GO** — 6 candidates identified, all with >= 3-layer config hierarchy.

| # | Repo | Chart/Component | Layers | Difficulty | Selected |
|---|------|----------------|--------|------------|----------|
| 1 | bitnami/charts | spring-cloud-dataflow | 4 | Hard | Yes |
| 2 | bitnami/charts | consul | 3 | Medium | Yes |
| 3 | bitnami/charts | redis | 4 | Hard | Yes |
| 4 | bitnami/charts | apisix | 3 | Medium | Reserve |
| 5 | argoproj/argo-cd | redis-ha subchart | 3 | Medium | Yes |
| 6 | argoproj/argo-cd | sync normalization | 3+ | Expert | Reserve |

**Selected for task authoring:** Candidates 1, 2, 3, 5 (4 tasks covering medium/hard/hard/medium difficulty distribution matching 30%/50% target).
