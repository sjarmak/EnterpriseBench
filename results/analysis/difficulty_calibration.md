# Difficulty Calibration Audit

**Total tasks audited:** 109
**Tasks with flags:** 10
**Clean tasks:** 99

## Distribution

| Difficulty | Count |
| ---------- | ----- |
| medium     | 27    |
| hard       | 66    |
| expert     | 16    |

| Stratum                | Count |
| ---------------------- | ----- |
| calibration            | 12    |
| dual_repo              | 7     |
| large_single           | 60    |
| monorepo_cross_package | 12    |
| multi_repo             | 13    |
| tri_repo               | 5     |

## All Tasks

| Task                                    | Suite                 | Type                   | Difficulty | Stratum                | Repos | Checkpoints | GT Items | Words | Baseline | MCP  |
| --------------------------------------- | --------------------- | ---------------------- | ---------- | ---------------------- | ----- | ----------- | -------- | ----- | -------- | ---- |
| calibration-001                         | customer_escalation   | error_provenance       | medium     | calibration            | 1     | 3           | 10       | 140   | -        | -    |
| calibration-002                         | customer_escalation   | error_provenance       | medium     | calibration            | 1     | 3           | 11       | 118   | -        | -    |
| calibration-003                         | customer_escalation   | error_provenance       | medium     | calibration            | 1     | 3           | 11       | 110   | -        | -    |
| calibration-004                         | customer_escalation   | error_provenance       | medium     | calibration            | 1     | 3           | 12       | 143   | -        | -    |
| calibration-005                         | customer_escalation   | support_code_mapping   | medium     | calibration            | 1     | 3           | 8        | 137   | -        | -    |
| calibration-006                         | customer_escalation   | support_code_mapping   | medium     | calibration            | 1     | 3           | 8        | 136   | -        | -    |
| calibration-007                         | customer_escalation   | support_code_mapping   | medium     | calibration            | 1     | 3           | 9        | 130   | -        | -    |
| calibration-008                         | customer_escalation   | support_code_mapping   | medium     | calibration            | 1     | 3           | 9        | 139   | -        | -    |
| err-provenance-01                       | customer_escalation   | error_provenance       | medium     | large_single           | 1     | 3           | 10       | 184   | 0.50     | 1.00 |
| err-provenance-010                      | customer_escalation   | error_provenance       | hard       | large_single           | 1     | 3           | 13       | 182   | -        | -    |
| err-provenance-02                       | customer_escalation   | error_provenance       | hard       | large_single           | 1     | 3           | 15       | 179   | -        | -    |
| err-provenance-03                       | customer_escalation   | error_provenance       | expert     | large_single           | 1     | 3           | 13       | 176   | -        | -    |
| err-provenance-04                       | customer_escalation   | error_provenance       | hard       | large_single           | 1     | 3           | 12       | 174   | -        | -    |
| err-provenance-05                       | customer_escalation   | error_provenance       | medium     | large_single           | 1     | 3           | 10       | 149   | -        | -    |
| err-provenance-06                       | customer_escalation   | error_provenance       | hard       | large_single           | 1     | 3           | 12       | 160   | 0.59     | 1.00 |
| err-provenance-07                       | customer_escalation   | error_provenance       | hard       | large_single           | 1     | 3           | 11       | 140   | -        | -    |
| err-provenance-08                       | customer_escalation   | error_provenance       | hard       | large_single           | 1     | 3           | 12       | 163   | -        | -    |
| err-provenance-09                       | customer_escalation   | error_provenance       | medium     | large_single           | 1     | 3           | 8        | 132   | -        | -    |
| support-mapping-001                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 16       | 178   | 0.50     | 1.00 |
| support-mapping-002                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 15       | 180   | -        | -    |
| support-mapping-003                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 15       | 183   | -        | -    |
| support-mapping-004                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 13       | 198   | -        | -    |
| support-mapping-005                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 15       | 207   | -        | -    |
| support-mapping-006                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 15       | 195   | -        | -    |
| support-mapping-007                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 16       | 227   | -        | -    |
| support-mapping-008                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 14       | 153   | -        | -    |
| support-mapping-009                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 14       | 190   | -        | -    |
| support-mapping-010                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 14       | 214   | -        | -    |
| support-mapping-011                     | customer_escalation   | support_code_mapping   | hard       | large_single           | 1     | 4           | 15       | 197   | -        | -    |
| support-mapping-012                     | customer_escalation   | support_code_mapping   | expert     | large_single           | 1     | 4           | 15       | 229   | -        | -    |
| api-contract-001                        | dependency_management | api_contract           | hard       | dual_repo              | 2     | 4           | 18       | 243   | -        | -    |
| api-contract-002                        | dependency_management | api_contract           | hard       | dual_repo              | 2     | 4           | 12       | 202   | -        | -    |
| api-contract-003                        | dependency_management | api_contract           | expert     | multi_repo             | 3     | 4           | 21       | 188   | 0.80     | 1.00 |
| api-contract-004                        | dependency_management | api_contract           | hard       | dual_repo              | 2     | 4           | 11       | 181   | -        | -    |
| api-contract-005                        | dependency_management | api_contract           | expert     | large_single           | 1     | 4           | 19       | 199   | -        | -    |
| api-contract-006                        | dependency_management | api_contract           | expert     | multi_repo             | 3     | 4           | 23       | 197   | -        | -    |
| api-contract-007                        | dependency_management | api_contract           | hard       | multi_repo             | 3     | 4           | 17       | 179   | -        | -    |
| api-contract-008                        | dependency_management | api_contract           | medium     | large_single           | 1     | 4           | 6        | 149   | -        | -    |
| ccx-dep-trace-106                       | dependency_management | dependency_graph       | hard       | large_single           | 1     | 2           | 0        | 275   | -        | -    |
| dep-traversal-001                       | dependency_management | dependency_graph       | medium     | multi_repo             | 3     | 4           | 8        | 185   | -        | -    |
| dep-traversal-002                       | dependency_management | dependency_graph       | medium     | multi_repo             | 3     | 4           | 6        | 135   | -        | -    |
| dep-traversal-003                       | dependency_management | dependency_graph       | medium     | dual_repo              | 2     | 4           | 7        | 146   | 0.82     | 1.00 |
| dep-traversal-004                       | dependency_management | dependency_graph       | hard       | multi_repo             | 3     | 4           | 9        | 168   | -        | -    |
| dep-traversal-005                       | dependency_management | dependency_graph       | hard       | multi_repo             | 3     | 4           | 9        | 148   | -        | -    |
| dep-traversal-006                       | dependency_management | dependency_graph       | hard       | multi_repo             | 3     | 4           | 8        | 167   | -        | -    |
| dep-traversal-007                       | dependency_management | dependency_graph       | hard       | multi_repo             | 2     | 4           | 6        | 134   | -        | -    |
| dep-traversal-008                       | dependency_management | dependency_graph       | hard       | multi_repo             | 3     | 4           | 6        | 168   | -        | -    |
| dep-traversal-009                       | dependency_management | dependency_graph       | hard       | multi_repo             | 3     | 4           | 5        | 180   | -        | -    |
| dep-traversal-010                       | dependency_management | dependency_graph       | hard       | tri_repo               | 3     | 4           | 6        | 169   | -        | -    |
| dep-traversal-011                       | dependency_management | dependency_graph       | expert     | multi_repo             | 3     | 4           | 9        | 219   | -        | -    |
| dep-traversal-012                       | dependency_management | dependency_graph       | expert     | multi_repo             | 3     | 4           | 11       | 243   | -        | -    |
| aspnetcore-code-review-001              | feature_delivery      | error_provenance       | medium     | large_single           | 1     | 2           | 1        | 439   | -        | -    |
| camel-routing-arch-001                  | feature_delivery      | api_contract           | hard       | large_single           | 1     | 3           | 6        | 255   | -        | -    |
| monorepo-boundary-001                   | feature_delivery      | monorepo_boundary      | medium     | monorepo_cross_package | 1     | 3           | 10       | 197   | -        | -    |
| monorepo-boundary-002                   | feature_delivery      | monorepo_boundary      | expert     | monorepo_cross_package | 1     | 3           | 10       | 183   | -        | -    |
| monorepo-boundary-003                   | feature_delivery      | monorepo_boundary      | hard       | monorepo_cross_package | 1     | 3           | 12       | 177   | 0.72     | 1.00 |
| monorepo-boundary-004                   | feature_delivery      | monorepo_boundary      | hard       | monorepo_cross_package | 1     | 3           | 13       | 169   | -        | -    |
| monorepo-boundary-005                   | feature_delivery      | monorepo_boundary      | expert     | monorepo_cross_package | 1     | 3           | 27       | 205   | -        | -    |
| monorepo-boundary-006                   | feature_delivery      | monorepo_boundary      | hard       | monorepo_cross_package | 1     | 3           | 8        | 159   | -        | -    |
| monorepo-boundary-007                   | feature_delivery      | monorepo_boundary      | hard       | monorepo_cross_package | 1     | 3           | 14       | 169   | -        | -    |
| monorepo-boundary-008                   | feature_delivery      | monorepo_boundary      | hard       | monorepo_cross_package | 1     | 3           | 17       | 198   | -        | -    |
| monorepo-boundary-009                   | feature_delivery      | monorepo_boundary      | expert     | monorepo_cross_package | 1     | 3           | 32       | 192   | -        | -    |
| monorepo-boundary-010                   | feature_delivery      | monorepo_boundary      | hard       | monorepo_cross_package | 1     | 3           | 19       | 222   | -        | -    |
| schema-evolution-001                    | feature_delivery      | db_schema_evolution    | hard       | large_single           | 1     | 4           | 40       | 244   | -        | -    |
| schema-evolution-002                    | feature_delivery      | db_schema_evolution    | hard       | large_single           | 1     | 4           | 23       | 209   | -        | -    |
| schema-evolution-003                    | feature_delivery      | db_schema_evolution    | expert     | large_single           | 1     | 4           | 56       | 244   | -        | -    |
| schema-evolution-004                    | feature_delivery      | db_schema_evolution    | hard       | large_single           | 1     | 4           | 30       | 194   | -        | -    |
| schema-evolution-005                    | feature_delivery      | db_schema_evolution    | expert     | large_single           | 1     | 4           | 41       | 243   | 0.50     | 1.00 |
| schema-evolution-006                    | feature_delivery      | db_schema_evolution    | hard       | large_single           | 1     | 4           | 26       | 196   | -        | -    |
| schema-evolution-007                    | feature_delivery      | db_schema_evolution    | hard       | large_single           | 1     | 4           | 18       | 214   | -        | -    |
| schema-evolution-008                    | feature_delivery      | db_schema_evolution    | hard       | large_single           | 1     | 4           | 27       | 201   | -        | -    |
| schema-evolution-009                    | feature_delivery      | db_schema_evolution    | hard       | large_single           | 1     | 4           | 15       | 209   | -        | -    |
| schema-evolution-010                    | feature_delivery      | db_schema_evolution    | hard       | large_single           | 1     | 4           | 23       | 225   | -        | -    |
| ansible-abc-imports-fix-001             | incident_response     | refactor_orchestration | medium     | large_single           | 1     | 3           | 3        | 292   | -        | -    |
| ansible-galaxy-tar-regression-prove-001 | incident_response     | error_provenance       | hard       | large_single           | 1     | 3           | 3        | 321   | -        | -    |
| ccx-incident-032                        | incident_response     | incident_investigation | hard       | large_single           | 1     | 3           | 11       | 199   | -        | -    |
| incident-investigation-001              | incident_response     | incident_investigation | hard       | large_single           | 1     | 4           | 13       | 286   | -        | -    |
| incident-investigation-002              | incident_response     | incident_investigation | hard       | large_single           | 1     | 4           | 12       | 348   | -        | -    |
| incident-investigation-003              | incident_response     | incident_investigation | hard       | dual_repo              | 2     | 4           | 12       | 329   | -        | -    |
| incident-investigation-004              | incident_response     | incident_investigation | hard       | large_single           | 1     | 4           | 12       | 322   | -        | -    |
| calibration-001                         | platform_engineering  | config_drift           | medium     | calibration            | 1     | 3           | 5        | 166   | -        | -    |
| calibration-002                         | platform_engineering  | config_drift           | medium     | calibration            | 1     | 3           | 5        | 173   | -        | -    |
| config-drift-001                        | platform_engineering  | config_drift           | medium     | large_single           | 1     | 3           | 1        | 188   | -        | -    |
| config-drift-002                        | platform_engineering  | config_drift           | hard       | large_single           | 1     | 3           | 6        | 253   | -        | -    |
| config-drift-003                        | platform_engineering  | config_drift           | hard       | large_single           | 1     | 3           | 3        | 219   | -        | -    |
| config-drift-004                        | platform_engineering  | config_drift           | medium     | large_single           | 1     | 3           | 3        | 244   | -        | -    |
| ccx-compliance-052                      | security_operations   | config_drift           | hard       | large_single           | 1     | 2           | 7        | 186   | -        | -    |
| ccx-compliance-053                      | security_operations   | config_drift           | hard       | large_single           | 1     | 2           | 6        | 184   | -        | -    |
| ceph-rgw-auth-secure-001                | security_operations   | config_drift           | hard       | large_single           | 1     | 3           | 5        | 221   | -        | -    |
| rbac-audit-001                          | security_operations   | incident_investigation | hard       | large_single           | 1     | 4           | 12       | 245   | -        | -    |
| rbac-audit-002                          | security_operations   | incident_investigation | hard       | large_single           | 1     | 4           | 4        | 164   | -        | -    |
| rbac-audit-003                          | security_operations   | incident_investigation | hard       | large_single           | 1     | 4           | 5        | 192   | -        | -    |
| rbac-audit-004                          | security_operations   | incident_investigation | hard       | large_single           | 1     | 4           | 12       | 211   | -        | -    |
| beam-pipeline-builder-refac-001         | technical_debt        | refactor_orchestration | medium     | large_single           | 1     | 3           | 3        | 205   | -        | -    |
| calibration-001                         | technical_debt        | dead_code_necropsy     | medium     | calibration            | 1     | 2           | 12       | 147   | -        | -    |
| calibration-002                         | technical_debt        | dead_code_necropsy     | medium     | calibration            | 1     | 2           | 12       | 130   | -        | -    |
| dead-code-001                           | technical_debt        | dead_code_necropsy     | hard       | large_single           | 1     | 3           | 21       | 239   | 0.41     | 0.96 |
| dead-code-002                           | technical_debt        | dead_code_necropsy     | hard       | large_single           | 1     | 3           | 21       | 235   | -        | -    |
| dead-code-003                           | technical_debt        | dead_code_necropsy     | hard       | large_single           | 1     | 3           | 14       | 186   | -        | -    |
| dead-code-004                           | technical_debt        | dead_code_necropsy     | expert     | large_single           | 1     | 3           | 27       | 220   | -        | -    |
| dead-code-005                           | technical_debt        | dead_code_necropsy     | expert     | large_single           | 1     | 3           | 20       | 253   | -        | -    |
| refactor-orchestration-001              | technical_debt        | refactor_orchestration | medium     | dual_repo              | 2     | 3           | 5        | 137   | -        | -    |
| refactor-orchestration-002              | technical_debt        | refactor_orchestration | medium     | dual_repo              | 2     | 3           | 5        | 130   | -        | -    |
| refactor-orchestration-003              | technical_debt        | refactor_orchestration | hard       | tri_repo               | 3     | 3           | 9        | 137   | 0.62     | 1.00 |
| refactor-orchestration-004              | technical_debt        | refactor_orchestration | hard       | tri_repo               | 3     | 3           | 9        | 135   | -        | -    |
| refactor-orchestration-005              | technical_debt        | refactor_orchestration | hard       | monorepo_cross_package | 1     | 3           | 26       | 147   | -        | -    |
| refactor-orchestration-006              | technical_debt        | refactor_orchestration | hard       | monorepo_cross_package | 1     | 3           | 30       | 102   | -        | -    |
| refactor-orchestration-007              | technical_debt        | refactor_orchestration | expert     | tri_repo               | 3     | 3           | 9        | 162   | -        | -    |
| refactor-orchestration-008              | technical_debt        | refactor_orchestration | expert     | tri_repo               | 3     | 3           | 9        | 171   | -        | -    |

