# Instruction Quality Audit Report

**Date:** 2026-03-29
**Tasks audited:** 111

## Summary

| Rating | Count |
|--------|-------|
| PASS | 59 |
| WARN | 52 |
| FAIL | 0 |

## Issue Frequency

| Issue Category | Count |
|---------------|-------|
| Alignment: checkpoint concept missing | 38 |
| GT leakage: file path mentioned (1-2 paths) | 18 |
| Realism: missing enterprise framing | 8 |
| Completeness: no output format | 3 |
| Completeness: no workspace location | 2 |

## WARN Tasks (52)

### customer_escalation/calibration-001

- WARN: Checkpoint 'error_source' concept may not be addressed in instruction

### customer_escalation/calibration-002

- WARN: Checkpoint 'error_source' concept may not be addressed in instruction
- WARN: Checkpoint 'error_chain' concept may not be addressed in instruction

### customer_escalation/calibration-003

- WARN: Checkpoint 'error_source' concept may not be addressed in instruction
- WARN: Checkpoint 'error_chain' concept may not be addressed in instruction

### customer_escalation/calibration-004

- WARN: Checkpoint 'error_source' concept may not be addressed in instruction
- WARN: Checkpoint 'error_chain' concept may not be addressed in instruction

### customer_escalation/calibration-005

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/calibration-006

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/calibration-007

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/calibration-008

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/chain-err-flask-import-001

- WARN: Instruction lacks enterprise scenario framing (no ticket/report/narrative)
- WARN: Instruction does not mention workspace/repository location

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

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-003

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-004

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-005

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-007

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-008

- WARN: Instruction does not specify expected output format or clear deliverables
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-009

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-010

- WARN: Instruction does not specify expected output format or clear deliverables
- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-011

- WARN: Checkpoint 'code_paths' concept may not be addressed in instruction

### customer_escalation/support-mapping-012

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

### feature_delivery/aspnetcore-code-review-001

- WARN: Instruction mentions GT file path: src/Components/Web/src/Forms/ExpressionMemberAccessor.cs

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

### incident_response/event-replay-click-ci-001

- WARN: Instruction does not mention workspace/repository location
- WARN: Checkpoint 'triage_severity' concept may not be addressed in instruction

### platform_engineering/config-drift-001

- WARN: Instruction mentions GT file path: bitnami/consul/values.yaml

### platform_engineering/config-drift-004

- WARN: Instruction mentions GT file path: manifests/ha/base/redis-ha/chart/values.yaml

### security_operations/rbac-audit-001

- WARN: Instruction mentions GT file path: webhooks/pkg/rbac/rbac.go

### security_operations/rbac-audit-003

- WARN: Instruction mentions GT file path: src/common/security/robot/context.go
- WARN: Instruction mentions GT file path: src/server/v2.0/handler/robot.go

### technical_debt/beam-pipeline-builder-refac-001

- WARN: Instruction lacks enterprise scenario framing (no ticket/report/narrative)

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

## PASS Tasks (59)

### customer_escalation/err-provenance-02

- No issues found

### customer_escalation/err-provenance-03

- No issues found

### customer_escalation/err-provenance-09

- No issues found

### customer_escalation/support-mapping-006

- No issues found

### dependency_management/api-contract-003

- No issues found

### dependency_management/api-contract-004

- No issues found

### dependency_management/api-contract-006

- No issues found

### dependency_management/api-contract-008

- No issues found

### dependency_management/ccx-dep-trace-106

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

### dependency_management/dep-traversal-007

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

### feature_delivery/camel-routing-arch-001

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

### feature_delivery/schema-evolution-009

- No issues found

### feature_delivery/schema-evolution-010

- No issues found

### incident_response/ccx-incident-032

- No issues found

### incident_response/incident-investigation-001

- No issues found

### incident_response/incident-investigation-002

- No issues found

### incident_response/incident-investigation-003

- No issues found

### incident_response/incident-investigation-004

- No issues found

### platform_engineering/calibration-001

- No issues found

### platform_engineering/calibration-002

- No issues found

### platform_engineering/config-drift-002

- No issues found

### platform_engineering/config-drift-003

- No issues found

### security_operations/ccx-compliance-052

- No issues found

### security_operations/ccx-compliance-053

- No issues found

### security_operations/ceph-rgw-auth-secure-001

- No issues found

### security_operations/rbac-audit-002

- No issues found

### security_operations/rbac-audit-004

- No issues found

### technical_debt/calibration-001

- No issues found

### technical_debt/calibration-002

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
