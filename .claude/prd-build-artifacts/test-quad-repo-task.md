# Test Results: quad-repo-task

## CRNT Validator

- **Status**: PASS
- **Command**: `python3 scripts/validation/crnt_validator.py benchmarks/incident_response/incident-investigation-quad-containerd-001/task.toml --json`
- **passes_crnt**: true
- All 4 repos pass threshold (removing any drops max score to 0.54, threshold is 0.60)
- Each repo has unique checkpoint + shares cross_repo_error_chain checkpoint

## Ablation Details

| Removed Repo | Max Score Without | Lost Checkpoints                                       | Passes |
| ------------ | ----------------- | ------------------------------------------------------ | ------ |
| kubernetes   | 0.54              | kubelet_seccomp_conversion, cross_repo_error_chain     | true   |
| containerd   | 0.54              | containerd_cri_seccomp_mapping, cross_repo_error_chain | true   |
| runc         | 0.54              | runc_seccomp_filter, cross_repo_error_chain            | true   |
| moby         | 0.54              | moby_default_profile, cross_repo_error_chain           | true   |

## Task Mix Validator

- Task counted in multi_repo stratum (now 13 multi-repo tasks, 62 strict multi-repo total)
- Pre-existing FAIL on Go ecosystem > 40% is not caused by this change

## Checkpoint Weights

- 0.18 + 0.18 + 0.18 + 0.18 + 0.28 = 1.00

## Files Created

- benchmarks/incident_response/incident-investigation-quad-containerd-001/task.toml
- benchmarks/incident_response/incident-investigation-quad-containerd-001/instruction.md
- benchmarks/incident_response/incident-investigation-quad-containerd-001/checks/check_kubelet_seccomp.sh
- benchmarks/incident_response/incident-investigation-quad-containerd-001/checks/check_containerd_seccomp.sh
- benchmarks/incident_response/incident-investigation-quad-containerd-001/checks/check_runc_seccomp.sh
- benchmarks/incident_response/incident-investigation-quad-containerd-001/checks/check_moby_seccomp.sh
- benchmarks/incident_response/incident-investigation-quad-containerd-001/checks/check_error_chain.sh
- configs/sg_mirrors/incident-investigation-quad-containerd-001.json

## Files Modified

- configs/repo_versions.json (added runc v1.2.4)
