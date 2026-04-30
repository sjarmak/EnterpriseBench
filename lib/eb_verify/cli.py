"""
CLI entry point for eb_verify.

Usage:
    python -m eb_verify.cli run <task.toml>
    python -m eb_verify.cli check <checkpoint_name> <task.toml>
    python -m eb_verify.cli validate-artifact <type> <path>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_run(args: argparse.Namespace) -> int:
    from eb_verify.task_parser import parse_task
    from eb_verify.runner import CheckpointRunner

    task_path = Path(args.task_file)
    if not task_path.exists():
        print(f"Error: {task_path} not found", file=sys.stderr)
        return 1

    task = parse_task(task_path)
    task_dir = task_path.parent

    workspace = Path(args.workspace) if args.workspace else task.workspace_root
    output = args.output or "reward.txt"

    runner = CheckpointRunner(task=task, task_dir=task_dir, workspace=workspace)
    result = runner.run_all(output_path=output)

    print()
    print(result.summary())
    return 0 if result.total_score > 0 else 1


def cmd_check(args: argparse.Namespace) -> int:
    from eb_verify.task_parser import parse_task
    from eb_verify.runner import CheckpointRunner

    task_path = Path(args.task_file)
    if not task_path.exists():
        print(f"Error: {task_path} not found", file=sys.stderr)
        return 1
    task = parse_task(task_path)
    task_dir = task_path.parent

    workspace = Path(args.workspace) if args.workspace else task.workspace_root

    runner = CheckpointRunner(task=task, task_dir=task_dir, workspace=workspace)
    try:
        result = runner.run_single(args.checkpoint_name)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    status = "PASS" if result.passed else "FAIL"
    print(f"{result.name}: {status} (score={result.score:.2f})")
    if result.detail:
        print(f"  {result.detail}")
    return 0 if result.passed else 1


def cmd_validate(args: argparse.Namespace) -> int:
    import json as _json
    from eb_verify.schema_validator import validate_task

    any_errors = False
    results = []

    for task_file in args.task_files:
        result = validate_task(
            task_file,
            qa_strict=getattr(args, "qa_strict", False),
            workspace_root=getattr(args, "workspace", None),
        )
        results.append((task_file, result))
        if not result.valid:
            any_errors = True

    if args.json:
        output = []
        for task_file, result in results:
            output.append({
                "file": task_file,
                "valid": result.valid,
                "errors": [
                    {"field": e.field, "message": e.message, "severity": e.severity}
                    for e in result.errors
                ],
                "warnings": [
                    {"field": w.field, "message": w.message, "severity": w.severity}
                    for w in result.warnings
                ],
            })
        print(_json.dumps(output, indent=2), file=sys.stderr if any_errors else sys.stdout)
    else:
        for task_file, result in results:
            status = "VALID" if result.valid else "INVALID"
            print(f"{task_file}: {status}", file=sys.stderr if not result.valid else sys.stdout)
            for e in result.errors:
                print(f"  ERROR   [{e.field}] {e.message}", file=sys.stderr)
            for w in result.warnings:
                print(f"  WARNING [{w.field}] {w.message}", file=sys.stderr)

    return 1 if any_errors else 0


def cmd_validate_artifact(args: argparse.Namespace) -> int:
    from eb_verify.plugins import get_validator

    validator = get_validator(args.artifact_type)
    if validator is None:
        print(f"Error: no validator for type '{args.artifact_type}'", file=sys.stderr)
        print(f"Available types: code_patch, config, incident_report, runbook, "
              f"reproduction_script, security_assessment, answer", file=sys.stderr)
        return 1

    workspace = Path(args.path)
    result = validator.validate(workspace)
    status = "VALID" if result.valid else "INVALID"
    print(f"{args.artifact_type}: {status}")
    if result.detail:
        print(f"  {result.detail}")
    return 0 if result.valid else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eb_verify",
        description="EnterpriseBench verification library",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_parser = subparsers.add_parser("run", help="Run all verification for a task")
    run_parser.add_argument("task_file", help="Path to task.toml")
    run_parser.add_argument("--workspace", "-w", help="Workspace root (default: /workspace)")
    run_parser.add_argument("--output", "-o", help="Output path for reward.txt")

    # check
    check_parser = subparsers.add_parser("check", help="Run a single checkpoint")
    check_parser.add_argument("checkpoint_name", help="Name of checkpoint to run")
    check_parser.add_argument("task_file", help="Path to task.toml")
    check_parser.add_argument("--workspace", "-w", help="Workspace root")

    # validate
    val_parser = subparsers.add_parser("validate", help="Validate task.toml file(s) against schema")
    val_parser.add_argument("task_files", nargs="+", help="Path(s) to task.toml file(s)")
    val_parser.add_argument("--json", action="store_true", help="Output results as JSON")
    val_parser.add_argument(
        "--qa-strict",
        action="store_true",
        dest="qa_strict",
        help=(
            "Promote benchmark_qa_core error-severity findings to schema "
            "errors (fails validation). Default is warn-only."
        ),
    )
    val_parser.add_argument(
        "--workspace",
        default=None,
        help=(
            "Optional workspace root. When supplied, oracle file existence "
            "checks (A1/B1/B2) run against $WORKSPACE/<repo.path>."
        ),
    )

    # validate-artifact
    va_parser = subparsers.add_parser("validate-artifact", help="Validate a single artifact")
    va_parser.add_argument("artifact_type", help="Artifact type (e.g. code_patch, config)")
    va_parser.add_argument("path", help="Path to workspace/directory containing artifact")

    args = parser.parse_args(argv)

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "check":
        return cmd_check(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "validate-artifact":
        return cmd_validate_artifact(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
