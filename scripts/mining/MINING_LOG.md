# Task Mining Log

## Overview

Mining session conducted 2026-03-28 investigating 3 dependency chains for verifiable benchmark tasks.

## Chain 1: grpc-go -> etcd (Go)

### Candidates Found: 2

**Candidate 1.1: grpc-go v1.27.0 balancer/resolver API removal** (HIGH confidence)
- **Upstream**: grpc-go v1.27.0 removed backward-compat type aliases (resolver.BuildOption, resolver.ResolveNowOption, balancer.PickOptions)
- **Downstream**: etcd v3.4.7 clientv3 failed to compile
- **Fix**: PR #11564, commit 4258cdd2, released in etcd v3.4.8
- **Scope**: 4 files in clientv3/balancer/
- **Verdict**: VIABLE — clean, well-scoped, self-contained fix with clear before/after states
- **Generated**: `benchmarks/mined/dep-mgmt-grpc-go-balancer-001.toml`

**Candidate 1.2: grpc-go v1.32.0 naming interface removal** (MEDIUM confidence)
- **Upstream**: grpc-go v1.32.0 removed naming interface entirely
- **Downstream**: etcd required complete rewrite of custom balancer (PR #12671)
- **Scope**: Entire clientv3/balancer/ package replaced with upstream grpc solution
- **Verdict**: BORDERLINE — fix is a full rewrite, not a targeted migration. Could work as an "expert" difficulty task but may be too open-ended for reliable verification.

### Rejected Candidates
- **etcd protobuf v1.4.0 panic** (issue #12197): Triggered by transitive dependency, not a direct API change. Hard to reproduce deterministically.
- **grpc-gateway v2 migration** (issue #14499): Involves 3 repos (grpc-gateway, grpc-go, etcd) and is more of a long-running migration than a single breaking change.

## Chain 2: urllib3 -> requests (Python)

### Candidates Found: 2

**Candidate 2.1: urllib3 2.0.0 breaking requests version pin** (HIGH confidence)
- **Upstream**: urllib3 2.0.0 major version bump (April 2023)
- **Downstream**: requests v2.28.2 had hard pin `urllib3<1.27`, excluding 2.0 entirely
- **Fix**: requests v2.30.0 (commit 2ad18e0e), multiple PRs contributing
- **Scope**: setup.cfg version pin + adapters.py/compat.py/models.py API updates
- **Verdict**: VIABLE — well-documented, ecosystem-wide breakage. Fix involves version pin update plus API compatibility changes.
- **Generated**: `benchmarks/mined/dep-mgmt-urllib3-requests-001.toml`

**Candidate 2.2: urllib3 2.0.0 breaking botocore** (MEDIUM confidence)
- **Upstream**: same urllib3 2.0.0
- **Downstream**: botocore had vendored urllib3 copy + hard pin
- **Fix**: Took many months, involved de-vendoring
- **Verdict**: NOT VIABLE for single task — fix was spread across many PRs over months. The de-vendoring is architecturally complex and not a clean breaking-change-fix pattern.

### Rejected Candidates
- **urllib3 2.0 control character handling** (issue #3053): Subtle behavioral change, not a compile/import error. Hard to write deterministic verification.
- **urllib3 2.0 partial response regression** (issue #3009): Bug in urllib3 itself, not a downstream adaptation task.

## Chain 3: ESLint -> typescript-eslint (TypeScript)

### Candidates Found: 1

**Candidate 3.1: ESLint v10 addGlobals() requirement** (HIGH confidence)
- **Upstream**: ESLint v10.0.0 (Feb 2026) requires ScopeManager.addGlobals()
- **Downstream**: typescript-eslint v8.x scope manager lacks the method, crashes immediately
- **Fix**: PR #11914 (commit 607c9c9f), merged Jan 2026
- **Scope**: 3 files in packages/scope-manager/src/
- **Verdict**: VIABLE — clean port of addGlobals from eslint-scope to typescript-eslint. Requires understanding scope manager internals but fix is well-contained.
- **Generated**: `benchmarks/mined/dep-mgmt-eslint-scope-001.toml`

### Rejected Candidates
- **ESLint v9 flat config migration**: Not a breaking API change to typescript-eslint directly — it's a config format change. Tasks would test config migration, not code fixing.
- **typescript-eslint v7 dropping Node 16**: Version requirement change, not a code-level breaking change to investigate.

## Summary Statistics

| Metric | Count |
|--------|-------|
| Chains investigated | 3 |
| Total candidates found | 5 |
| High confidence (viable) | 3 |
| Medium confidence (borderline) | 2 |
| Rejected (not viable) | 6 additional candidates investigated but rejected |
| Tasks generated | 3 |

### Hit Rate
- **Candidates per chain**: ~1.7 (5 total / 3 chains)
- **Viable tasks per chain**: 1.0 (3 viable / 3 chains)
- **Candidate-to-task conversion**: 60% (3/5)

### Reasons Candidates Failed
1. **Fix too broad**: Full rewrites rather than targeted fixes (grpc-go v1.32 balancer rewrite, botocore de-vendoring)
2. **Not deterministically reproducible**: Behavioral changes that don't cause compile/test failures predictably
3. **Multi-PR fix**: Fix spread across many PRs over months, no single ground truth commit
4. **Transitive dependency issue**: Breaking change comes through indirect dependency, hard to pin exact state

### Time Estimate
- **Research per chain**: ~30-45 minutes (searching issues, releases, understanding the change)
- **Validation per candidate**: ~15-20 minutes (checking scope, fix quality, revisions)
- **Task generation per viable candidate**: ~15-20 minutes (writing prompt, defining checkpoints)
- **Total per viable task**: ~1.5-2 hours

### Projection for 80-100 Tasks
At 1 viable task per chain investigated and ~2 hours per task:
- Need ~80-100 dependency chains to investigate
- Estimated 160-200 hours of expert effort
- With tooling improvements (automated GitHub search, candidate pre-filtering): estimate 100-130 hours
- Parallelizable across multiple researchers

### Note on Suite Coverage
All 3 mined tasks are `dependency_management` suite. Other suites (incident_response, platform_engineering, etc.) require different mining approaches:
- **Incident response**: Mine from production incident postmortems in OSS projects
- **Platform engineering**: Mine from CI/CD migration PRs (e.g., Travis -> GitHub Actions)
- **Security operations**: Mine from CVE fix commits and security advisories
- **Feature delivery**: Mine from RFC/proposal -> implementation PRs

Each suite likely needs its own mining strategy, though the pipeline structure (discover -> validate -> generate) remains the same.
