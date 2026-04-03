# Plan: Multi-Repo Incident Investigation Tasks

## Task 1: incident-investigation-dual-istio-001

- **Scenario**: Service mesh routing failure — requests to a specific service return 503 after Istio upgrade. Trace from Istio VirtualService HTTPRoute matching through to Envoy filter chain configuration.
- **Repos**: istio/istio v1.20.0, envoyproxy/envoy v1.28.0
- **Pattern**: investigate
- **Key files**: Istio pilot/pkg/networking/core/v1alpha3/route/route.go, Envoy source/common/router/config_impl.cc
- **Checkpoints**: root_cause (0.35), error_chain (0.30), affected_services (0.15), remediation (0.20)
- **Output**: /workspace/istio/INCIDENT_REPORT.md

## Task 2: incident-investigation-dual-prometheus-001

- **Scenario**: Critical alerts silenced unexpectedly. Alertmanager inhibition rules interact with Prometheus recording rules causing alerts to never fire.
- **Repos**: prometheus/prometheus v2.48.0, prometheus/alertmanager v0.26.0
- **Pattern**: investigate
- **Key files**: Prometheus rules/manager.go, Alertmanager inhibit/inhibitor.go
- **Checkpoints**: root_cause (0.35), error_chain (0.30), affected_services (0.15), remediation (0.20)
- **Output**: /workspace/alertmanager/INCIDENT_REPORT.md

## Task 3: incident-investigation-tri-containerd-001

- **Scenario**: Container start failure with "exec format error" despite correct platform image. Trace from Docker daemon through containerd shim to runc exec.
- **Repos**: moby/moby v24.0.7, containerd/containerd v1.7.8, opencontainers/runc v1.1.10
- **Pattern**: investigate
- **Key files**: moby daemon/start.go, containerd pkg/process/init.go, runc libcontainer/process_linux.go
- **Checkpoints**: root_cause (0.30), error_chain (0.30), affected_components (0.20), remediation (0.20)
- **Output**: /workspace/moby/INCIDENT_REPORT.md

## Task 4: incident-investigation-dual-kafka-001

- **Scenario**: JDBC Sink Connector fails with transaction timeout. Trace from Kafka Connect framework through JDBC connector to identify the root cause in offset commit vs JDBC transaction interaction.
- **Repos**: apache/kafka 3.6.0, confluentinc/kafka-connect-jdbc v10.7.4
- **Pattern**: investigate
- **Key files**: kafka connect/runtime/src/.../WorkerSinkTask.java, kafka-connect-jdbc src/.../JdbcSinkTask.java
- **Checkpoints**: root_cause (0.35), error_chain (0.30), affected_connectors (0.15), remediation (0.20)
- **Output**: /workspace/kafka/INCIDENT_REPORT.md

## Task 5: incident-investigation-dual-flux-001

- **Scenario**: Helm release stuck in "not-ready" state after Flux upgrade. Flux reconciliation loop cannot detect helm-controller's release status correctly due to status condition API change.
- **Repos**: fluxcd/flux2 v2.2.0, fluxcd/helm-controller v0.37.0
- **Pattern**: enforce
- **Key files**: flux2 internal/reconcile/reconciler.go, helm-controller internal/reconcile/helmrelease.go
- **Checkpoints**: root_cause (0.35), error_chain (0.30), affected_resources (0.15), remediation (0.20)
- **Output**: /workspace/flux2/INCIDENT_REPORT.md

## Implementation Steps

1. Create 5 directories under benchmarks/incident_response/
2. For each: create task.toml, ground_truth.json, instruction.md, checks/ with 2+ scripts
3. Verify all acceptance criteria
