# Test: single-repo-retirement

## Results

| Check                                    | Result                        |
| ---------------------------------------- | ----------------------------- |
| Tasks moved to \_archived                | 28 (PASS, >= 20 required)     |
| Total active tasks                       | 112                           |
| Strict multi-repo (dual+tri+multi)       | 57                            |
| Multi-repo percentage                    | 50.9% (PASS, >= 45% required) |
| Archived IDs in sweep_manifest.json      | 0 (PASS)                      |
| Archived IDs in validation_registry.json | 0 (PASS)                      |

## Per-type verification (no type below calibration + multi-repo count)

| Task Type              | Active | large_single | calibration | multi-repo | cal+multi | Status |
| ---------------------- | ------ | ------------ | ----------- | ---------- | --------- | ------ |
| support_code_mapping   | 11     | 4            | 4           | 3          | 7         | PASS   |
| error_provenance       | 14     | 4            | 5           | 5          | 10        | PASS   |
| db_schema_evolution    | 7      | 4            | 0           | 3          | 3         | PASS   |
| incident_investigation | 12     | 5            | 1           | 6          | 7         | PASS   |
| config_drift           | 11     | 5            | 2           | 4          | 6         | PASS   |
| dead_code_necropsy     | 8      | 3            | 2           | 3          | 5         | PASS   |
| api_contract           | 12     | 3            | 0           | 9          | 9         | PASS   |
| dependency_graph       | 16     | 1            | 0           | 15         | 15        | PASS   |
| monorepo_boundary      | 10     | 0            | 0           | 10         | 10        | PASS   |
| refactor_orchestration | 11     | 0            | 0           | 11         | 11        | PASS   |

## Verdict: ALL CHECKS PASS
