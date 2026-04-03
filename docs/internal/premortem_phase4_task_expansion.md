# Premortem: Phase 4 — Task Expansion

## Risk Registry

| #   | Failure Lens             | Severity | Likelihood | Score | Root Cause                                            |
| --- | ------------------------ | -------- | ---------- | ----- | ----------------------------------------------------- |
| 1   | Technical Architecture   | Critical | High       | 12    | Timeout/turns calibrated on small repos only          |
| 2   | Integration & Dependency | Critical | High       | 12    | No version-pinning or health checks for external deps |
| 3   | Operational              | Critical | High       | 12    | No disk budget or resource monitoring for large repos |
| 4   | Scope & Requirements     | Critical | High       | 12    | "Meaningful spread" never operationalized             |
| 5   | Scale & Evolution        | Critical | High       | 12    | Filesystem-only state with no run lifecycle tracking  |

## Cross-Cutting Themes

### A. Small-repo calibration doesn't predict large-repo behavior (Lenses 1, 3, 5)

Calibration used Flask/Click/Requests (8-15MB). Untested tasks use Django/Kubernetes/Next.js (500MB-2GB). 30-200x gap affects timeout, disk, memory, clone time, turn budget.

### B. No infra-error vs agent-error distinction (Lenses 1, 2, 3)

Score of 0.0 is ambiguous — could be bad agent OR disk full, token expired, MCP 429. Silently corrupts data.

### C. Checkpoints test format, not retrieval quality (Lens 4)

Verifiers check structural validity. Agent could hallucinate plausible output and score well. Existential threat to benchmark thesis.

## Required Mitigations (before launching Phase 4)

### M1. Graduated pilot (10 tasks, not 45)

- 1 task per task type, spanning repo-size tiers
- Instrument: clone time, turns consumed, disk usage, memory
- Set per-stratum timeout/turn parameters from data
- Cost: Low | Addresses: Tech, Ops, Scope

### M2. Infrastructure error tracking in results.json

- Add failure_class field: null | agent | infra_timeout | infra_disk | infra_auth | infra_clone
- Auto-requeue infra failures
- Cost: Low | Addresses: Tech, Deps, Ops

### M3. Disk and resource pre-flight

- Check available disk > 2x estimated repo size before launch
- Maintain repo-size manifest
- Cap concurrent large-repo tasks at 3
- Cost: Low | Addresses: Tech, Ops

### M4. Construct validity audit (6 untested task types)

- For each untested type, verify 1 checkpoint requires reading specific source files
- Create gold + fool's-gold test cases
- Cost: Medium | Addresses: Scope

### M5. Pin external dependencies

- Pin Claude CLI to exact npm version in Dockerfile
- Add mirrors.json indirection for sg-evals repos
- MCP endpoint health check before MCP-mode runs
- Cost: Low | Addresses: Deps

## Recommended Execution Order

1. Implement M2 + M3 (infra error tracking + disk pre-flight) — 1 session
2. Implement M1 (graduated pilot of 10 tasks) — uses M2/M3, produces data for M4
3. Review pilot results, set per-stratum parameters
4. Implement M4 (spot-check 6 untested task types) — parallel with parameter tuning
5. Implement M5 (pin deps) — parallel with above
6. Run remaining ~35 tasks with mitigations in place

## Full Failure Narratives

(See agent outputs for complete narratives per lens)
