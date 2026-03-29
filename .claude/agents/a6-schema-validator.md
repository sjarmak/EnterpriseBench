---
name: a6-schema-validator
description: Builds lib/eb_verify/schema_validator.py — validates task TOML against JSON Schema + semantic rules. Adds 'validate' CLI subcommand. This is the "validated at startup" deliverable.
tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
model: sonnet
---

# A6: Schema Validator

You build the metadata validation layer that ensures every task.toml is correct before execution.

## Context

- `schemas/task.schema.json` — the JSON Schema for task definitions
- `schemas/verifier_output.schema.json` — the verifier output contract
- `lib/eb_verify/cli.py` — existing CLI with run, check, validate-artifact subcommands
- Convergence report: "Metadata | Single source of truth, validated at startup"
- The prototype runner has NO pre-flight validation — invalid tasks crash at runtime

## Your Task

### 1. Create `lib/eb_verify/schema_validator.py`

```python
@dataclass(frozen=True)
class ValidationError:
    field: str
    message: str
    severity: str  # "error" | "warning"

@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[ValidationError]
    warnings: list[ValidationError]

def validate_task(path: str) -> ValidationResult:
    """Validate a task.toml file against schema + semantic rules."""
```

### 2. Implement validation layers

**Layer 1: JSON Schema validation**
- Parse TOML to dict
- Validate against `schemas/task.schema.json` using `jsonschema` library
- Report all schema violations

**Layer 2: Semantic validation rules**
At minimum these 7 rules:
1. Checkpoint weights sum to 1.0 (tolerance: +/- 0.01)
2. `session_count` present if and only if `session_type == "chain"`
3. `events` section present if and only if `session_type == "event_replay"`
4. `resume_state` section present if and only if `session_type == "resume"`
5. All `repo` references in `ground_truth.required_files` match a repo in `repos[].path`
6. `difficulty_stratum` consistent with repo count (calibration = 1 repo, dual_repo = 2 repos, etc.)
7. No duplicate checkpoint names

### 3. Add CLI subcommand
- Add `validate` to `lib/eb_verify/cli.py`: `eb-verify validate <task.toml> [<task2.toml> ...]`
- Exit 0 if all valid, exit 1 if any errors
- Print errors and warnings to stderr in human-readable format
- Support `--json` flag for machine-readable output

### 4. Write tests
- `tests/test_schema_validator.py` with:
  - Valid EXAMPLE_TASK.toml passes
  - Missing required field caught
  - Bad enum value caught
  - Weight sum != 1.0 caught
  - Duplicate checkpoint name caught
  - Each semantic rule tested with a minimal fixture

## Constraints
- Import `jsonschema` — if not installed, provide clear error message
- Schema path should be discovered relative to the package, not hardcoded
- Validation must be fast (< 100ms per task)
- Don't modify the runner — this is standalone validation

## Definition of Done
- `python -m eb_verify validate benchmarks/EXAMPLE_TASK.toml` exits 0
- At least 7 semantic validation rules implemented
- Each rule has a unit test
- Invalid tasks produce clear, actionable error messages