## Flagged Tasks

### calibration-002

- **Difficulty:** medium | **Stratum:** calibration
- **Repos:** 1 | **GT items:** 11 | **Checkpoints:** 3
- **Flags:**
  - medium with 11 GT items (>10) -> probably hard

### calibration-003

- **Difficulty:** medium | **Stratum:** calibration
- **Repos:** 1 | **GT items:** 11 | **Checkpoints:** 3
- **Flags:**
  - medium with 11 GT items (>10) -> probably hard

### calibration-004

- **Difficulty:** medium | **Stratum:** calibration
- **Repos:** 1 | **GT items:** 12 | **Checkpoints:** 3
- **Flags:**
  - medium with 12 GT items (>10) -> probably hard

### ccx-dep-trace-106

- **Difficulty:** hard | **Stratum:** large_single
- **Repos:** 1 | **GT items:** 0 | **Checkpoints:** 2
- **Flags:**
  - hard with 1 repo and 0 GT items (<5) -> review

### dep-traversal-003

- **Difficulty:** medium | **Stratum:** dual_repo
- **Repos:** 2 | **GT items:** 7 | **Checkpoints:** 4
- **Baseline:** 0.82 | **MCP:** 1.00
- **Flags:**
  - baseline score 0.82 > 0.8 -> too easy for medium?

