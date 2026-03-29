# Tag/Revision Verification Report

**Date**: 2026-03-29
**Total tasks scanned**: 97
**Total repo entries**: 131
**Unique (url, rev) pairs**: 113
**Verified OK**: 104
**Missing/broken**: 9

## Missing Tags/Revisions

| URL | Rev | Detail | Affected Tasks |
|-----|-----|--------|----------------|
| https://github.com/bitnami/charts | `24493~1` | not found as tag or branch | platform_engineering/config-drift-002 |
| https://github.com/bitnami/charts | `33114~1` | not found as tag or branch | platform_engineering/config-drift-001 |
| https://github.com/bitnami/charts | `36231~1` | not found as tag or branch | platform_engineering/config-drift-003 |
| https://github.com/keycloak/keycloak | `05ff44b8a0ea57ba9c68c4b416f8b90f5116bb83~1` | not found as tag or branch | security_operations/rbac-audit-004 |
| https://github.com/keycloak/keycloak | `bfcb150e312362fa6fd9c6ac080bf58989949d93~1` | not found as tag or branch | security_operations/rbac-audit-002 |
| https://github.com/projectcalico/calico | `1ea2a4ea3e0407c97d387cc8dbe5f80db7e2e430~1` | not found as tag or branch | security_operations/rbac-audit-001 |
| https://github.com/sg-evals/envoy | `v1.31.2` | not found as tag or branch | incident_response/ccx-incident-032, security_operations/ccx-compliance-052 |
| https://github.com/sg-evals/kafka | `0753c489` | commit hash - could not verify | security_operations/ccx-compliance-053 |
| https://github.com/sg-evals/llvm-project | `a8f3c97d` | commit hash - could not verify | dependency_management/ccx-dep-trace-106 |

## Analysis

### Root Cause Categories

**1. Git parent notation `~1` used as rev (6 cases)**
- `bitnami/charts` uses `24493~1`, `33114~1`, `36231~1` -- these are PR numbers with parent notation, not valid git refs
- `keycloak/keycloak` uses `<sha>~1` -- commit hash with parent notation
- `projectcalico/calico` uses `<sha>~1` -- commit hash with parent notation
- Fix: Resolve `~1` to actual parent commit hashes. These were likely intended to mean "the commit before this PR merged" but git ls-remote cannot resolve `~1` syntax. The sandbox setup would need to clone the repo and resolve `git rev-parse <ref>~1`.

**2. sg-evals mirror repos (3 cases)**
- `sg-evals/envoy`, `sg-evals/kafka`, `sg-evals/llvm-project` -- private or non-existent mirror forks
- These are CSB-era mirror repos that may not be publicly accessible
- Fix: Either make sg-evals repos public, or update task.toml to use upstream repo URLs

### Severity

| Severity | Count | Issue |
|----------|-------|-------|
| MEDIUM | 6 | `~1` parent refs need resolution to actual commit hashes |
| HIGH | 3 | sg-evals mirror repos inaccessible (blocks sandbox setup) |

### Affected Tasks

| Task | Issue |
|------|-------|
| platform_engineering/config-drift-001 | `bitnami/charts @ 33114~1` |
| platform_engineering/config-drift-002 | `bitnami/charts @ 24493~1` |
| platform_engineering/config-drift-003 | `bitnami/charts @ 36231~1` |
| security_operations/rbac-audit-001 | `projectcalico/calico @ <sha>~1` |
| security_operations/rbac-audit-002 | `keycloak/keycloak @ <sha>~1` |
| security_operations/rbac-audit-004 | `keycloak/keycloak @ <sha>~1` |
| incident_response/ccx-incident-032 | `sg-evals/envoy @ v1.31.2` |
| security_operations/ccx-compliance-052 | `sg-evals/envoy @ v1.31.2` |
| security_operations/ccx-compliance-053 | `sg-evals/kafka @ 0753c489` |
| dependency_management/ccx-dep-trace-106 | `sg-evals/llvm-project @ a8f3c97d` |

## All Verified Pairs

