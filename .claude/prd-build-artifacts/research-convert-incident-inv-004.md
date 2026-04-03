# Research: convert-incident-inv-004

## Current State

- Single-repo task (moby v28.0.0) tracing Docker daemon shutdown warnings
- difficulty_stratum = "large_single"
- 4 checkpoints: root_cause_identification (0.35), error_chain_trace (0.30), affected_services (0.15), remediation_proposal (0.20)
- No repo_deps on checkpoints
- ground_truth has 3 required_files (all moby), 1 sufficient_file (moby)
- 4 check scripts in checks/ directory, all valid bash, all check /workspace/moby/INCIDENT_REPORT.md
- No checks directory listed by glob (files are there per ls)
- tool_access.expected_mcp_benefit = "medium"

## Containerd Relevance

The task already references containerd shim lifecycle in its description and error chain. The containerd repo has:

- runtime/v2/shim.go — shim v2 runtime (shim lifecycle management)
- pkg/process/exec.go — process execution and exit handling
- services/tasks/local.go — task service handling delete events

Docker v28.0.0 uses containerd v1.7.x series. Pin to v1.7.24.

## Reference: dual-flux-001

- difficulty_stratum = "dual_repo"
- Two [[repos]] entries with role="primary" and role="dependency"
- Checkpoints don't have repo_deps (uses fallback to ground_truth)
- ground_truth.required_files spans both repos
- tool_access.expected_mcp_benefit = "high"

## CRNT Analysis

For CRNT to pass, removing either repo must drop max score <= 0.60.
Plan:

- root_cause_identification (0.35): repo_deps=["moby"] — lost when moby removed
- error_chain_trace (0.30): repo_deps=["moby","containerd"] — lost when either removed
- affected_services (0.15): repo_deps=["moby","containerd"] — lost when either removed
- remediation_proposal (0.20): repo_deps=["moby"] — lost when moby removed

Remove moby: lose all 4 checkpoints → max_score=0.00 (passes, <=0.60)
Remove containerd: lose error_chain_trace + affected_services → max_score=0.35+0.20=0.55 (passes, <=0.60)

Both pass threshold. CRNT will pass with differentiated scores (0.00 vs 0.55).
