---
name: a7-packaging
description: Creates pyproject.toml for eb_verify, making it pip-installable with CLI entry point. Adds dependencies (tomli, jsonschema).
tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
model: sonnet
---

# A7: Packaging

You make the eb_verify library pip-installable with proper dependency management.

## Context

- `lib/eb_verify/` — Python package with CLI (cli.py), parser, runner, scoring, plugins
- Dependencies needed: `tomli` (TOML parsing for Python <3.11), `jsonschema` (schema validation)
- CLI entry point: `eb-verify` should map to `eb_verify.cli:main`

## Your Task

### 1. Create `pyproject.toml`
Place at the appropriate level (likely `lib/pyproject.toml` or top-level — check where `lib/eb_verify/` is relative to).

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "eb-verify"
version = "0.2.0"
description = "EnterpriseBench verification library"
requires-python = ">=3.10"
dependencies = [
    "tomli>=2.0; python_version < '3.11'",
    "jsonschema>=4.20",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]

[project.scripts]
eb-verify = "eb_verify.cli:main"

[tool.setuptools.packages.find]
where = ["."]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

### 2. Verify installation
- `pip install -e .` (from the correct directory) succeeds
- `eb-verify --help` shows CLI usage
- `python -m eb_verify --help` also works
- `python -c "import eb_verify; print(eb_verify.__version__)"` works

### 3. Fix any package discovery issues
- Ensure `setuptools.packages.find` correctly discovers `eb_verify` and `eb_verify.plugins`
- Ensure `schemas/` directory is accessible (may need `package_data` or `data_files` config)

## Constraints
- Keep dependencies minimal — only tomli and jsonschema
- Support Python 3.10+ (use tomli conditionally for <3.11)
- Don't add unnecessary dev tools or linters
- Don't restructure the package — work with existing layout

## Definition of Done
- `pip install -e .` succeeds
- `eb-verify --help` works from any directory
- `import eb_verify` works
- All declared dependencies resolve
