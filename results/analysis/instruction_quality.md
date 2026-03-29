# Instruction Quality Audit Report

**Date:** 2026-03-29
**Tasks audited:** 97

## Summary

| Rating | Count |
|--------|-------|
| PASS | 47 |
| WARN | 45 |
| FAIL | 5 |

## Issue Frequency

| Issue Category | Count |
|---------------|-------|
| Alignment: checkpoint concept missing | 26 |
| GT leakage: FAIL-level file path leak (3+ paths) | 23 |
| GT leakage: file path mentioned (1-2 paths) | 22 |
| Completeness: no workspace location | 11 |
| Realism: missing enterprise framing | 8 |
| Completeness: no output format | 3 |

## FAIL Tasks (5)

### dependency_management/ccx-dep-trace-106

- FAIL: Instruction reveals GT file path: gcc/passes.def
- FAIL: Instruction reveals GT file path: gcc/passes.cc
- FAIL: Instruction reveals GT file path: gcc/tree-pass.h
- FAIL: Instruction reveals GT file path: gcc/pass_manager.h
- FAIL: Instruction reveals GT file path: gcc/tree-ssa-dce.cc
- FAIL: Instruction leaks 5 ground-truth file paths — gives away the answer

### feature_delivery/schema-evolution-009

- FAIL: Instruction reveals GT file path: src/sentry/backup/comparators.py
- FAIL: Instruction reveals GT file path: src/sentry/migrations/0947_add_dashboard_last_visited_model.py
- FAIL: Instruction reveals GT file path: src/sentry/testutils/helpers/backups.py
- FAIL: Instruction leaks 3 ground-truth file paths — gives away the answer

### feature_delivery/schema-evolution-010

- FAIL: Instruction reveals GT file path: server/channels/app/view_test.go
- FAIL: Instruction reveals GT file path: server/channels/api4/view_test.go
- FAIL: Instruction reveals GT file path: server/public/model/view.go
- FAIL: Instruction reveals GT file path: server/i18n/en.json
- FAIL: Instruction reveals GT file path: server/channels/store/sqlstore/view_store.go
- FAIL: Instruction reveals GT file path: server/channels/db/migrations/postgres/000167_views_drop_icon.up.sql
- FAIL: Instruction reveals GT file path: server/public/model/view_test.go
- FAIL: Instruction reveals GT file path: server/channels/store/storetest/view_store.go
- FAIL: Instruction leaks 8 ground-truth file paths — gives away the answer

### security_operations/ceph-rgw-auth-secure-001

- FAIL: Instruction reveals GT file path: src/rgw/rgw_rest_s3.cc
- FAIL: Instruction reveals GT file path: src/rgw/rgw_auth.h
- FAIL: Instruction reveals GT file path: src/rgw/rgw_auth_s3.h
- FAIL: Instruction reveals GT file path: src/rgw/rgw_auth_s3.cc
- FAIL: Instruction leaks 4 ground-truth file paths — gives away the answer
- WARN: Instruction lacks enterprise scenario framing (no ticket/report/narrative)

### technical_debt/beam-pipeline-builder-refac-001

- FAIL: Instruction reveals GT file path: sdks/java/core/src/main/java/org/apache/beam/sdk/options/PipelineOptionsValidator.java
- FAIL: Instruction reveals GT file path: sdks/java/core/src/main/java/org/apache/beam/sdk/options/PipelineOptions.java
- FAIL: Instruction reveals GT file path: sdks/java/core/src/main/java/org/apache/beam/sdk/options/PipelineOptionsFactory.java
- FAIL: Instruction leaks 3 ground-truth file paths — gives away the answer
- WARN: Instruction lacks enterprise scenario framing (no ticket/report/narrative)

## WARN Tasks (45)

### customer_escalation/err-provenance-01

- WARN: Checkpoint 'error_chain' concept may not be addressed in instruction

### customer_escalation/err-provenance-010

- WARN: Checkpoint 'error_source' concept may not be addressed in instruction

### customer_escalation/err-provenance-04

- WARN: Checkpoint 'error_source' concept may not be addressed in instruction
- WARN: Checkpoint 'error_chain' concept may not be addressed in instruction

### customer_escalation/err-provenance-05

