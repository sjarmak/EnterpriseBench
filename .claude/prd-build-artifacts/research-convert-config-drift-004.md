# Research: convert-config-drift-004

## Current State

- **task.toml**: Single-repo (argo-cd only), difficulty_stratum="large_single", 3 checkpoints (identify_drift_points 0.40, determine_expected_values 0.35, validate_corrected_config 0.25)
- **instruction.md**: References "upstream redis-ha chart defaults (built into the dependency)" but only has argo-cd repo
- **ground_truth.json**: References PR #22035 and issue #22034 in argoproj/argo-cd
- **Check scripts**: 3 shell scripts checking DRIFT_REPORT.json for securityContext, null values, helm version sensitivity, and corrected config
- No repo_deps on any checkpoint currently

## Target Upstream Repo

- `dandydeveloper/charts` pinned at `redis-ha-4.26.6` in configs/repo_versions.json (verified 2026-04-03)
- Contains `charts/redis-ha/values.yaml` (upstream defaults), `charts/redis-ha/Chart.yaml`, `charts/redis-ha/templates/`
- This is the actual upstream source for the redis-ha Helm chart that ArgoCD bundles

## Dual-Repo Reference (incident-investigation-dual-flux-001)

- difficulty_stratum = "dual_repo"
- Two [[repos]] entries with role="primary" and role="dependency"
- No repo_deps on checkpoints (uses ground_truth fallback heuristic)
- ground_truth.required_files references both repos

## CRNT Validator

- Checks that removing ANY single repo drops max score <= 60%
- Per-checkpoint anchoring: if checkpoint has repo_deps, uses those; otherwise falls back to ground_truth.required_files repos
- For passes_crnt=true, need at least one checkpoint anchored only to argo-cd AND at least one anchored to dandydeveloper-charts (or both)

## Key Design Decision

- identify_drift_points (0.40): Only needs argo-cd (drift is in ArgoCD's values.yaml)
- determine_expected_values (0.35): Needs both repos (compare upstream defaults vs ArgoCD overrides)
- validate_corrected_config (0.25): Needs both repos (validation needs upstream reference)

With this setup:

- Remove argo-cd → lose all 3 checkpoints (score=0.0) ✓
- Remove dandydeveloper-charts → lose determine_expected_values + validate_corrected_config (score=0.40) ✓
- Both below 0.60 threshold → passes CRNT
