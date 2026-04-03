# Plan: Multi-Repo Remaining Types

## 8 Tasks to Create

### 1. config-drift-tri-kustomize-001 (investigate)

- Suite: platform_engineering
- Stratum: tri_repo
- Repos: kubernetes-sigs/kustomize (v5.3.0), argoproj/argo-cd (v2.9.0), fluxcd/flux2 (v2.2.0)
- Scenario: Detect drift in resource patching behavior across Kustomize overlays, ArgoCD sync, and Flux reconciliation
- Checkpoints: config_valid, drift_points, cross_repo_impact

### 2. config-drift-dual-terraform-001 (investigate)

- Suite: platform_engineering
- Stratum: dual_repo
- Repos: hashicorp/terraform (v1.7.0), hashicorp/terraform-provider-aws (v5.31.0)
- Scenario: Detect drift between Terraform core state handling and AWS provider resource implementations
- Checkpoints: config_valid, drift_points, expected_values

### 3. schema-evolution-tri-supabase-001 (propagate)

- Suite: feature_delivery
- Stratum: tri_repo
- Repos: supabase/supabase (v0.24.12), PostgREST/postgrest (v12.0.2), supabase/gotrue (v2.143.0)
- Scenario: Trace schema migration impact across Supabase, PostgREST auto-API, and GoTrue auth
- Checkpoints: schema_change, direct_refs, indirect_refs, test_impact

### 4. dead-code-dual-angular-001 (investigate)

- Suite: technical_debt
- Stratum: dual_repo
- Repos: angular/angular (18.0.0), angular/components (18.0.0)
- Scenario: Find dead exported APIs in Angular framework that are only consumed by Angular Components
- Checkpoints: dead_code_identified, cross_repo_usage, removal_impact

### 5. api-contract-tri-protobuf-001 (enforce)

- Suite: dependency_management
- Stratum: tri_repo
- Repos: protocolbuffers/protobuf (v25.1), grpc/grpc (v1.60.0), googleapis/googleapis (master common-protos-1_3_1)
- Scenario: Verify protobuf contract compliance across definitions, gRPC runtime, and googleapis
- Checkpoints: contract_source, direct_consumers, compliance_check

### 6. api-contract-dual-fastapi-001 (investigate)

- Suite: dependency_management
- Stratum: dual_repo
- Repos: tiangolo/fastapi (0.109.0), encode/httpx (0.26.0)
- Scenario: Trace API schema handling differences between FastAPI server and httpx client
- Checkpoints: contract_source, consumer_usage, drift_analysis

### 7. api-contract-tri-envoy-001 (enforce)

- Suite: dependency_management
- Stratum: tri_repo
- Repos: envoyproxy/envoy (v1.28.0), istio/istio (1.20.0), envoyproxy/go-control-plane (v0.12.0)
- Scenario: Verify xDS API contract across Envoy, Istio pilot, and go-control-plane
- Checkpoints: contract_source, direct_consumers, transitive_impact

### 8. support-mapping-dual-ansible-001 (investigate)

- Suite: customer_escalation
- Stratum: dual_repo
- Repos: ansible/ansible (v2.16.0), pallets/jinja (3.1.3)
- Scenario: Map customer Jinja2 template rendering error to code across Ansible and Jinja2
- Checkpoints: error_source, error_chain, trigger_conditions

## Implementation Steps

1. Create all 8 directories with mkdir -p
2. Create task.toml for each task
3. Create ground_truth.json for each task
4. Create instruction.md for each task
5. Create checks/ directory with 2-3 scripts per task
6. Verify all files exist and are valid
