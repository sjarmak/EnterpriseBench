# Sandbox Measurements

Validated: 2026-03-28

## Test Task

- **Task**: `dep-mgmt-grpc-go-balancer-001`
- **Repos**: 2 (grpc-go v1.27.0, etcd v3.4.7)
- **Base image**: `golang:1.21-bookworm`
- **Session type**: single

## Build Results

| Metric | Value |
|--------|-------|
| Build time | ~8.7s |
| Image size (total) | 869 MB |
| Workspace size | 49 MB |
| grpc-go clone | 5.9 MB |
| etcd clone | 43 MB |
| health_check.sh | PASS |

## Breakdown

- **Image size** is dominated by the base image (`golang:1.21-bookworm` ~820MB). The workspace repos add ~49MB.
- **Workspace is well under the 100MB target** for a 2-repo case (49MB total).
- `--depth 1` shallow clones keep repo sizes minimal.
- Build is fast (~9s) since both repos clone quickly at shallow depth.

## Per-Base-Image Estimates

| Base Image | Approx Size | Languages |
|------------|-------------|-----------|
| `ubuntu:22.04` | ~77 MB | generic |
| `python:3.11-bookworm` | ~350 MB | Python |
| `golang:1.21-bookworm` | ~820 MB | Go |
| `node:20-bookworm` | ~350 MB | JS/TS |
| `eclipse-temurin:21-jdk-jammy` | ~450 MB | Java |
| `rust:1.75-bookworm` | ~1.2 GB | Rust |

These are base image sizes; workspace overhead stays proportional to repo size (typically 5-50MB per repo with shallow clone).

## Health Check Validation

```
OK: grpc-go — a89bee7 Change version to 1.27.0 (#3340)
OK: etcd — e694b7b version: 3.4.7

All repos healthy.
```

The health check validates:
1. Marker files exist (`/workspace/.markers/{repo}.status` = "OK")
2. Revision markers recorded (`/workspace/.markers/{repo}.rev`)
3. `.git` directory present in each repo

## Scripts Validated

| Script | Status | Notes |
|--------|--------|-------|
| `sandbox_builder.py` | Working | Generates Dockerfile + health_check.sh + test_runner.sh |
| `dockerfile_generator.py` | Needs `create_sg_mirrors` import | Depends on `scripts/infra/create_sg_mirrors.py` |
| `health_check.sh` | Working | Validates marker files and .git presence |
| `test_runner.sh` | Working | Skeleton runs; reports no verifiers (expected) |

## Bugs Fixed

1. **URL normalization order** (`sandbox_builder.py`): `validate_repo_entry()` was called before URL normalization (`https://` prefix). Moved normalization before validation.
2. **Dockerfile indentation** (`sandbox_builder.py`): `textwrap.dedent` mixed with f-string interpolation produced inconsistent indentation. Replaced with line-by-line list builder.

## Recommendations

- Consider using multi-stage builds or `--squash` for production to reduce layer count.
- For tasks with >3 repos, consider parallel cloning (Docker BuildKit `RUN --mount` or a clone script).
- The 100MB workspace budget is easily met for 2-repo tasks; 3-5 repo tasks may need monitoring.
