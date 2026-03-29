# Verifier Testing Report

Generated: 2026-03-29 18:34:06 UTC

## Summary

| Metric | Count |
|--------|-------|
| Total check runs | 105 |
| Passed | 105 |
| Failed (wrong score) | 0 |
| Crashed (exit > 1) | 0 |
| Invalid JSON output | 0 |

## Detailed Results

| Task | Check | Tier | Exit | Valid JSON | Score | Passed | Status |
|------|-------|------|------|------------|-------|--------|--------|
| err-provenance-01 | check_error_chain | good | 0 | yes | 1.0 | True | OK |
| err-provenance-01 | check_error_source | good | 0 | yes | 1.0 | True | OK |
| err-provenance-01 | check_trigger_conditions | good | 0 | yes | 1.0 | True | OK |
| support-mapping-001 | check_code_paths | good | 0 | yes | 0.9 | True | OK |
| support-mapping-001 | check_ownership | good | 0 | yes | 1.0 | True | OK |
| support-mapping-001 | check_related_issues | good | 0 | yes | 1.0 | True | OK |
| support-mapping-001 | check_severity | good | 0 | yes | 1.0 | True | OK |
| monorepo-boundary-001 | check_affected_packages | good | 0 | yes | 1.0 | True | OK |
| monorepo-boundary-001 | check_boundary_violations | good | 0 | yes | 1.0 | True | OK |
| monorepo-boundary-001 | check_impact_classification | good | 0 | yes | 1.0 | True | OK |
| dep-traversal-001 | check_cve_id | good | 0 | yes | 1.0 | True | OK |
| dep-traversal-001 | check_direct_deps | good | 0 | yes | 1.0 | True | OK |
| dep-traversal-001 | check_transitive_paths | good | 0 | yes | 1.0 | True | OK |
| dep-traversal-001 | check_version_analysis | good | 0 | yes | 1.0 | True | OK |
| schema-evolution-001 | check_direct_refs | good | 0 | yes | 1.0 | True | OK |
| schema-evolution-001 | check_indirect_refs | good | 0 | yes | 1.0 | True | OK |
| schema-evolution-001 | check_schema_change | good | 0 | yes | 1.0 | True | OK |
| schema-evolution-001 | check_test_impact | good | 0 | yes | 1.0 | True | OK |
| api-contract-001 | check_classification | good | 0 | yes | 1.0 | True | OK |
| api-contract-001 | check_direct_consumers | good | 0 | yes | 1.0 | True | OK |
| api-contract-001 | check_source_identification | good | 0 | yes | 1.0 | True | OK |
| api-contract-001 | check_transitive_impact | good | 0 | yes | 1.0 | True | OK |
| refactor-orchestration-001 | check_parallelism | good | 0 | yes | 0.8 | True | OK |
| refactor-orchestration-001 | check_repo_set | good | 0 | yes | 1.0 | True | OK |
| refactor-orchestration-001 | check_topo_order | good | 0 | yes | 2.0 | True | OK |
| dead-code-001 | check_dead_code | good | 0 | yes | 0.8889 | N/A | OK |
| dead-code-001 | check_evidence | good | 0 | yes | 1.0 | N/A | OK |
| dead-code-001 | check_feature_flags | good | 0 | yes | 1.0 | N/A | OK |
| incident-investigation-001 | check_affected_services | good | 0 | yes | 1.0 | True | OK |
| incident-investigation-001 | check_error_chain | good | 0 | yes | 1.0 | True | OK |
| incident-investigation-001 | check_remediation | good | 0 | yes | 1.0 | True | OK |
| incident-investigation-001 | check_root_cause | good | 0 | yes | 1.0 | True | OK |
| config-drift-001 | check_config_valid | good | 0 | yes | 1.0 | True | OK |
| config-drift-001 | check_drift_points | good | 0 | yes | 1.0 | True | OK |
| config-drift-001 | check_expected_values | good | 0 | yes | 1.0 | True | OK |
| err-provenance-01 | check_error_chain | partial | 0 | yes | 0.17 | False | OK |
| err-provenance-01 | check_error_source | partial | 0 | yes | 0.5 | True | OK |
| err-provenance-01 | check_trigger_conditions | partial | 0 | yes | 0.0 | False | OK |
| support-mapping-001 | check_code_paths | partial | 0 | yes | 0.17 | False | OK |
| support-mapping-001 | check_ownership | partial | 0 | yes | 0.0 | False | OK |
| support-mapping-001 | check_related_issues | partial | 0 | yes | 0.0 | False | OK |
| support-mapping-001 | check_severity | partial | 0 | yes | 0.6 | True | OK |
| monorepo-boundary-001 | check_affected_packages | partial | 0 | yes | 0.5 | False | OK |
| monorepo-boundary-001 | check_boundary_violations | partial | 0 | yes | 0.0 | False | OK |
| monorepo-boundary-001 | check_impact_classification | partial | 0 | yes | 0.0 | False | OK |
| dep-traversal-001 | check_cve_id | partial | 0 | yes | 0.5 | False | OK |
| dep-traversal-001 | check_direct_deps | partial | 0 | yes | 0.33 | False | OK |
| dep-traversal-001 | check_transitive_paths | partial | 0 | yes | 0.33 | False | OK |
| dep-traversal-001 | check_version_analysis | partial | 0 | yes | 0.0 | False | OK |
| schema-evolution-001 | check_direct_refs | partial | 0 | yes | 0.5 | False | OK |
| schema-evolution-001 | check_indirect_refs | partial | 0 | yes | 0.0 | False | OK |
| schema-evolution-001 | check_schema_change | partial | 0 | yes | 0.5 | False | OK |
| schema-evolution-001 | check_test_impact | partial | 0 | yes | 0.25 | False | OK |
| api-contract-001 | check_classification | partial | 0 | yes | 0.0 | False | OK |
| api-contract-001 | check_direct_consumers | partial | 0 | yes | 0.25 | False | OK |
| api-contract-001 | check_source_identification | partial | 0 | yes | 0.67 | False | OK |
| api-contract-001 | check_transitive_impact | partial | 0 | yes | 0.0 | False | OK |
| refactor-orchestration-001 | check_parallelism | partial | 0 | yes | 1.0 | True | OK |
| refactor-orchestration-001 | check_repo_set | partial | 0 | yes | 1.0 | True | OK |
| refactor-orchestration-001 | check_topo_order | partial | 0 | yes | 0.0 | False | OK |
| dead-code-001 | check_dead_code | partial | 0 | yes | 0.25 | N/A | OK |
| dead-code-001 | check_evidence | partial | 0 | yes | 1.0 | N/A | OK |
| dead-code-001 | check_feature_flags | partial | 0 | yes | 0.0 | N/A | OK |
| incident-investigation-001 | check_affected_services | partial | 0 | yes | 0.67 | True | OK |
| incident-investigation-001 | check_error_chain | partial | 0 | yes | 0.75 | True | OK |
| incident-investigation-001 | check_remediation | partial | 0 | yes | 0.0 | False | OK |
| incident-investigation-001 | check_root_cause | partial | 0 | yes | 0.33 | False | OK |
| config-drift-001 | check_config_valid | partial | 0 | yes | 1.0 | True | OK |
| config-drift-001 | check_drift_points | partial | 0 | yes | 0.5 | False | OK |
| config-drift-001 | check_expected_values | partial | 0 | yes | 0.5 | True | OK |
| err-provenance-01 | check_error_chain | empty | 1 | yes | 0.0 | False | OK |
| err-provenance-01 | check_error_source | empty | 1 | yes | 0.0 | False | OK |
| err-provenance-01 | check_trigger_conditions | empty | 1 | yes | 0.0 | False | OK |
| support-mapping-001 | check_code_paths | empty | 1 | yes | 0.0 | False | OK |
| support-mapping-001 | check_ownership | empty | 1 | yes | 0.0 | False | OK |
| support-mapping-001 | check_related_issues | empty | 1 | yes | 0.0 | False | OK |
| support-mapping-001 | check_severity | empty | 1 | yes | 0.0 | False | OK |
| monorepo-boundary-001 | check_affected_packages | empty | 0 | yes | 0.0 | False | OK |
| monorepo-boundary-001 | check_boundary_violations | empty | 0 | yes | 0.0 | False | OK |
| monorepo-boundary-001 | check_impact_classification | empty | 0 | yes | 0.0 | False | OK |
| dep-traversal-001 | check_cve_id | empty | 0 | yes | 0.0 | False | OK |
| dep-traversal-001 | check_direct_deps | empty | 0 | yes | 0.0 | False | OK |
| dep-traversal-001 | check_transitive_paths | empty | 0 | yes | 0.0 | False | OK |
| dep-traversal-001 | check_version_analysis | empty | 0 | yes | 0.0 | False | OK |
| schema-evolution-001 | check_direct_refs | empty | 0 | yes | 0.0 | False | OK |
| schema-evolution-001 | check_indirect_refs | empty | 0 | yes | 0.0 | False | OK |
| schema-evolution-001 | check_schema_change | empty | 0 | yes | 0.0 | False | OK |
| schema-evolution-001 | check_test_impact | empty | 0 | yes | 0.0 | False | OK |
| api-contract-001 | check_classification | empty | 0 | yes | 0.0 | False | OK |
| api-contract-001 | check_direct_consumers | empty | 0 | yes | 0.0 | False | OK |
| api-contract-001 | check_source_identification | empty | 0 | yes | 0.0 | False | OK |
| api-contract-001 | check_transitive_impact | empty | 0 | yes | 0.0 | False | OK |
| refactor-orchestration-001 | check_parallelism | empty | 0 | yes | 0.0 | False | OK |
| refactor-orchestration-001 | check_repo_set | empty | 0 | yes | 0.0 | False | OK |
| refactor-orchestration-001 | check_topo_order | empty | 0 | yes | 0.0 | False | OK |
| dead-code-001 | check_dead_code | empty | 0 | yes | 0.0 | N/A | OK |
| dead-code-001 | check_evidence | empty | 0 | yes | 0.0 | N/A | OK |
| dead-code-001 | check_feature_flags | empty | 0 | yes | 0.0 | N/A | OK |
| incident-investigation-001 | check_affected_services | empty | 0 | yes | 0.0 | False | OK |
| incident-investigation-001 | check_error_chain | empty | 0 | yes | 0.0 | False | OK |
| incident-investigation-001 | check_remediation | empty | 0 | yes | 0.0 | False | OK |
| incident-investigation-001 | check_root_cause | empty | 0 | yes | 0.0 | False | OK |
| config-drift-001 | check_config_valid | empty | 0 | yes | 0.0 | False | OK |
| config-drift-001 | check_drift_points | empty | 0 | yes | 0.0 | False | OK |
| config-drift-001 | check_expected_values | empty | 0 | yes | 0.0 | False | OK |


## Methodology

For each of the 10 task types, one representative task was tested:
- **err-provenance-01** (error_provenance)
- **support-mapping-001** (support_code_mapping)
- **monorepo-boundary-001** (monorepo_boundary)
- **dep-traversal-001** (dependency_graph)
- **schema-evolution-001** (db_schema_evolution)
- **api-contract-001** (api_contract)
- **refactor-orchestration-001** (refactor_orchestration)
- **dead-code-001** (dead_code_necropsy)
- **incident-investigation-001** (incident_investigation)
- **config-drift-001** (config_drift)

Three tiers of agent output were tested:
1. **good** — Ground-truth-matching output with all expected fields
2. **partial** — Half-right output with incomplete data
3. **empty** — No output files at all

Scoring expectations:
- Good tier: score >= 0.5
- Empty tier: score <= 0.1
- Partial tier: any score (informational)

## Issues Found

No issues found. All verifier scripts produce valid JSON, correct exit codes, and reasonable scores.
