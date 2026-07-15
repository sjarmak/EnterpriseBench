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
- A python3 interpreter exists in the task's image whenever a check script
  runs python or imports eb_verify

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
import re
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

sys.path.insert(0, str(ROOT / "scripts" / "infra"))
from mirror_naming import GITHUB_REPO_NAME_RE, ORG, derive_mirror_name  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "sandbox"))
from dockerfile_generator import (  # noqa: E402
    base_image_for_languages,
    image_provides_python,
)

EXCLUDED_DIRS = {"mined", "_archived"}
DOCKERFILE_VARIANTS = {"Dockerfile", "Dockerfile.hybrid", "Dockerfile.sg_only"}

# Top-level fields expected in task.toml (from convergence report)
EXPECTED_TOP_LEVEL = {"difficulty_stratum", "mcp_suite", "verification_modes"}

# A check script needs an interpreter in the container if it runs python or
# imports the eb_verify library through one.
_PYTHON_USE_RE = re.compile(r"\bpython3?\b|\beb_verify\b")


def _script_invokes_python(text: str) -> bool:
    """True if any executable line of *text* runs python or reaches eb_verify.

    The shebang is read before comments are skipped. ``#!/usr/bin/env python3``
    is how a script declares the interpreter it cannot start without, so
    discarding it as a comment hides the very scripts this check exists to find.
    Below the shebang, whole-line comments are skipped but a trailing
    ``# python`` still trips the detector -- see check 14 for why the detector
    errs this way.
    """
    lines = text.splitlines()
    # A shebang is only a shebang on the first line, at column 0.
    if lines and lines[0].startswith("#!") and _PYTHON_USE_RE.search(lines[0]):
        return True
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if _PYTHON_USE_RE.search(line):
            return True
    return False


def _python_dependent_scripts(task_dir: Path, checkpoints: list[dict]) -> list[str]:
    """Names of the task's scripts that cannot run without a python3.

    Scans every declared checkpoint verifier *and* every ``*.sh`` under the
    task. Neither alone is enough: the schema lets a verifier be a ``.py`` file,
    which needs an interpreter just to start, and a verifier may call a shell
    helper the checkpoint list never names.

    Verifiers are reported under their declared name, as check 5 reports them.
    A verifier declared absolute resolves outside the task (``task_dir / "/x"``
    is just ``/x``), so it has no task-relative name to compute -- and deriving
    one anyway raised, taking down the whole run over one malformed task.
    """
    candidates: dict[Path, str] = {}
    for cp in checkpoints:
        verifier = cp.get("verifier")
        if verifier:
            candidates[task_dir / verifier] = str(verifier)
    for path in task_dir.rglob("*.sh"):
        # Discovered under task_dir, so a relative name always exists. A verifier
        # already naming this file keeps its declared spelling.
        candidates.setdefault(path, path.relative_to(task_dir).as_posix())

    needs_python: list[str] = []
    for path, name in candidates.items():
        if not path.is_file():
            continue  # missing verifiers are already reported by the scripts check
        if path.suffix == ".py" or _script_invokes_python(path.read_text(errors="replace")):
            needs_python.append(name)
    return sorted(needs_python)


def _suite_name(task_dir: Path, benchmarks_dir: Path | None) -> str:
    """The suite *task_dir* belongs to, falling back to its parent's name."""
    base = benchmarks_dir or BENCHMARKS_DIR
    if task_dir.is_relative_to(base):
        return task_dir.relative_to(base).parts[0]
    return task_dir.parent.name


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
    python_interpreter_ok: bool = False
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


def _mirror_verified_indexed(sg_name: str, sg_index: dict[str, bool]) -> bool:
    """True iff sg_name is present in sg_index AND its _indexed flag is truthy.

    Used by tool_access.sourcegraph_mirrors[], which wants verified-indexed-
    on-Sourcegraph semantics.
    """
    return sg_index.get(sg_name, False)


