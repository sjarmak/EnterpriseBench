# Research: repo-versions-manifest

## Task TOML Format

Repos are defined as TOML array-of-tables `[[repos]]` with fields:

- `url` — GitHub URL (e.g., `https://github.com/lodash/lodash`)
- `rev` — pinned revision (tag like `v5.64.0`, `3.1.0`, or full SHA like `9fba65efa50fe5f38e5664729d4aa6f85cf7be92`)
- `path` — local checkout path
- `role` — `primary`, `consumer`, `config_source`, etc.

## TOML Parser

Project uses `tomllib` (Python 3.11+ stdlib) with `tomli` as fallback:

```python
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
```

## Task Files

~100 task.toml files under `benchmarks/*/` (plus `_archived/`). Each can have 1-5 repos.

## Unique Repos

Repos are identified by (url, rev) pairs. Same repo may appear at different revs across tasks.

## Existing Infra Scripts

`scripts/infra/` already has Python scripts for infrastructure checks. New script fits here.