- WARN: Checkpoint 'error_source' concept may not be addressed in instruction
- WARN: Checkpoint 'error_chain' concept may not be addressed in instruction

### customer_escalation/err-provenance-06

- WARN: Checkpoint 'error_source' concept may not be addressed in instruction
- WARN: Checkpoint 'error_chain' concept may not be addressed in instruction

### customer_escalation/err-provenance-07

- WARN: Checkpoint 'error_chain' concept may not be addressed in instruction

### customer_escalation/err-provenance-08

- WARN: Checkpoint 'error_source' concept may not be addressed in instruction
- WARN: Checkpoint 'error_chain' concept may not be addressed in instruction

### customer_escalation/support-mapping-001

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-002

- WARN: Instruction does not mention workspace/repository location
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-003

- WARN: Instruction does not mention workspace/repository location
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-004

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-005

- WARN: Instruction does not mention workspace/repository location
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-006

- WARN: Instruction does not mention workspace/repository location

### customer_escalation/support-mapping-007

- WARN: Instruction does not mention workspace/repository location
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-008

- WARN: Instruction does not mention workspace/repository location
- WARN: Instruction does not specify expected output format or clear deliverables
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-009

- WARN: Instruction does not mention workspace/repository location
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-010

- WARN: Instruction does not mention workspace/repository location
- WARN: Instruction does not specify expected output format or clear deliverables
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-011

- WARN: Instruction does not mention workspace/repository location
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-012

- WARN: Instruction does not mention workspace/repository location
- WARN: Instruction does not specify expected output format or clear deliverables
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### dependency_management/api-contract-001

- WARN: Instruction mentions GT file path: metadata/metadata.go

### dependency_management/api-contract-002

- WARN: Instruction mentions GT file path: balancer/balancer.go
- WARN: Instruction mentions GT file path: resolver/resolver.go
- WARN: Checkpoint 'identify_breaking_api' concept may not be addressed in instruction

### dependency_management/api-contract-005

- WARN: Instruction mentions GT file path: internal/status/status.go
- WARN: Checkpoint 'identify_breaking_api' concept may not be addressed in instruction

### dependency_management/api-contract-007

- WARN: Checkpoint 'identify_breaking_api' concept may not be addressed in instruction

### dependency_management/dep-traversal-007

- WARN: Instruction mentions GT file path: packages/grpc-js/package.json

### feature_delivery/aspnetcore-code-review-001

- WARN: Instruction mentions GT file path: src/Components/Web/src/Forms/ExpressionMemberAccessor.cs
- WARN: Instruction mentions GT file path: src/Components/Web/src/Forms/DisplayName.cs

### feature_delivery/camel-routing-arch-001

- WARN: Instruction does not mention workspace/repository location

### feature_delivery/monorepo-boundary-001

- WARN: Instruction mentions GT file path: packages/babel-types/src/definitions/typescript.ts

### feature_delivery/monorepo-boundary-006

- WARN: Instruction mentions GT file path: config/config/src/getOptionsFromRootManifest.ts

### feature_delivery/schema-evolution-001

- WARN: Instruction mentions GT file path: zerver/migrations/0578_namedusergroup_deactivated.py

### feature_delivery/schema-evolution-002

- WARN: Instruction mentions GT file path: zerver/migrations/0595_add_realmexport_table_and_backfill.py

### feature_delivery/schema-evolution-004

- WARN: Instruction mentions GT file path: zerver/migrations/0776_realm_default_avatar_source.py

### feature_delivery/schema-evolution-005

- WARN: Instruction mentions GT file path: db/migrate/20250319024514_add_automatic_to_reviewable_claimed_topic.rb

### feature_delivery/schema-evolution-006

- WARN: Instruction mentions GT file path: db/migrate/20250614020437_add_description_to_invites.rb

### incident_response/ansible-abc-imports-fix-001

- WARN: Instruction mentions GT file path: lib/ansible/module_utils/common/_collections_compat.py
- WARN: Instruction lacks enterprise scenario framing (no ticket/report/narrative)

### incident_response/ansible-galaxy-tar-regression-prove-001

- WARN: Checkpoint 'test_fails_on_buggy_code' concept may not be addressed in instruction