def _mirror_present_in_index(sg_name: str, sg_index: dict[str, bool]) -> bool:
    """True iff sg_name is present in sg_index, regardless of _indexed.

    Used by configs/sg_mirrors/*.json, which only wants presence-in-index
    semantics. _indexed is currently hardcoded False for every repo pending
    the deferred --check-api work (EnterpriseBench-k9po.1); once that ships
    and _indexed becomes a real signal, decide then whether this call site
    should switch to _mirror_verified_indexed instead.
    """
    return sg_name in sg_index


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
    dir_name = task_dir.name

    result = TaskValidation(
        task_id=dir_name,
        suite=_suite_name(task_dir, benchmarks_dir),
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
            # mirror_id is "{org}/{repo}--{rev}"; the real sg-evals mirror
            # name drops the org (EnterpriseBench-k9po). No independent rev
            # is available here to route through derive_mirror_name, so
            # strip the org segment directly — this assumes whoever wrote
            # mirror_id already applied derive_mirror_name's ref_suffix
            # transform (slash->underscore, hash truncation). Validate that
            # assumption explicitly rather than let a violation blend into
            # a generic "not indexed" result.
            name_segment = mirror_id.split("/", 1)[-1] if mirror_id else ""
            candidate = f"{ORG}/{name_segment}" if name_segment else ""
            if candidate and not GITHUB_REPO_NAME_RE.match(name_segment):
                all_indexed = False
                result.issues.append(
                    TaskIssue(
                        "warning",
                        "mirrors_indexed",
                        f"mirror_id '{mirror_id}' is not a legal sg-evals mirror "
                        "name segment (not pre-transformed to match "
                        "derive_mirror_name's convention)",
                    )
                )
            elif not _mirror_verified_indexed(candidate, sg_index):
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
                                sg_name = derive_mirror_name(
                                    m.get("repo", ""), m.get("rev", "")
                                )
                                if not _mirror_present_in_index(sg_name, sg_index):
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

    # 14. Python interpreter present wherever a check script needs one.
    # A python-invoking check on a python-less image does not fail loudly — it
    # scores 0.0 with a plausible-looking reason ("Found 0/2 drift points"), so
    # nothing downstream can tell a wrong answer from an unrunnable checkpoint.
    #
    # That asymmetry is why the two helpers above deliberately over-include: a
    # false positive costs a loud preflight error on an image that does ship an
    # interpreter, while a miss puts a checkpoint back to scoring 0.0 in silence.
    languages = task_data.get("metadata", {}).get("languages", [])
    python_scripts = _python_dependent_scripts(task_dir, checkpoints)
    if python_scripts and not image_provides_python(languages):
        result.issues.append(
            TaskIssue(
                "error",
                "python_interpreter",
                f"{python_scripts} run python or import eb_verify, but the "
                f"generated image ({base_image_for_languages(languages)}) ships "
                "no python3 — those checkpoints would silently score 0.0",
            )
        )
    else:
        result.python_interpreter_ok = True

    return result


def validate_task_guarded(
    task_dir: Path,
    schema: dict[str, Any] | None,
    validator: Any | None,
    sg_index: dict[str, bool],
    mirror_task_ids: set[str],
    *,
    benchmarks_dir: Path | None = None,
) -> TaskValidation:
    """``validate_task``, with an unhandled error degraded to that task's issue.

    Preflight's product is a per-task verdict for every task. A malformed task
    that raises must therefore be reported as unready on its own row rather than
    aborting the run, which would report nothing about any of the others.
    """
    try:
        return validate_task(
            task_dir,
            schema,
            validator,
            sg_index,
            mirror_task_ids,
            benchmarks_dir=benchmarks_dir,
        )
    except Exception as exc:
        result = TaskValidation(
            task_id=task_dir.name,
            suite=_suite_name(task_dir, benchmarks_dir),
            task_dir=str(task_dir),
        )
        result.issues.append(
            TaskIssue(
                "error",
                "validator_error",
                f"Validation raised {type(exc).__name__}: {exc}",
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
            "python_interpreter_ok": r.python_interpreter_ok,
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
        "python_interpreter": sum(1 for r in results if r.python_interpreter_ok),
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
        validate_task_guarded(td, schema, validator, sg_index, mirror_task_ids)
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
