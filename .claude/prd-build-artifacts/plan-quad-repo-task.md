# Plan: quad-repo-task

## Scenario: CRI Seccomp Profile Chain Failure

When a pod spec includes a custom seccomp profile, the request flows:

1. **kubernetes kubelet** — parses pod SecurityContext, converts seccomp profile to CRI LinuxContainerSecurityContext
2. **containerd CRI plugin** — receives CRI request, maps seccomp profile spec to OCI runtime spec
3. **runc libcontainer** — reads OCI spec seccomp section, builds BPF filter via libseccomp
4. **moby seccomp package** — provides default seccomp profile and profile loading utilities

A version mismatch or misconfiguration causes containers to fail with cryptic "operation not permitted" errors when a syscall is unexpectedly blocked by seccomp.

## Key Files Per Repo

### kubernetes (v1.33.0-alpha.2)

- `pkg/kubelet/kuberuntime/kuberuntime_container_linux.go` — converts pod seccomp to CRI
- `pkg/kubelet/kuberuntime/security_context.go` — security context handling

### containerd (v1.7.24)

- `pkg/cri/server/container_create_linux.go` — CRI seccomp to OCI spec mapping
- `contrib/seccomp/seccomp_default.go` — default seccomp profile

### runc (v1.2.4)

- `libcontainer/seccomp/seccomp_linux.go` — BPF filter generation from OCI seccomp config
- `libcontainer/specconv/spec_linux.go` — OCI spec conversion

### moby (v28.0.0)

- `profiles/seccomp/seccomp.go` — default profile definition
- `profiles/seccomp/default_linux.go` — default profile JSON

## Checkpoint Design (CRNT-passing)

All weights equal at 0.20 each = 1.00 total.
Removing any single repo loses 0.20 (unique) + 0.20 (cross-repo) = 0.40.
Remaining = 0.60 <= threshold 0.60. PASSES CRNT.

| #   | Name                           | Weight | repo_deps                                    | What it checks                                                   |
| --- | ------------------------------ | ------ | -------------------------------------------- | ---------------------------------------------------------------- |
| 1   | kubelet_seccomp_conversion     | 0.20   | ["kubernetes"]                               | Agent identifies kubelet CRI seccomp profile conversion          |
| 2   | containerd_cri_seccomp_mapping | 0.20   | ["containerd"]                               | Agent traces containerd CRI plugin seccomp handling              |
| 3   | runc_seccomp_filter            | 0.20   | ["runc"]                                     | Agent identifies runc libcontainer seccomp BPF filter generation |
| 4   | moby_default_profile           | 0.20   | ["moby"]                                     | Agent identifies moby default seccomp profile and loading        |
| 5   | cross_repo_error_chain         | 0.20   | ["kubernetes", "containerd", "runc", "moby"] | Agent traces full error propagation across all 4 repos           |

## Implementation Steps

1. Create directory: benchmarks/incident_response/incident-investigation-quad-containerd-001/
2. Create task.toml with 4 repos, 5 checkpoints, proper schema
3. Create instruction.md with realistic enterprise scenario
4. Create checks/ directory with 5 check scripts
5. Create configs/sg_mirrors/incident-investigation-quad-containerd-001.json
6. Add runc v1.2.4 to configs/repo_versions.json
7. Run CRNT validator to verify passes_crnt: true