### ansible-galaxy-tar-regression-prove-001

- **Difficulty:** hard | **Stratum:** large_single
- **Repos:** 1 | **GT items:** 3 | **Checkpoints:** 3
- **Flags:**
  - hard with 1 repo and 3 GT items (<5) -> review

### config-drift-003

- **Difficulty:** hard | **Stratum:** large_single
- **Repos:** 1 | **GT items:** 3 | **Checkpoints:** 3
- **Flags:**
  - hard with 1 repo and 3 GT items (<5) -> review

### rbac-audit-002

- **Difficulty:** hard | **Stratum:** large_single
- **Repos:** 1 | **GT items:** 4 | **Checkpoints:** 4
- **Flags:**
  - hard with 1 repo and 4 GT items (<5) -> review

### calibration-001

- **Difficulty:** medium | **Stratum:** calibration
- **Repos:** 1 | **GT items:** 12 | **Checkpoints:** 2
- **Flags:**
  - medium with 12 GT items (>10) -> probably hard

### calibration-002

- **Difficulty:** medium | **Stratum:** calibration
- **Repos:** 1 | **GT items:** 12 | **Checkpoints:** 2
- **Flags:**
  - medium with 12 GT items (>10) -> probably hard

## Summary

- **baseline too easy for label:** 1 tasks
- **hard -> needs review:** 4 tasks
- **medium -> probably hard:** 5 tasks