### incident_response/incident-investigation-002

- WARN: Instruction mentions GT file path: staging/src/k8s.io/apiserver/pkg/storage/etcd3/watcher.go
- WARN: Instruction mentions GT file path: staging/src/k8s.io/apiserver/pkg/storage/etcd/etcd_watcher.go

### platform_engineering/config-drift-001

- WARN: Instruction mentions GT file path: bitnami/consul/values.yaml

### platform_engineering/config-drift-004

- WARN: Instruction mentions GT file path: manifests/ha/base/redis-ha/chart/values.yaml

### security_operations/rbac-audit-001

- WARN: Instruction mentions GT file path: webhooks/pkg/rbac/rbac.go

### security_operations/rbac-audit-003

- WARN: Instruction mentions GT file path: src/common/security/robot/context.go
- WARN: Instruction mentions GT file path: src/server/v2.0/handler/robot.go

### technical_debt/refactor-orchestration-003

- WARN: Instruction lacks enterprise scenario framing (no ticket/report/narrative)

### technical_debt/refactor-orchestration-004

- WARN: Instruction lacks enterprise scenario framing (no ticket/report/narrative)

### technical_debt/refactor-orchestration-005

- WARN: Instruction lacks enterprise scenario framing (no ticket/report/narrative)

### technical_debt/refactor-orchestration-006

- WARN: Instruction lacks enterprise scenario framing (no ticket/report/narrative)

### technical_debt/refactor-orchestration-008

- WARN: Instruction lacks enterprise scenario framing (no ticket/report/narrative)

## PASS Tasks (47)

### customer_escalation/err-provenance-02

- No issues found

### customer_escalation/err-provenance-03

- No issues found

### customer_escalation/err-provenance-09

- No issues found

### dependency_management/api-contract-003

- No issues found

### dependency_management/api-contract-004

- No issues found

### dependency_management/api-contract-006

- No issues found

### dependency_management/api-contract-008

- No issues found

### dependency_management/dep-traversal-001

- No issues found

### dependency_management/dep-traversal-002

- No issues found

### dependency_management/dep-traversal-003

- No issues found

### dependency_management/dep-traversal-004

- No issues found

### dependency_management/dep-traversal-005

- No issues found

### dependency_management/dep-traversal-006

- No issues found

### dependency_management/dep-traversal-008

- No issues found

### dependency_management/dep-traversal-009

- No issues found

### dependency_management/dep-traversal-010

- No issues found

### dependency_management/dep-traversal-011

- No issues found

### dependency_management/dep-traversal-012

- No issues found

### feature_delivery/monorepo-boundary-002

- No issues found

### feature_delivery/monorepo-boundary-003

- No issues found

### feature_delivery/monorepo-boundary-004

- No issues found

### feature_delivery/monorepo-boundary-005

- No issues found

### feature_delivery/monorepo-boundary-007

- No issues found

### feature_delivery/monorepo-boundary-008

- No issues found

### feature_delivery/monorepo-boundary-009

- No issues found

### feature_delivery/monorepo-boundary-010

- No issues found

### feature_delivery/schema-evolution-003

- No issues found

### feature_delivery/schema-evolution-007

- No issues found

### feature_delivery/schema-evolution-008

- No issues found

### incident_response/ccx-incident-032

- No issues found

### incident_response/incident-investigation-001

- No issues found

### incident_response/incident-investigation-003

- No issues found

### incident_response/incident-investigation-004

- No issues found

### platform_engineering/config-drift-002

- No issues found

### platform_engineering/config-drift-003

- No issues found

### security_operations/ccx-compliance-052

- No issues found

### security_operations/ccx-compliance-053

- No issues found

### security_operations/rbac-audit-002

- No issues found

### security_operations/rbac-audit-004

- No issues found

### technical_debt/dead-code-001

- No issues found

### technical_debt/dead-code-002

- No issues found

### technical_debt/dead-code-003

- No issues found

### technical_debt/dead-code-004

- No issues found

### technical_debt/dead-code-005

- No issues found

### technical_debt/refactor-orchestration-001

- No issues found

### technical_debt/refactor-orchestration-002

- No issues found

### technical_debt/refactor-orchestration-007

- No issues found
