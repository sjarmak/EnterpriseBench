# Duplicate and Near-Duplicate Task Detection Report

**Date:** 2026-03-29
**Tasks scanned:** 97
**Findings:** 17

## Summary

| Check | Count |
|-------|-------|
| identical_gt_paths | 2 |
| high_instruction_similarity | 0 |
| same_repo_rev_pr | 0 |
| identical_check_scripts | 15 |

| Severity | Count |
|----------|-------|
| HIGH | 2 |
| MEDIUM | 15 |

## Findings

### Identical Ground-Truth File Path Sets

**1. [HIGH]** Tasks: technical_debt/refactor-orchestration-001, technical_debt/refactor-orchestration-002, technical_debt/refactor-orchestration-003, technical_debt/refactor-orchestration-004, technical_debt/refactor-orchestration-008
   - Shared paths: go.mod

**2. [HIGH]** Tasks: dependency_management/dep-traversal-003, dependency_management/dep-traversal-004, dependency_management/dep-traversal-005, dependency_management/dep-traversal-006
   - Shared paths: go.mod, go.sum

### Identical Check Script Content (same task type)

**1. [MEDIUM]** Tasks: customer_escalation/err-provenance-01, customer_escalation/err-provenance-010, customer_escalation/err-provenance-02, customer_escalation/err-provenance-03, customer_escalation/err-provenance-04, customer_escalation/err-provenance-05, customer_escalation/err-provenance-06, customer_escalation/err-provenance-07, customer_escalation/err-provenance-08, customer_escalation/err-provenance-09
   - Script: check_error_chain.sh, Type: error_provenance

**2. [MEDIUM]** Tasks: customer_escalation/err-provenance-01, customer_escalation/err-provenance-010, customer_escalation/err-provenance-02, customer_escalation/err-provenance-03, customer_escalation/err-provenance-04, customer_escalation/err-provenance-05, customer_escalation/err-provenance-06, customer_escalation/err-provenance-07, customer_escalation/err-provenance-08, customer_escalation/err-provenance-09
   - Script: check_error_source.sh, Type: error_provenance

**3. [MEDIUM]** Tasks: customer_escalation/err-provenance-01, customer_escalation/err-provenance-010, customer_escalation/err-provenance-02, customer_escalation/err-provenance-03, customer_escalation/err-provenance-04, customer_escalation/err-provenance-05, customer_escalation/err-provenance-06, customer_escalation/err-provenance-07, customer_escalation/err-provenance-08, customer_escalation/err-provenance-09
   - Script: check_trigger_conditions.sh, Type: error_provenance

**4. [MEDIUM]** Tasks: customer_escalation/support-mapping-001, customer_escalation/support-mapping-002, customer_escalation/support-mapping-003, customer_escalation/support-mapping-004, customer_escalation/support-mapping-005, customer_escalation/support-mapping-006, customer_escalation/support-mapping-007, customer_escalation/support-mapping-008, customer_escalation/support-mapping-009, customer_escalation/support-mapping-010, customer_escalation/support-mapping-011, customer_escalation/support-mapping-012
   - Script: check_code_paths.sh, Type: support_code_mapping

**5. [MEDIUM]** Tasks: customer_escalation/support-mapping-001, customer_escalation/support-mapping-002, customer_escalation/support-mapping-003, customer_escalation/support-mapping-004, customer_escalation/support-mapping-005, customer_escalation/support-mapping-006, customer_escalation/support-mapping-007, customer_escalation/support-mapping-008, customer_escalation/support-mapping-009, customer_escalation/support-mapping-010, customer_escalation/support-mapping-011, customer_escalation/support-mapping-012
   - Script: check_ownership.sh, Type: support_code_mapping

**6. [MEDIUM]** Tasks: customer_escalation/support-mapping-001, customer_escalation/support-mapping-002, customer_escalation/support-mapping-003, customer_escalation/support-mapping-004, customer_escalation/support-mapping-005, customer_escalation/support-mapping-006, customer_escalation/support-mapping-007, customer_escalation/support-mapping-008, customer_escalation/support-mapping-009, customer_escalation/support-mapping-010, customer_escalation/support-mapping-011, customer_escalation/support-mapping-012
   - Script: check_related_issues.sh, Type: support_code_mapping

**7. [MEDIUM]** Tasks: customer_escalation/support-mapping-001, customer_escalation/support-mapping-002, customer_escalation/support-mapping-003, customer_escalation/support-mapping-004, customer_escalation/support-mapping-005, customer_escalation/support-mapping-006, customer_escalation/support-mapping-007, customer_escalation/support-mapping-008, customer_escalation/support-mapping-009, customer_escalation/support-mapping-010, customer_escalation/support-mapping-011, customer_escalation/support-mapping-012
   - Script: check_severity.sh, Type: support_code_mapping

