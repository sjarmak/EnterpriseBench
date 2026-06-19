"""
Schema and semantic validation for eb_verify task.toml files.

Three-layer validation:
  Layer 1: JSON Schema validation against schemas/task.schema.json
  Layer 2: Semantic rules (weights, session-type consistency, repo refs, etc.)
  Layer 3: benchmark_qa_core checks (oracle coherence, scoring honesty,
           aux-file leakage). Layer 3 findings are emitted as warnings by
           default; pass ``qa_strict=True`` to promote ``error``-severity
           findings to schema errors that fail validation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    jsonschema = None  # type: ignore[assignment]
    Draft202012Validator = None  # type: ignore[assignment,misc]

# schemas/ is two levels up from this file (lib/eb_verify/schema_validator.py)
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schemas" / "task.schema.json"


@dataclass(frozen=True)
class ValidationError:
    field: str
    message: str
    severity: str  # "error" | "warning"


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list  # list[ValidationError]
    warnings: list  # list[ValidationError]


def _load_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise ImportError(
            "TOML parsing requires 'tomllib' (Python 3.11+) or 'tomli'. "
            "Install with: pip install tomli"
        )
    with open(path, "rb") as f:
        return tomllib.load(f)


def _load_schema() -> dict[str, Any]:
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


def _validate_schema_layer(data: dict[str, Any], schema: dict[str, Any]) -> list[ValidationError]:
    if jsonschema is None or Draft202012Validator is None:
        raise ImportError(
            "JSON Schema validation requires 'jsonschema'. "
            "Install with: pip install jsonschema"
        )
    errors: list[ValidationError] = []
    validator = Draft202012Validator(schema)
    for error in validator.iter_errors(data):
        field_path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(ValidationError(
            field=field_path,
            message=error.message,
            severity="error",
        ))
    return errors


def _validate_semantic_layer(
    data: dict[str, Any],
) -> tuple[list[ValidationError], list[ValidationError]]:
    """Return (errors, warnings) from semantic validation rules."""
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    task = data.get("task", {})
    session_type = task.get("session_type")
    checkpoints = data.get("checkpoints", [])
    repos = data.get("repos", [])
    ground_truth = data.get("ground_truth", {})
    difficulty_stratum = data.get("difficulty_stratum")

    # Rule 1: Checkpoint weights must sum to 1.0 (tolerance ±0.01)
    if checkpoints:
        total_weight = sum(cp.get("weight", 0.0) for cp in checkpoints)
        if abs(total_weight - 1.0) > 0.01:
            errors.append(ValidationError(
                field="checkpoints[*].weight",
                message=(
                    f"Checkpoint weights sum to {total_weight:.4f}, expected 1.0 (tolerance ±0.01)"
                ),
                severity="error",
            ))

    # Rule 2: session_count present iff session_type == "chain"
    has_session_count = "session_count" in task
    if session_type == "chain" and not has_session_count:
        errors.append(ValidationError(
            field="task.session_count",
            message="session_count is required when session_type is 'chain'",
            severity="error",
        ))
    elif session_type != "chain" and has_session_count:
        errors.append(ValidationError(
            field="task.session_count",
            message=(
                f"session_count must only be present when session_type is 'chain', "
                f"got session_type='{session_type}'"
            ),
            severity="error",
        ))

    # Rule 3: events section present iff session_type == "event_replay"
    has_events = "events" in data
    if session_type == "event_replay" and not has_events:
        errors.append(ValidationError(
            field="events",
            message="events section is required when session_type is 'event_replay'",
            severity="error",
        ))
    elif session_type != "event_replay" and has_events:
        errors.append(ValidationError(
            field="events",
            message=(
                f"events section must only be present when session_type is 'event_replay', "
                f"got session_type='{session_type}'"
            ),
            severity="error",
        ))

    # Rule 4: resume_state section present iff session_type == "resume"
    has_resume_state = "resume_state" in data
    if session_type == "resume" and not has_resume_state:
        errors.append(ValidationError(
            field="resume_state",
            message="resume_state section is required when session_type is 'resume'",
            severity="error",
        ))
    elif session_type != "resume" and has_resume_state:
        errors.append(ValidationError(
            field="resume_state",
            message=(
                f"resume_state section must only be present when session_type is 'resume', "
                f"got session_type='{session_type}'"
            ),
            severity="error",
        ))

    # Rule 5: All repo refs in ground_truth.{required,sufficient}_files must match repos[].path
    repo_paths = {r.get("path") for r in repos if r.get("path")}
    for section_name in ("required_files", "sufficient_files"):
        for i, file_entry in enumerate(ground_truth.get(section_name, [])):
            repo_ref = file_entry.get("repo")
            if repo_ref and repo_ref not in repo_paths:
                errors.append(ValidationError(
                    field=f"ground_truth.{section_name}[{i}].repo",
                    message=(
                        f"repo '{repo_ref}' not found in repos[].path "
                        f"(available: {sorted(repo_paths)})"
                    ),
                    severity="error",
                ))

    # Rule 6: difficulty_stratum consistent with repo count
    _stratum_repo_range: dict[str, tuple[int, int]] = {
        "calibration": (1, 1),
        "large_single": (1, 1),
        "dual_repo": (2, 2),
        "multi_repo": (3, 5),
        "monorepo_cross_package": (1, 1),
    }
    if difficulty_stratum and difficulty_stratum in _stratum_repo_range:
        repo_count = len(repos)
        min_repos, max_repos = _stratum_repo_range[difficulty_stratum]
        if not (min_repos <= repo_count <= max_repos):
            errors.append(ValidationError(
                field="difficulty_stratum",
                message=(
                    f"difficulty_stratum '{difficulty_stratum}' expects "
                    f"{min_repos}–{max_repos} repo(s), got {repo_count}"
                ),
                severity="error",
            ))

    # Rule 7: No duplicate checkpoint names
    seen_names: set[str] = set()
    for i, cp in enumerate(checkpoints):
        name = cp.get("name")
        if name:
            if name in seen_names:
                errors.append(ValidationError(
                    field=f"checkpoints[{i}].name",
                    message=f"Duplicate checkpoint name '{name}'",
                    severity="error",
                ))
            seen_names.add(name)

    return errors, warnings


def _run_qa_layer(
    task_path: Path,
    *,
    strict: bool,
    workspace_root: Path | None,
) -> tuple[list[ValidationError], list[ValidationError]]:
    """Layer 3: run benchmark_qa_core checks via the EB adapter.

    Returns ``(errors, warnings)``. In non-strict mode, all findings are
    warnings regardless of underlying severity. In strict mode, ``error``-
    severity findings become validation errors and ``warning``/``info``
    findings stay as validation warnings.
    """
    try:
        from eb_verify.qa_adapter import load_task_inputs, run_qa_checks
    except Exception as exc:  # pragma: no cover — import-time failure
        return (
            [],
            [
                ValidationError(
                    field="(qa)",
                    message=f"Layer 3 QA skipped — adapter import failed: {exc}",
                    severity="warning",
                )
            ],
        )

    try:
        inputs = load_task_inputs(task_path, workspace_root=workspace_root)
        report = run_qa_checks(inputs)
    except Exception as exc:
        return (
            [],
            [
                ValidationError(
                    field="(qa)",
                    message=f"Layer 3 QA skipped — adapter raised: {exc}",
                    severity="warning",
                )
            ],
        )

    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []
    for f in report.findings:
        target = errors if (strict and f.severity == "error") else warnings
        target.append(
            ValidationError(
                field=f"qa.{f.code}{f' [' + f.location + ']' if f.location else ''}",
                message=f.message,
                severity="error" if (strict and f.severity == "error") else f.severity,
            )
        )
    return errors, warnings


def validate_task(
    path: str,
    *,
    qa_strict: bool = False,
    workspace_root: str | Path | None = None,
) -> ValidationResult:
    """Validate a task.toml file against the JSON Schema and semantic rules.

    Args:
        path: Path to the task.toml file.
        qa_strict: When ``True``, ``error``-severity findings from the
            ``benchmark_qa_core`` Layer 3 checks become validation errors
            and fail the result. When ``False`` (the default), all Layer 3
            findings are emitted as warnings only.
        workspace_root: Optional absolute path to the runtime workspace
            (typically ``/workspace``). When supplied and the cloned repo
            exists at ``workspace_root/<repo.path>``, oracle file/symbol
            existence checks (A1/B1/B2) run against the live tree;
            otherwise those checks are skipped with an info finding.

    Returns:
        ValidationResult with valid flag, errors, and warnings.
    """
    task_path = Path(path)

    # Parse TOML
    try:
        data = _load_toml(task_path)
    except FileNotFoundError:
        return ValidationResult(
            valid=False,
            errors=[ValidationError(
                field="(file)", message=f"File not found: {path}", severity="error",
            )],
            warnings=[],
        )
    except Exception as exc:
        return ValidationResult(
            valid=False,
            errors=[ValidationError(
                field="(parse)", message=f"TOML parse error: {exc}", severity="error",
            )],
            warnings=[],
        )

    all_errors: list[ValidationError] = []
    all_warnings: list[ValidationError] = []

    # Layer 1: JSON Schema validation
    try:
        schema = _load_schema()
        all_errors.extend(_validate_schema_layer(data, schema))
    except ImportError:
        raise
    except Exception as exc:
        all_warnings.append(ValidationError(
            field="(schema)",
            message=f"Schema validation skipped due to error: {exc}",
            severity="warning",
        ))

    # Layer 2: Semantic validation
    sem_errors, sem_warnings = _validate_semantic_layer(data)
    all_errors.extend(sem_errors)
    all_warnings.extend(sem_warnings)

    # Layer 3: benchmark_qa_core checks (warn-only by default)
    workspace = (
        Path(workspace_root) if isinstance(workspace_root, (str, Path)) else None
    )
    qa_errors, qa_warnings = _run_qa_layer(
        task_path,
        strict=qa_strict,
        workspace_root=workspace,
    )
    all_errors.extend(qa_errors)
    all_warnings.extend(qa_warnings)

    return ValidationResult(
        valid=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings,
    )