| URL | Rev | Status | Tasks |
|-----|-----|--------|-------|
| https://github.com/FasterXML/jackson-databind | `jackson-databind-2.13.2` | OK | dependency_management/dep-traversal-010 |
| https://github.com/NodeBB/NodeBB | `8fd8079a84d8e71ab02eaa69ef15cb33fcea85c7` | OK | customer_escalation/support-mapping-011 |
| https://github.com/angular/angular | `891318e805da3cdfb9839bf6cb3412c15c146253` | OK | technical_debt/dead-code-005 |
| https://github.com/ansible/ansible | `v2.16.0` | OK | incident_response/ansible-abc-imports-fix-001, incident_response/ansible-galaxy-tar-regression-prove-001 |
| https://github.com/apache/beam | `v2.55.0` | OK | technical_debt/beam-pipeline-builder-refac-001 |
| https://github.com/apache/camel | `camel-4.4.0` | OK | feature_delivery/camel-routing-arch-001 |
| https://github.com/apache/druid | `druid-26.0.0` | OK | dependency_management/dep-traversal-002 |
| https://github.com/apache/kafka | `3.1.0` | OK | dependency_management/dep-traversal-011 |
| https://github.com/apache/logging-log4j2 | `rel/2.14.1` | OK | dependency_management/dep-traversal-011 |
| https://github.com/argoproj/argo-cd | `v2.14.0-rc3` | OK | platform_engineering/config-drift-004 |
| https://github.com/aws/aws-cli | `2.11.0` | OK | dependency_management/dep-traversal-008 |
| https://github.com/axios/axios | `v0.21.1` | OK | dependency_management/dep-traversal-002 |
| https://github.com/babel/babel | `v7.22.20` | OK | feature_delivery/monorepo-boundary-003 |
| https://github.com/babel/babel | `v7.23.5` | OK | feature_delivery/monorepo-boundary-001, feature_delivery/monorepo-boundary-004 |
| https://github.com/babel/babel | `v7.23.9` | OK | feature_delivery/monorepo-boundary-002 |
| https://github.com/babel/babel | `v7.25.0` | OK | technical_debt/refactor-orchestration-005 |
| https://github.com/bitnami/charts | `24493~1` | MISSING | platform_engineering/config-drift-002 |
| https://github.com/bitnami/charts | `33114~1` | MISSING | platform_engineering/config-drift-001 |
| https://github.com/bitnami/charts | `36231~1` | MISSING | platform_engineering/config-drift-003 |
| https://github.com/boto/boto3 | `1.26.0` | OK | dependency_management/dep-traversal-008, dependency_management/dep-traversal-009 |
| https://github.com/ceph/ceph | `v19.2.0` | OK | security_operations/ceph-rgw-auth-secure-001 |
| https://github.com/curl/curl | `curl-7_82_0` | OK | dependency_management/dep-traversal-012 |
| https://github.com/discourse/discourse | `168de52538632ae18b95c0757ab2ae5e21ff240c` | OK | feature_delivery/schema-evolution-008 |
| https://github.com/discourse/discourse | `290b435a727ed1d95aef554d60d8572eba7e818a` | OK | feature_delivery/schema-evolution-006 |
| https://github.com/discourse/discourse | `5d603ece49a296da47197bc91ea8e1d178d5772c` | OK | feature_delivery/schema-evolution-007 |
| https://github.com/discourse/discourse | `e7c3abb94b1db0ff811f991b873dcca9d589cd3a` | OK | feature_delivery/schema-evolution-005 |
| https://github.com/dotnet/aspnetcore | `v9.0.0` | OK | feature_delivery/aspnetcore-code-review-001 |
| https://github.com/dropwizard/dropwizard | `v2.1.0` | OK | dependency_management/dep-traversal-010 |
| https://github.com/element-hq/element-web | `526645c79160ab1ad4b4c3845de27d51263a405e` | OK | customer_escalation/support-mapping-010 |
| https://github.com/element-hq/element-web | `8ebdcab7d92f90422776c4390363338dcfd98ba5` | OK | customer_escalation/support-mapping-009 |
| https://github.com/envoyproxy/envoy | `v1.18.0` | OK | dependency_management/api-contract-006 |
| https://github.com/envoyproxy/envoy | `v1.31.2` | OK | customer_escalation/support-mapping-001 |
| https://github.com/envoyproxy/go-control-plane | `v0.12.0` | OK | dependency_management/dep-traversal-006 |
| https://github.com/envoyproxy/go-control-plane | `v0.13.2` | OK | dependency_management/api-contract-007 |
| https://github.com/envoyproxy/go-control-plane | `v0.9.9` | OK | dependency_management/api-contract-006 |
| https://github.com/etcd-io/etcd | `v3.3.0` | OK | dependency_management/api-contract-001 |
| https://github.com/etcd-io/etcd | `v3.3.10` | OK | dependency_management/api-contract-003 |
| https://github.com/etcd-io/etcd | `v3.4.3` | OK | dependency_management/api-contract-002 |
| https://github.com/etcd-io/etcd | `v3.5.12` | OK | technical_debt/refactor-orchestration-004 |
| https://github.com/etcd-io/etcd | `v3.5.17` | OK | dependency_management/api-contract-004, technical_debt/refactor-orchestration-003, technical_debt/refactor-orchestration-007 (+1 more) |
| https://github.com/etcd-io/etcd | `v3.5.9` | OK | dependency_management/dep-traversal-004 |
| https://github.com/etcd-io/etcd | `v3.6.0` | OK | technical_debt/refactor-orchestration-001 |
| https://github.com/facebook/react | `56408a5b12fa4099e9dbbeca7f6bc59e1307e507` | OK | technical_debt/dead-code-002 |
| https://github.com/facebook/react | `9fba65efa50fe5f38e5664729d4aa6f85cf7be92` | OK | technical_debt/dead-code-001 |
| https://github.com/facebook/react | `ab18f33d46171ed1963ae1ac955c5110bb1eb199` | OK | technical_debt/dead-code-003 |
| https://github.com/getsentry/sentry | `fad1fc61366a8162823603a9e86eafd96faa9c00` | OK | feature_delivery/schema-evolution-009 |
| https://github.com/git/git | `v2.35.0` | OK | dependency_management/dep-traversal-012 |
| https://github.com/go-chi/chi | `v5.0.8` | OK | dependency_management/dep-traversal-003 |
| https://github.com/goharbor/harbor | `v2.12.0` | OK | security_operations/rbac-audit-003 |
| https://github.com/gohugoio/hugo | `v0.111.0` | OK | dependency_management/dep-traversal-003 |
| https://github.com/grafana/grafana | `v10.1.0` | OK | incident_response/incident-investigation-003 |
| https://github.com/grafana/grafana | `v10.2.0` | OK | customer_escalation/err-provenance-010 |
| https://github.com/grafana/grafana | `v9.5.0` | OK | dependency_management/dep-traversal-002 |
| https://github.com/grpc-ecosystem/go-grpc-middleware | `v1.4.0` | OK | technical_debt/refactor-orchestration-008 |
| https://github.com/grpc/grpc-go | `v1.14.0` | OK | dependency_management/api-contract-003 |
| https://github.com/grpc/grpc-go | `v1.27.0` | OK | dependency_management/api-contract-002 |
| https://github.com/grpc/grpc-go | `v1.4.0` | OK | dependency_management/api-contract-001 |
| https://github.com/grpc/grpc-go | `v1.46.0` | OK | dependency_management/api-contract-008 |
| https://github.com/grpc/grpc-go | `v1.58.0` | OK | dependency_management/dep-traversal-004 |
| https://github.com/grpc/grpc-go | `v1.62.0` | OK | dependency_management/dep-traversal-006, technical_debt/refactor-orchestration-004 |
| https://github.com/grpc/grpc-go | `v1.68.0` | OK | dependency_management/api-contract-007 |
| https://github.com/grpc/grpc-go | `v1.70.0` | OK | dependency_management/api-contract-005 |
| https://github.com/grpc/grpc-go | `v1.71.0` | OK | dependency_management/api-contract-004 |
| https://github.com/grpc/grpc-go | `v1.72.1` | OK | technical_debt/refactor-orchestration-003 |
| https://github.com/grpc/grpc-go | `v1.79.0` | OK | technical_debt/refactor-orchestration-007 |
| https://github.com/grpc/grpc-node | `v1.8.0` | OK | dependency_management/dep-traversal-007 |
| https://github.com/hashicorp/consul | `v1.16.0` | OK | dependency_management/dep-traversal-005 |
| https://github.com/hashicorp/terraform | `v1.10.0` | OK | customer_escalation/err-provenance-08, customer_escalation/err-provenance-09 |
| https://github.com/hashicorp/terraform | `v1.6.0` | OK | customer_escalation/err-provenance-07 |
| https://github.com/hashicorp/vault | `v1.14.0` | OK | dependency_management/dep-traversal-005 |
| https://github.com/istio/istio | `1.10.0` | OK | dependency_management/api-contract-006 |
| https://github.com/istio/istio | `1.20.0` | OK | dependency_management/dep-traversal-006 |
| https://github.com/istio/istio | `1.24.0` | OK | dependency_management/api-contract-007 |
| https://github.com/jestjs/jest | `v29.0.0` | OK | dependency_management/dep-traversal-001 |
| https://github.com/keycloak/keycloak | `05ff44b8a0ea57ba9c68c4b416f8b90f5116bb83~1` | MISSING | security_operations/rbac-audit-004 |
| https://github.com/keycloak/keycloak | `bfcb150e312362fa6fd9c6ac080bf58989949d93~1` | MISSING | security_operations/rbac-audit-002 |
| https://github.com/kubernetes-client/javascript | `0.18.0` | OK | dependency_management/dep-traversal-007 |
| https://github.com/kubernetes/kubernetes | `v1.13.0` | OK | dependency_management/api-contract-003 |
| https://github.com/kubernetes/kubernetes | `v1.24.0` | OK | dependency_management/dep-traversal-012 |
| https://github.com/kubernetes/kubernetes | `v1.28.0` | OK | dependency_management/dep-traversal-004 |
| https://github.com/kubernetes/kubernetes | `v1.32.0` | OK | customer_escalation/err-provenance-03, customer_escalation/err-provenance-05, technical_debt/refactor-orchestration-001 (+1 more) |
| https://github.com/kubernetes/kubernetes | `v1.33.0` | OK | technical_debt/refactor-orchestration-002, technical_debt/refactor-orchestration-007, technical_debt/refactor-orchestration-008 |
| https://github.com/kubernetes/kubernetes | `v1.33.0-alpha.1` | OK | customer_escalation/err-provenance-01, customer_escalation/err-provenance-06 |
| https://github.com/kubernetes/kubernetes | `v1.33.0-alpha.2` | OK | customer_escalation/err-provenance-02, customer_escalation/err-provenance-04 |
| https://github.com/kubernetes/kubernetes | `v1.34.0` | OK | technical_debt/refactor-orchestration-006 |
| https://github.com/kubernetes/kubernetes | `v1.7.3` | OK | incident_response/incident-investigation-001 |
| https://github.com/kubernetes/kubernetes | `v1.9.1` | OK | incident_response/incident-investigation-002 |
| https://github.com/lodash/lodash | `4.17.20` | OK | dependency_management/dep-traversal-001 |
| https://github.com/mattermost/mattermost | `1349899f42212aab066a8d1a6caed08b7d3d2b53` | OK | feature_delivery/schema-evolution-010 |
| https://github.com/microsoft/TypeScript | `f7833b2a72309dd695b45cf2cf2187e2f2f264df` | OK | technical_debt/dead-code-004 |
| https://github.com/moby/moby | `v28.0.0` | OK | incident_response/incident-investigation-004 |
| https://github.com/pnpm/pnpm | `v8.15.9` | OK | feature_delivery/monorepo-boundary-005 |
| https://github.com/pnpm/pnpm | `v9.15.0` | OK | feature_delivery/monorepo-boundary-006, feature_delivery/monorepo-boundary-007 |
| https://github.com/projectcalico/calico | `1ea2a4ea3e0407c97d387cc8dbe5f80db7e2e430~1` | MISSING | security_operations/rbac-audit-001 |
| https://github.com/prometheus/prometheus | `v2.45.0` | OK | dependency_management/dep-traversal-005 |
| https://github.com/prometheus/prometheus | `v2.46.0` | OK | incident_response/incident-investigation-003 |
| https://github.com/protocolbuffers/protobuf-go | `v1.32.0` | OK | technical_debt/refactor-orchestration-004 |
| https://github.com/psf/requests | `v2.28.0` | OK | dependency_management/dep-traversal-008, dependency_management/dep-traversal-009 |
| https://github.com/rust-lang/rust | `1.76.0` | OK | feature_delivery/monorepo-boundary-010 |
| https://github.com/rust-lang/rust | `1.83.0` | OK | feature_delivery/monorepo-boundary-009 |
| https://github.com/sg-evals/envoy | `v1.31.2` | MISSING | incident_response/ccx-incident-032, security_operations/ccx-compliance-052 |
| https://github.com/sg-evals/kafka | `0753c489` | MISSING | security_operations/ccx-compliance-053 |
| https://github.com/sg-evals/llvm-project | `a8f3c97d` | MISSING | dependency_management/ccx-dep-trace-106 |
| https://github.com/spf13/cobra | `v1.10.2` | OK | technical_debt/refactor-orchestration-002 |
| https://github.com/spring-projects/spring-boot | `v2.6.1` | OK | dependency_management/dep-traversal-011 |
| https://github.com/spring-projects/spring-boot | `v2.7.0` | OK | dependency_management/dep-traversal-010 |
| https://github.com/urllib3/urllib3 | `1.26.16` | OK | dependency_management/dep-traversal-009 |
| https://github.com/vercel/next.js | `v13.5.6` | OK | feature_delivery/monorepo-boundary-008 |
| https://github.com/webpack/webpack | `v5.64.0` | OK | dependency_management/dep-traversal-001 |
| https://github.com/zulip/zulip | `38053e9c7cc59b5e3f7c26af49fc1bb57acf0b86` | OK | feature_delivery/schema-evolution-001 |
| https://github.com/zulip/zulip | `912c1b598458f89afa6814b3a19b95d4648e2371` | OK | feature_delivery/schema-evolution-002 |
| https://github.com/zulip/zulip | `f2a5dc949a7c0ec776b3729b2c92703292404127` | OK | feature_delivery/schema-evolution-004 |
| https://github.com/zulip/zulip | `faa06497ed09f65dc0c7ba510dc56ebd41fbe037` | OK | feature_delivery/schema-evolution-003 |
