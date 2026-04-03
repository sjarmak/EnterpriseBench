# Plan: Multi-Repo Task Authoring (10 tasks)

## config_drift (benchmarks/platform_engineering/)

### 1. config-drift-dual-argocd-001

- Type: config_drift
- Repos: ArgoCD (v2.9.0, primary) + argo-helm (argo-cd-5.51.0, consumer)
- Ecosystem: argocd-ecosystem
- Pattern: enforce
- Description: Detect config drift between ArgoCD application controller defaults and Helm chart values.yaml overrides

### 2. config-drift-dual-prometheus-001

- Type: config_drift
- Repos: Prometheus (v2.48.0, primary) + Thanos (v0.32.5, consumer)
- Ecosystem: prometheus-ecosystem
- Pattern: enforce
- Description: Detect config drift between Prometheus TSDB/storage config and Thanos sidecar expected configuration

## db_schema_evolution (benchmarks/feature_delivery/)

### 3. schema-evolution-dual-django-001

- Type: db_schema_evolution
- Repos: Django (5.0, primary) + Wagtail (v5.2, consumer)
- Ecosystem: django-ecosystem
- Pattern: propagate
- Description: Trace Django model field changes that break Wagtail's dependent model assumptions

### 4. schema-evolution-dual-sentry-001

- Type: db_schema_evolution
- Repos: Sentry (23.11.0, primary) + Relay (23.11.0, consumer)
- Ecosystem: sentry-ecosystem
- Pattern: propagate
- Description: Trace schema evolution between Sentry Django models and Relay Rust schema definitions

## dead_code_necropsy (benchmarks/technical_debt/)

### 5. dead-code-dual-react-001

- Type: dead_code_necropsy
- Repos: React (v18.2.0, primary) + create-react-app (v5.0.1, consumer)
- Ecosystem: react-ecosystem
- Pattern: investigate
- Description: Find dead code from deprecated React internals still referenced by create-react-app

### 6. dead-code-dual-k8s-001

- Type: dead_code_necropsy
- Repos: Kubernetes (v1.28.0, primary) + client-go (v0.28.0, consumer)
- Ecosystem: kubernetes-ecosystem
- Pattern: investigate
- Description: Find dead code in client-go referencing removed Kubernetes API groups

## error_provenance (benchmarks/customer_escalation/)

### 7. err-provenance-dual-docker-001

- Type: error_provenance
- Repos: Docker CLI (v24.0.7, primary) + Moby (v24.0.7, upstream)
- Ecosystem: docker-ecosystem
- Pattern: investigate
- Description: Trace user-facing Docker error to Moby daemon origin

### 8. err-provenance-dual-terraform-001

- Type: error_provenance
- Repos: Terraform (v1.6.0, primary) + terraform-provider-aws (v5.30.0, consumer)
- Ecosystem: terraform-ecosystem
- Pattern: investigate
- Description: Trace Terraform plan error to AWS provider implementation

## support_code_mapping (benchmarks/customer_escalation/)

### 9. support-mapping-dual-grafana-001

- Type: support_code_mapping
- Repos: Grafana (v10.2.0, primary) + Prometheus (v2.48.0, upstream)
- Ecosystem: grafana-prometheus-ecosystem
- Pattern: investigate
- Description: Map dashboard query failure to Prometheus query engine code

### 10. support-mapping-dual-flask-001

- Type: support_code_mapping
- Repos: Flask (3.0.0, primary) + Werkzeug (3.0.1, upstream)
- Ecosystem: flask-ecosystem
- Pattern: investigate
- Description: Map routing error to Werkzeug URL routing implementation

## Summary

- 10 tasks, 2 per type
- Patterns: enforce (2), propagate (2), investigate (6) — meets ≥4 investigate requirement
- Ecosystems: argocd, prometheus, django, sentry, react, kubernetes, docker, terraform, grafana-prometheus, flask — meets ≥3 distinct requirement
- All dual_repo stratum
