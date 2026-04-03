# Research: single-repo-retirement

## Current State

- 140 total active tasks
- Strict multi-repo (dual+tri+multi): 28+16+13 = 57 (40.7%)
- Target: >= 45%

## Distribution by task_type (large_single | calibration | multi-repo)

| Task Type              | large_single | calibration | dual | tri | multi | monorepo | total |
| ---------------------- | ------------ | ----------- | ---- | --- | ----- | -------- | ----- |
| support_code_mapping   | 12           | 4           | 3    | 0   | 0     | 0        | 19    |
| error_provenance       | 11           | 5           | 5    | 0   | 0     | 0        | 21    |
| db_schema_evolution    | 10           | 0           | 2    | 1   | 0     | 0        | 13    |
| incident_investigation | 8            | 1           | 5    | 1   | 0     | 0        | 15    |
| config_drift           | 7            | 2           | 3    | 1   | 0     | 0        | 13    |
| dead_code_necropsy     | 5            | 2           | 3    | 0   | 0     | 0        | 10    |
| api_contract           | 3            | 0           | 4    | 2   | 3     | 0        | 12    |
| dependency_graph       | 1            | 0           | 1    | 4   | 9     | 0        | 15    |
| monorepo_boundary      | 0            | 0           | 0    | 0   | 0     | 10       | 10    |
| refactor_orchestration | 0            | 0           | 2    | 8   | 0     | 2        | 12    |

## Config files

- `configs/sweep_manifest.json`: Contains task IDs in run configurations (6 runs each)
- `configs/validation_registry.json`: Contains one entry per task

## Notes

- Some tasks live in unexpected suites (config_drift in security_operations, incident_investigation in security_operations)
- incident_investigation has 8 large_single (4 incident-investigation + 4 rbac-audit)
- config_drift has 7 large_single (4 config-drift + 3 in security_operations)
- error_provenance has 11 large_single (10 err-provenance + 1 ansible-galaxy)
