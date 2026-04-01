#!/usr/bin/env python3
"""Pre-flight validation for EnterpriseBench tasks.

Validates all tasks against the schema and checks structural readiness:
- task.toml validates against schemas/task.schema.json
- instruction.md exists
- ground_truth.json exists and is valid
- Checkpoint verifier scripts exist and are executable
- Checkpoint weights sum to 1.0
- Dockerfile variants in environment/ directory
- Mirror config in configs/sg_mirrors/
- Mirror repos indexed in configs/sg_indexing_list.json
- Required top-level fields present (mcp_suite, repo_set_id, etc.)

Usage:
    python scripts/validate_tasks_preflight.py
    python scripts/validate_tasks_preflight.py --suite customer_escalation
    python scripts/validate_tasks_preflight.py --task-id calibration-001
    python scripts/validate_tasks_preflight.py --generate-registry
    python scripts/validate_tasks_preflight.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tomllib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None  # type: ignore[misc,assignment]

ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = ROOT / "benchmarks"
SCHEMA_PATH = ROOT / "schemas" / "task.schema.json"
SG_INDEXING_PATH = ROOT / "configs" / "sg_indexing_list.json"
SG_MIRRORS_DIR = ROOT / "configs" / "sg_mirrors"
REGISTRY_PATH = ROOT / "configs" / "validation_registry.json"

EXCLUDED_DIRS = {"mined", "_archived"}
DOCKERFILE_VARIANTS = {"Dockerfile", "Dockerfile.hybrid", "Dockerfile.sg_only"}

# Top-level fields expected in task.toml (from convergence report)
EXPECTED_TOP_LEVEL = {"difficulty_stratum", "mcp_suite", "verification_modes"}


@dataclass(frozen=True)
class TaskIssue:
    """A single validation issue for a task."""

    severity: str  # "error" or "warning"
    check: str
    message: str


@dataclass
class TaskValidation:
    """Validation result for a single task."""

    task_id: str
    suite: str
    task_dir: str
    has_instruction: bool = False
    has_ground_truth: bool = False
    has_dockerfile: bool = False
    has_dockerfile_hybrid: bool = False
    has_dockerfile_sg_only: bool = False
    has_environment_dir: bool = False
    has_checks_dir: bool = False
    has_test_sh: bool = False
    has_mirror_config: bool = False
    mirrors_indexed: bool = False
    schema_valid: bool = False
    weights_valid: bool = False
    scripts_valid: bool = False
    has_ground_truth_in_toml: bool = False
    has_tool_access: bool = False
    top_level_fields_present: bool = False
    issues: list[TaskIssue] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """Task is ready if it has no errors (warnings are OK)."""
        return not any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


def collect_task_dirs(
    suite_filter: str | None = None,
    task_id_filter: str | None = None,
) -> list[Path]:
    """Find all task.toml directories, with optional filtering."""
    tasks: list[Path] = []
    for toml_path in sorted(BENCHMARKS_DIR.rglob("task.toml")):
        rel = toml_path.relative_to(BENCHMARKS_DIR)
        if rel.parts[0] in EXCLUDED_DIRS:
            continue
        task_dir = toml_path.parent
        suite_name = rel.parts[0]
        dir_name = rel.parts[1] if len(rel.parts) > 2 else task_dir.name

        if suite_filter and suite_name != suite_filter:
            continue
        if task_id_filter and dir_name != task_id_filter:
            continue
        tasks.append(task_dir)
    return tasks


def load_sg_index() -> dict[str, bool]:
    """Load sg_indexing_list.json and return {sg_name: indexed} mapping."""
    if not SG_INDEXING_PATH.exists():
        return {}
    with open(SG_INDEXING_PATH) as f:
        data = json.load(f)
    return {
        repo["sg_name"]: repo.get("_indexed", False) for repo in data.get("repos", [])
    }


def load_mirror_task_ids() -> set[str]:
    """Get set of task IDs that have mirror config files."""
    if not SG_MIRRORS_DIR.exists():
        return set()
    return {p.stem for p in SG_MIRRORS_DIR.glob("*.json")}


def load_schema() -> dict[str, Any] | None:
    """Load task schema, returning None if unavailable."""
    if not SCHEMA_PATH.exists():
        return None
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def validate_task(
    task_dir: Path,
    schema: dict[str, Any] | None,
    validator: Any | None,
    sg_index: dict[str, bool],
    mirror_task_ids: set[str],
    *,
    benchmarks_dir: Path | None = None,
) -> TaskValidation:
    """Run all validation checks on a single task directory."""
    base = benchmarks_dir or BENCHMARKS_DIR
    if task_dir.is_relative_to(base):
        rel = task_dir.relative_to(base)
        suite_name = rel.parts[0]
    else:
        # Fallback: parent directory name as suite
        suite_name = task_dir.parent.name
    dir_name = task_dir.name

    result = TaskValidation(
        task_id=dir_name,
        suite=suite_name,
        task_dir=str(task_dir),
    )

    # Load task.toml
    toml_path = task_dir / "task.toml"
    try:
        with open(toml_path, "rb") as f:
            task_data = tomllib.load(f)
    except Exception as exc:
        result.issues.append(
            TaskIssue("error", "toml_parse", f"Cannot parse task.toml: {exc}")
        )
        return result

    task_block = task_data.get("task", {})
    task_id_from_toml = task_block.get("id", dir_name)

    # 1. Schema validation
    if validator is not None:
        errors = [e.message for e in validator.iter_errors(task_data)]
        if errors:
            for err in errors:
                result.issues.append(TaskIssue("error", "schema", err))
        else:
            result.schema_valid = True
    elif schema is not None:
        result.issues.append(
            TaskIssue(
                "warning",
                "schema",
                "jsonschema not installed, skipping schema validation",
            )
        )
    else:
        result.issues.append(TaskIssue("warning", "schema", "Schema file not found"))

    # 2. instruction.md
    if (task_dir / "instruction.md").exists():
        result.has_instruction = True
    else:
        result.issues.append(
            TaskIssue("error", "instruction", "Missing instruction.md")
        )

    # 3. ground_truth.json
    gt_path = task_dir / "ground_truth.json"
    if gt_path.exists():
        try:
            gt_content = json.loads(gt_path.read_text())
            gt_block = gt_content.get("ground_truth", gt_content)
            if len(gt_block) == 0:
                result.issues.append(
                    TaskIssue("error", "ground_truth", "ground_truth.json is empty")
                )
            else:
                result.has_ground_truth = True
        except json.JSONDecodeError as exc:
            result.issues.append(
                TaskIssue("error", "ground_truth", f"Invalid JSON: {exc}")
            )
    else:
        result.issues.append(
            TaskIssue("error", "ground_truth", "Missing ground_truth.json")
        )

    # 4. Checkpoint weights
    checkpoints = task_data.get("checkpoints", [])
    if checkpoints:
        total_weight = sum(cp.get("weight", 0) for cp in checkpoints)
        if abs(total_weight - 1.0) < 0.01:
            result.weights_valid = True
        else:
            result.issues.append(
                TaskIssue(
                    "error",
                    "weights",
                    f"Checkpoint weights sum to {total_weight:.3f}, expected 1.0",
                )
            )
    else:
        result.issues.append(
            TaskIssue("error", "checkpoints", "No checkpoints defined")
        )

    # 5. Check scripts exist and are executable
    missing_scripts: list[str] = []
    not_exec_scripts: list[str] = []
    for cp in checkpoints:
        script_path = task_dir / cp.get("verifier", "")
        if not script_path.exists():
            missing_scripts.append(cp.get("verifier", "???"))
        elif not os.access(script_path, os.X_OK):
            not_exec_scripts.append(cp.get("verifier", "???"))

    if missing_scripts:
        result.issues.append(
            TaskIssue(
                "error", "scripts", f"Missing verifier scripts: {missing_scripts}"
            )
        )
    elif not_exec_scripts:
        result.issues.append(
            TaskIssue(
                "warning", "scripts", f"Non-executable scripts: {not_exec_scripts}"
            )
        )
    else:
        result.scripts_valid = True

    # 6. Environment directory and Dockerfile variants
    env_dir = task_dir / "environment"
    if env_dir.is_dir():
        result.has_environment_dir = True
        result.has_dockerfile = (env_dir / "Dockerfile").exists()
        result.has_dockerfile_hybrid = (env_dir / "Dockerfile.hybrid").exists()
        result.has_dockerfile_sg_only = (env_dir / "Dockerfile.sg_only").exists()
        if not result.has_dockerfile:
            result.issues.append(
                TaskIssue("warning", "dockerfile", "No Dockerfile in environment/")
            )
    else:
        result.issues.append(
            TaskIssue("warning", "environment", "No environment/ directory")
        )

    # 7. Checks directory
    result.has_checks_dir = (task_dir / "checks").is_dir()

    # 8. test.sh
    result.has_test_sh = (task_dir / "tests" / "test.sh").exists()

    # 9. Mirror config
    if task_id_from_toml in mirror_task_ids:
        result.has_mirror_config = True
    elif dir_name in mirror_task_ids:
        result.has_mirror_config = True
    else:
        # Check tool_access.sourcegraph_mirror_config path
        tool_access = task_data.get("tool_access", {})
        mirror_cfg = tool_access.get("sourcegraph_mirror_config", "")
        if mirror_cfg:
            cfg_path = ROOT / mirror_cfg
            if cfg_path.exists():
                result.has_mirror_config = True
            else:
                result.issues.append(
                    TaskIssue(
                        "warning",
                        "mirror_config",
                        f"Referenced mirror config not found: {mirror_cfg}",
                    )
                )
        else:
            result.issues.append(
                TaskIssue("warning", "mirror_config", "No mirror config file found")
            )

    # 10. Mirrors indexed in sg_indexing_list
    tool_access = task_data.get("tool_access", {})
    mirrors = tool_access.get("sourcegraph_mirrors", [])
    if mirrors:
        all_indexed = True
        for m in mirrors:
            mirror_id = m.get("mirror_id", "")
            sg_name_candidates = [
                f"sg-evals/{mirror_id}",
                mirror_id,
            ]
            found = False
            for candidate in sg_name_candidates:
                if candidate in sg_index:
                    if not sg_index[candidate]:
                        all_indexed = False
                    found = True
                    break
            if not found:
                all_indexed = False
        result.mirrors_indexed = all_indexed
        if not all_indexed:
            result.issues.append(
                TaskIssue(
                    "warning",
                    "mirrors_indexed",
                    "Not all mirrors indexed in sg_indexing_list",
                )
            )
    else:
        # Check mirror config file for mirror info
        if result.has_mirror_config:
            # Try to load and check
            for candidate_id in [task_id_from_toml, dir_name]:
                mirror_file = SG_MIRRORS_DIR / f"{candidate_id}.json"
                if mirror_file.exists():
                    try:
                        mirror_data = json.loads(mirror_file.read_text())
                        mirror_list = mirror_data.get("mirrors", [])
                        if mirror_list:
                            all_indexed = True
                            for m in mirror_list:
                                mid = m.get("mirror_id", "")
                                # Check in sg_index
                                found = any(
                                    c in sg_index for c in [f"sg-evals/{mid}", mid]
                                )
                                if not found:
                                    all_indexed = False
                            result.mirrors_indexed = all_indexed
                    except (json.JSONDecodeError, KeyError):
                        pass
                    break

    # 11. Ground truth in TOML
    if "ground_truth" in task_data:
        gt_toml = task_data["ground_truth"]
        if gt_toml.get("required_files") or gt_toml.get("tiers"):
            result.has_ground_truth_in_toml = True

    # 12. Tool access
    if "tool_access" in task_data:
        result.has_tool_access = True

    # 13. Top-level fields
    present = EXPECTED_TOP_LEVEL.intersection(task_data.keys())
    if present == EXPECTED_TOP_LEVEL:
        result.top_level_fields_present = True
    else:
        missing = EXPECTED_TOP_LEVEL - present
        result.issues.append(
            TaskIssue(
                "warning",
                "top_level_fields",
                f"Missing top-level fields: {sorted(missing)}",
            )
        )

    return result


def generate_registry(results: list[TaskValidation]) -> dict[str, Any]:
    """Generate the validation registry JSON structure."""
    tasks_by_suite: dict[str, list[dict[str, Any]]] = {}
    total_ready = 0
    total_blocked = 0
    all_issues: list[dict[str, str]] = []

    for r in results:
        entry = {
            "task_id": r.task_id,
            "suite": r.suite,
            "ready": r.ready,
            "has_instruction": r.has_instruction,
            "has_ground_truth": r.has_ground_truth,
            "has_dockerfile": r.has_dockerfile,
            "has_dockerfile_hybrid": r.has_dockerfile_hybrid,
            "has_dockerfile_sg_only": r.has_dockerfile_sg_only,
            "has_environment_dir": r.has_environment_dir,
            "has_checks_dir": r.has_checks_dir,
            "has_test_sh": r.has_test_sh,
            "has_mirror_config": r.has_mirror_config,
            "mirrors_indexed": r.mirrors_indexed,
            "schema_valid": r.schema_valid,
            "weights_valid": r.weights_valid,
            "scripts_valid": r.scripts_valid,
            "has_ground_truth_in_toml": r.has_ground_truth_in_toml,
            "has_tool_access": r.has_tool_access,
            "top_level_fields_present": r.top_level_fields_present,
            "error_count": r.error_count,
            "warning_count": r.warning_count,
            "issues": [asdict(i) for i in r.issues],
        }
        tasks_by_suite.setdefault(r.suite, []).append(entry)

        if r.ready:
            total_ready += 1
        else:
            total_blocked += 1

        for issue in r.issues:
            if issue.severity == "error":
                all_issues.append(
                    {
                        "task_id": r.task_id,
                        "suite": r.suite,
                        "check": issue.check,
                        "message": issue.message,
                    }
                )

    suite_summaries = {}
    for suite_name, tasks in sorted(tasks_by_suite.items()):
        suite_ready = sum(1 for t in tasks if t["ready"])
        suite_summaries[suite_name] = {
            "total": len(tasks),
            "ready": suite_ready,
            "blocked": len(tasks) - suite_ready,
        }

    return {
        "_generated_by": "scripts/validate_tasks_preflight.py",
        "_description": "Per-task readiness tracking for EnterpriseBench pre-flight validation",
        "summary": {
            "total_tasks": len(results),
            "ready": total_ready,
            "blocked": total_blocked,
            "suites": suite_summaries,
        },
        "blocking_issues": all_issues,
        "tasks": tasks_by_suite,
    }


def print_report(results: list[TaskValidation]) -> None:
    """Print a human-readable validation report to stdout."""
    total = len(results)
    ready = sum(1 for r in results if r.ready)
    blocked = total - ready

    print(f"\n{'='*70}")
    print(f"EnterpriseBench Pre-Flight Validation Report")
    print(f"{'='*70}")
    print(f"  Total tasks: {total}")
    print(f"  Ready:       {ready}")
    print(f"  Blocked:     {blocked}")
    print()

    # Group by suite
    by_suite: dict[str, list[TaskValidation]] = {}
    for r in results:
        by_suite.setdefault(r.suite, []).append(r)

    for suite_name in sorted(by_suite):
        suite_tasks = by_suite[suite_name]
        suite_ready = sum(1 for t in suite_tasks if t.ready)
        print(f"  {suite_name}: {suite_ready}/{len(suite_tasks)} ready")

    # Print errors
    error_tasks = [r for r in results if not r.ready]
    if error_tasks:
        print(f"\n{'='*70}")
        print(f"BLOCKING ERRORS ({blocked} tasks)")
        print(f"{'='*70}")
        for r in sorted(error_tasks, key=lambda x: (x.suite, x.task_id)):
            errors = [i for i in r.issues if i.severity == "error"]
            print(f"\n  {r.suite}/{r.task_id}:")
            for e in errors:
                print(f"    [{e.check}] {e.message}")

    # Print warnings summary
    warning_tasks = [r for r in results if r.warning_count > 0]
    if warning_tasks:
        print(f"\n{'='*70}")
        print(f"WARNINGS ({sum(r.warning_count for r in results)} total)")
        print(f"{'='*70}")
        for r in sorted(warning_tasks, key=lambda x: (x.suite, x.task_id)):
            warnings = [i for i in r.issues if i.severity == "warning"]
            for w in warnings:
                print(f"  {r.suite}/{r.task_id}: [{w.check}] {w.message}")

    # Feature coverage
    print(f"\n{'='*70}")
    print(f"FEATURE COVERAGE")
    print(f"{'='*70}")
    coverage = {
        "instruction.md": sum(1 for r in results if r.has_instruction),
        "ground_truth.json": sum(1 for r in results if r.has_ground_truth),
        "schema_valid": sum(1 for r in results if r.schema_valid),
        "weights_valid": sum(1 for r in results if r.weights_valid),
        "scripts_valid": sum(1 for r in results if r.scripts_valid),
        "environment/": sum(1 for r in results if r.has_environment_dir),
        "Dockerfile": sum(1 for r in results if r.has_dockerfile),
        "Dockerfile.hybrid": sum(1 for r in results if r.has_dockerfile_hybrid),
        "Dockerfile.sg_only": sum(1 for r in results if r.has_dockerfile_sg_only),
        "mirror_config": sum(1 for r in results if r.has_mirror_config),
        "mirrors_indexed": sum(1 for r in results if r.mirrors_indexed),
        "ground_truth_in_toml": sum(1 for r in results if r.has_ground_truth_in_toml),
        "tool_access": sum(1 for r in results if r.has_tool_access),
        "top_level_fields": sum(1 for r in results if r.top_level_fields_present),
    }
    for label, count in coverage.items():
        pct = (count / total * 100) if total > 0 else 0
        bar = "#" * int(pct / 2)
        print(f"  {label:<25} {count:>3}/{total}  ({pct:5.1f}%)  {bar}")

    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-flight validation for EnterpriseBench tasks"
    )
    parser.add_argument(
        "--suite",
        help="Filter to a specific suite (e.g., customer_escalation)",
    )
    parser.add_argument(
        "--task-id",
        help="Filter to a specific task directory name",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable report",
    )
    parser.add_argument(
        "--generate-registry",
        action="store_true",
        help="Write configs/validation_registry.json",
    )
    parser.add_argument(
        "--errors-only",
        action="store_true",
        help="Only show tasks with errors",
    )
    args = parser.parse_args()

    # Load resources
    schema = load_schema()
    validator = None
    if schema is not None and Draft202012Validator is not None:
        validator = Draft202012Validator(schema)

    sg_index = load_sg_index()
    mirror_task_ids = load_mirror_task_ids()

    # Collect and validate tasks
    task_dirs = collect_task_dirs(
        suite_filter=args.suite,
        task_id_filter=args.task_id,
    )

    if not task_dirs:
        print("No tasks found matching filters.", file=sys.stderr)
        return 1

    results = [
        validate_task(td, schema, validator, sg_index, mirror_task_ids)
        for td in task_dirs
    ]

    # Output
    if args.json:
        registry = generate_registry(results)
        print(json.dumps(registry, indent=2))
    elif args.generate_registry:
        registry = generate_registry(results)
        REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n")
        print(f"Registry written to {REGISTRY_PATH}")
        print_report(results)
    else:
        print_report(results)

    # Exit code
    has_errors = any(not r.ready for r in results)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
