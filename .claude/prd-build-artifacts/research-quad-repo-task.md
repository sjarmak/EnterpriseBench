# Research: quad-repo-task

## Key Findings

### Schema Requirements

- `difficulty_stratum` must be one of: calibration, large_single, dual_repo, multi_repo, monorepo_cross_package, tri_repo
- For 4-repo task, use `multi_repo` (no quad_repo enum value)
- Max 5 repos, max 5 checkpoints
- `repo_deps` on checkpoints anchors them to specific repos for CRNT validation
- Required top-level fields: task, repos, checkpoints, artifacts

### CRNT Validator Logic

- Removes each repo one at a time
- Computes max achievable score without that repo (sum of weights of checkpoints NOT depending on that repo)
- Passes if removing ANY single repo drops max score to <= 60% (threshold)
- Uses `repo_deps` field on checkpoints for per-checkpoint anchoring
- If no `repo_deps`, falls back to ground_truth heuristic

### Existing Patterns (from tri-containerd-001 and incident-inv-004)

- task.toml has: difficulty_stratum, mcp_suite, repo_set_id, org_scale, verification_modes at top level
- Repos have url, rev, path, role fields
- Check scripts: bash, set -euo pipefail, output JSON with score/passed/reason
- SG mirror config: JSON with task_id and mirrors array

### Repo Versions Already Pinned

- kubernetes/kubernetes: v1.33.0-alpha.2 (present)
- containerd/containerd: v1.7.24 (present)
- opencontainers/runc: v1.1.10 (present, need to ADD v1.2.4)
- moby/moby: v28.0.0 (present)

### CRNT Strategy for 4 Repos

With 4 repos and up to 5 checkpoints, need each repo uniquely represented:

- Checkpoint 1: kubelet CRI seccomp handling (repo_deps: ["kubernetes"])
- Checkpoint 2: containerd CRI seccomp processing (repo_deps: ["containerd"])
- Checkpoint 3: runc seccomp filter application (repo_deps: ["runc"])
- Checkpoint 4: moby seccomp defaults/profile (repo_deps: ["moby"])
- Checkpoint 5: cross-repo error chain (repo_deps: all 4)

Weights: 0.25 + 0.25 + 0.25 + 0.15 + 0.10 = 1.0
Removing any single repo: loses its unique checkpoint + the cross-repo one.

- Remove kubernetes: lose 0.25 + 0.10 = 0.35, max remaining = 0.65 > 0.60 -- FAILS
  Need to adjust. Let me use: 0.25 + 0.25 + 0.25 + 0.25 = 1.0 with 4 checkpoints, each anchored to unique repos plus cross-deps.

Better strategy with 5 checkpoints:

- CP1 (0.25): kubernetes only
- CP2 (0.25): containerd only
- CP3 (0.25): runc only
- CP4 (0.15): moby only
- CP5 (0.10): kubernetes, containerd, runc, moby (all)

Remove kubernetes: lose CP1(0.25) + CP5(0.10) = 0.35, remaining = 0.65 > 0.60 FAIL

Need more weight on cross-repo or redistribute:

- CP1 (0.20): kubernetes only
- CP2 (0.20): containerd only
- CP3 (0.20): runc only
- CP4 (0.20): moby only
- CP5 (0.20): all repos

Remove any single: lose 0.20 + 0.20 = 0.40, remaining = 0.60 <= 0.60 PASS