**8. [MEDIUM]** Tasks: feature_delivery/monorepo-boundary-001, feature_delivery/monorepo-boundary-004
   - Script: check_impact_classification.sh, Type: monorepo_boundary

**9. [MEDIUM]** Tasks: feature_delivery/monorepo-boundary-002, feature_delivery/monorepo-boundary-003
   - Script: check_impact_classification.sh, Type: monorepo_boundary

**10. [MEDIUM]** Tasks: feature_delivery/monorepo-boundary-005, feature_delivery/monorepo-boundary-006, feature_delivery/monorepo-boundary-007
   - Script: check_impact_classification.sh, Type: monorepo_boundary

**11. [MEDIUM]** Tasks: technical_debt/dead-code-001, technical_debt/dead-code-003
   - Script: check_dead_code.sh, Type: dead_code_necropsy

**12. [MEDIUM]** Tasks: technical_debt/dead-code-001, technical_debt/dead-code-002, technical_debt/dead-code-003
   - Script: check_evidence.sh, Type: dead_code_necropsy

**13. [MEDIUM]** Tasks: technical_debt/dead-code-001, technical_debt/dead-code-003
   - Script: check_feature_flags.sh, Type: dead_code_necropsy

**14. [MEDIUM]** Tasks: technical_debt/refactor-orchestration-001, technical_debt/refactor-orchestration-002, technical_debt/refactor-orchestration-003, technical_debt/refactor-orchestration-004, technical_debt/refactor-orchestration-005, technical_debt/refactor-orchestration-006, technical_debt/refactor-orchestration-007, technical_debt/refactor-orchestration-008
   - Script: check_parallelism.sh, Type: refactor_orchestration

**15. [MEDIUM]** Tasks: technical_debt/refactor-orchestration-001, technical_debt/refactor-orchestration-002, technical_debt/refactor-orchestration-003, technical_debt/refactor-orchestration-004, technical_debt/refactor-orchestration-005, technical_debt/refactor-orchestration-006, technical_debt/refactor-orchestration-007, technical_debt/refactor-orchestration-008
   - Script: check_topo_order.sh, Type: refactor_orchestration

### Repo+Rev Overlap (Informational)

Tasks sharing the same repo and revision (expected for same-codebase tasks):

- **github.com/kubernetes/kubernetes@v1.32.0** (4 tasks): customer_escalation/err-provenance-03, customer_escalation/err-provenance-05, technical_debt/refactor-orchestration-001, technical_debt/refactor-orchestration-003
- **github.com/etcd-io/etcd@v3.5.17** (4 tasks): dependency_management/api-contract-004, technical_debt/refactor-orchestration-003, technical_debt/refactor-orchestration-007, technical_debt/refactor-orchestration-008
- **github.com/kubernetes/kubernetes@v1.33.0** (3 tasks): technical_debt/refactor-orchestration-002, technical_debt/refactor-orchestration-007, technical_debt/refactor-orchestration-008
- **github.com/kubernetes/kubernetes@v1.33.0-alpha.1** (2 tasks): customer_escalation/err-provenance-01, customer_escalation/err-provenance-06
- **github.com/kubernetes/kubernetes@v1.33.0-alpha.2** (2 tasks): customer_escalation/err-provenance-02, customer_escalation/err-provenance-04
- **github.com/hashicorp/terraform@v1.10.0** (2 tasks): customer_escalation/err-provenance-08, customer_escalation/err-provenance-09
- **github.com/grafana/grafana@** (2 tasks): customer_escalation/support-mapping-003, customer_escalation/support-mapping-004
- **github.com/grpc/grpc-go@v1.62.0** (2 tasks): dependency_management/dep-traversal-006, technical_debt/refactor-orchestration-004
- **github.com/psf/requests@v2.28.0** (2 tasks): dependency_management/dep-traversal-008, dependency_management/dep-traversal-009
- **github.com/boto/boto3@1.26.0** (2 tasks): dependency_management/dep-traversal-008, dependency_management/dep-traversal-009
- **github.com/babel/babel@v7.23.5** (2 tasks): feature_delivery/monorepo-boundary-001, feature_delivery/monorepo-boundary-004
- **github.com/pnpm/pnpm@v9.15.0** (2 tasks): feature_delivery/monorepo-boundary-006, feature_delivery/monorepo-boundary-007
- **github.com/ansible/ansible@v2.16.0** (2 tasks): incident_response/ansible-abc-imports-fix-001, incident_response/ansible-galaxy-tar-regression-prove-001
- **github.com/sg-evals/envoy@v1.31.2** (2 tasks): incident_response/ccx-incident-032, security_operations/ccx-compliance-052

## Verdict

**2 HIGH-severity findings** require review. See details above.
