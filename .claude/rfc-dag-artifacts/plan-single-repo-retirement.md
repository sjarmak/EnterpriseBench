# Plan: single-repo-retirement

## Tasks to Archive (28 total)

### support_code_mapping: CUT 8 (keep 4 of 12 large_single)

1. customer_escalation/support-mapping-005
2. customer_escalation/support-mapping-006
3. customer_escalation/support-mapping-007
4. customer_escalation/support-mapping-008
5. customer_escalation/support-mapping-009
6. customer_escalation/support-mapping-010
7. customer_escalation/support-mapping-011
8. customer_escalation/support-mapping-012

### error_provenance: CUT 7 (keep 4 of 11 large_single)

9. customer_escalation/err-provenance-04
10. customer_escalation/err-provenance-05
11. customer_escalation/err-provenance-06
12. customer_escalation/err-provenance-07
13. customer_escalation/err-provenance-08
14. customer_escalation/err-provenance-09
15. customer_escalation/err-provenance-010

### db_schema_evolution: CUT 6 (keep 4 of 10 large_single)

16. feature_delivery/schema-evolution-005
17. feature_delivery/schema-evolution-006
18. feature_delivery/schema-evolution-007
19. feature_delivery/schema-evolution-008
20. feature_delivery/schema-evolution-009
21. feature_delivery/schema-evolution-010

### incident_investigation: CUT 3 (keep 5 of 8 large_single)

22. security_operations/rbac-audit-002
23. security_operations/rbac-audit-003
24. security_operations/rbac-audit-004

### config_drift: CUT 2 (keep 5 of 7 large_single)

25. security_operations/ccx-compliance-052
26. security_operations/ccx-compliance-053

### dead_code_necropsy: CUT 2 (keep 3 of 5 large_single)

27. technical_debt/dead-code-004
28. technical_debt/dead-code-005

## Post-archive projection

- Active: 140 - 28 = 112
- Strict multi-repo: 57 (unchanged)
- Percentage: 57/112 = 50.9% (>= 45% target)

## Config cleanup needed

- sweep_manifest.json: remove references to 17 tasks (schema-evolution 005-010, rbac-audit 002-004, ccx-compliance 052-053, dead-code 004-005)
- validation_registry.json: remove entries for all 28 archived tasks
