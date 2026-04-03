# Test Results: Multi-Repo Incident Investigation Tasks

## Acceptance Criteria Verification

| #   | Criterion                                                                                          | Status |
| --- | -------------------------------------------------------------------------------------------------- | ------ |
| 1   | 5 task directories exist under benchmarks/incident_response/                                       | PASS   |
| 2   | Each directory has task.toml, ground_truth.json, instruction.md, checks/ with 4 scripts            | PASS   |
| 3   | difficulty_stratum = dual_repo/tri_repo, task_type = incident_investigation, session_type = single | PASS   |
| 4   | Real GitHub repos with actual release tags in [[repos]]                                            | PASS   |
| 5   | 4 checkpoints per task, weights sum to 1.00                                                        | PASS   |
| 6   | [ground_truth] required_files from 2+ repos                                                        | PASS   |
| 7   | 4 of 5 tasks use investigate pattern (>= 3 required)                                               | PASS   |
| 8   | ground_truth.json has task_id, task_type, repos, required_files, expected_answer                   | PASS   |

## Task Summary

| Task                                       | Stratum   | Pattern     | Repos                                                 | Checkpoints |
| ------------------------------------------ | --------- | ----------- | ----------------------------------------------------- | ----------- |
| incident-investigation-dual-istio-001      | dual_repo | investigate | istio/istio, envoyproxy/envoy                         | 4 (1.00)    |
| incident-investigation-dual-prometheus-001 | dual_repo | investigate | prometheus/prometheus, prometheus/alertmanager        | 4 (1.00)    |
| incident-investigation-tri-containerd-001  | tri_repo  | investigate | moby/moby, containerd/containerd, opencontainers/runc | 4 (1.00)    |
| incident-investigation-dual-kafka-001      | dual_repo | investigate | apache/kafka, confluentinc/kafka-connect-jdbc         | 4 (1.00)    |
| incident-investigation-dual-flux-001       | dual_repo | enforce     | fluxcd/flux2, fluxcd/helm-controller                  | 4 (1.00)    |

## Result: ALL PASS
