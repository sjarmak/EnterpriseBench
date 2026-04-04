# Research: staleness-verify-files

## Current state

- `scripts/infra/check_repo_staleness.py`: ~115 lines, loads `repo_versions.json`, checks staleness dates, supports `--json` output
- Uses argparse with `--json`, `--manifest`, `--threshold-days` flags
- Pure functions: `load_manifest()`, `check_staleness()`, `main()`
- Existing tests in `tests/test_repo_staleness.py` (3 test classes, ~15 tests)

## task.toml structure

- `[[repos]]` entries have `url`, `rev`, `path`, `role`
- `[[ground_truth.required_files]]` entries have `path`, `repo`, `confidence`, `source`
- The `repo` field in required_files maps to the `path` field in `[[repos]]`
- Need to cross-reference required_files[].repo -> repos[].path -> repos[].rev

## TOML parsing pattern

- Codebase uses `try: import tomllib` / `except: import tomli as tomllib` pattern
- Binary read mode (`"rb"`) required for tomllib

## repo_versions.json structure

- Array of `{url, pinned_rev, last_verified}` objects
- URL format: `https://github.com/org/repo`
