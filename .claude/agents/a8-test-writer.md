---
name: a8-test-writer
description: Writes pytest test suite for eb_verify — parser, scoring, runner (mocked), validators, schema validator. Targets 80%+ coverage.
tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
model: sonnet
---

# A8: Test Writer

You write the comprehensive test suite for the eb_verify library.

## Context

- `lib/eb_verify/` — verification library with: task_parser, runner, scoring, cli, schema_validator, plugins/
- `benchmarks/EXAMPLE_TASK.toml` — reference task (valid)
- `schemas/task.schema.json` — task definition schema
- `schemas/verifier_output.schema.json` — verifier output contract
- Target: 80%+ coverage on `lib/eb_verify/`

## Your Task

### 1. Create test directory structure
```
tests/
├── __init__.py
├── conftest.py           # shared fixtures
├── fixtures/
│   ├── valid_task.toml   # minimal valid task
│   ├── invalid_task.toml # task with known errors
│   └── edge_cases/       # edge case tasks
├── test_task_parser.py
├── test_scoring.py
├── test_runner.py
├── test_schema_validator.py
└── test_plugins.py
```

### 2. Write test modules

**test_task_parser.py:**
- Parse EXAMPLE_TASK.toml — verify all fields accessible
- Parse minimal valid task — only required fields
- Parse invalid TOML — proper error handling
- Verify frozen dataclass immutability
- Test all new dataclass types (GroundTruth, ToolAccess, CSBLineage, etc.)

**test_scoring.py:**
- Weight computation with various checkpoint results
- All-pass case (score = 1.0)
- All-fail case (score = 0.0)
- Partial credit (mixed scores)
- Edge case: empty checkpoint list
- Edge case: single checkpoint with weight 1.0
- reward.txt output format

**test_runner.py:**
- Mock verifier scripts (use subprocess mocking or temp scripts)
- Health check with existing repos
- Health check with missing repos (should fail)
- Checkpoint timeout handling
- JSON output parsing from verifier stdout
- Exit code fallback (no JSON output)

**test_schema_validator.py:**
- Valid task passes validation
- Missing required field caught
- Invalid enum value caught
- Weight sum != 1.0 caught
- Duplicate checkpoint names caught
- Session-type conditional rules (chain needs session_count, etc.)
- Repo reference consistency
- JSON output mode

**test_plugins.py:**
- Plugin registry returns correct validator for each artifact type
- Unknown artifact type returns error
- code_patch validator basic check
- config_validator with valid/invalid YAML
- Each registered plugin can be instantiated

### 3. Create fixtures
- `valid_task.toml` — minimal task that passes all validation
- `invalid_task.toml` — task with multiple deliberate errors
- Edge case tasks: empty checkpoints, single repo, multi-repo, chain session, event replay

### 4. Verify coverage
- Run `pytest --cov=eb_verify --cov-report=term-missing`
- Target 80%+ overall coverage
- Identify uncovered lines and add tests if below threshold

## Constraints
- Use pytest (not unittest)
- Use fixtures and parametrize for DRY tests
- Mock external dependencies (subprocess, file system) where needed
- Don't modify lib/ code — only write tests
- Tests must pass in isolation (no dependency on external repos or network)

## Definition of Done
- All test files created
- `pytest` passes with 0 failures
- Coverage >= 80% on lib/eb_verify/
- Fixtures cover valid, invalid, and edge cases
