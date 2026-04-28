"""Validate ``llm_curator`` enablement across the benchmark tree.

Bead EnterpriseBench-0rv.17 acceptance gate. After running the batch enabler
(``enable_llm_curator.py``), this script enforces the contract:

A. Every task whose ``verification_modes`` contains ``llm_curator`` has a
   sibling ``expected_solution.json`` file.
B. No single-repo task (``calibration``, ``large_single``,
   ``monorepo_cross_package``) has ``llm_curator`` enabled.
C. Every multi-repo task (``dual_repo``, ``tri_repo``, ``multi_repo``,
   ``quad_repo``) that has ``expected_solution.json`` has ``llm_curator``
   enabled.

Use as a CI gate or local pre-PR check::

    python3 scripts/validation/validate_llm_curator_modes.py benchmarks/
    python3 scripts/validation/validate_llm_curator_modes.py benchmarks/ --json

Exit codes:
- 0: all gates pass.
- 1: at least one gate failed; details printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found]


MULTI_REPO_STRATA = frozenset(
    {"dual_repo", "tri_repo", "multi_repo", "quad_repo"}
)
SINGLE_REPO_STRATA = frozenset(
    {"calibration", "large_single", "monorepo_cross_package"}
)
EXCLUDED_DIR_NAMES = frozenset({"_archived", "mined"})


@dataclass(frozen=True)
class TaskInfo:
    task_dir: Path
    stratum: str | None
    has_llm_curator: bool
    has_expected_solution: bool


@dataclass
class ValidationReport:
    tasks: list[TaskInfo] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.failures


def iter_task_dirs(root: Path) -> Iterator[Path]:
    for task_toml in root.rglob("task.toml"):
        if any(part in EXCLUDED_DIR_NAMES for part in task_toml.parts):
            continue
        yield task_toml.parent


def _load_task(task_dir: Path) -> TaskInfo:
    """Read ``task.toml`` and check the sibling expected_solution.json.

    ``difficulty_stratum`` and ``verification_modes`` live at the top level in
    current task.toml files; older files may carry them inside ``[task]``.
    """
    task_toml = task_dir / "task.toml"
    try:
        data = tomllib.loads(task_toml.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return TaskInfo(task_dir, None, False, False)

    section = data.get("task") if isinstance(data.get("task"), dict) else {}

    stratum = data.get("difficulty_stratum")
    if not isinstance(stratum, str):
        stratum = section.get("difficulty_stratum")
    stratum = stratum if isinstance(stratum, str) else None

    modes = data.get("verification_modes")
    if not isinstance(modes, list):
        modes = section.get("verification_modes")
    has_llm = isinstance(modes, list) and "llm_curator" in modes

    has_es = (task_dir / "expected_solution.json").exists()
    return TaskInfo(task_dir, stratum, has_llm, has_es)


def validate(root: Path) -> ValidationReport:
    report = ValidationReport()
    for task_dir in sorted(iter_task_dirs(root)):
        info = _load_task(task_dir)
        report.tasks.append(info)

        # Gate A: llm_curator must have expected_solution.json sibling.
        if info.has_llm_curator and not info.has_expected_solution:
            report.failures.append(
                f"{info.task_dir}: llm_curator enabled but no "
                "expected_solution.json sibling"
            )

        # Gate B: single-repo tasks must not have llm_curator.
        if (
            info.has_llm_curator
            and info.stratum in SINGLE_REPO_STRATA
        ):
            report.failures.append(
                f"{info.task_dir}: llm_curator enabled on single-repo stratum "
                f"{info.stratum!r}"
            )

        # Gate C: multi-repo task with expected_solution.json should have
        # llm_curator enabled.
        if (
            info.stratum in MULTI_REPO_STRATA
            and info.has_expected_solution
            and not info.has_llm_curator
        ):
            report.failures.append(
                f"{info.task_dir}: multi-repo task ({info.stratum}) with "
                "expected_solution.json is missing llm_curator"
            )

    return report


def _format_text_report(report: ValidationReport) -> str:
    lines: list[str] = []
    enabled = [t for t in report.tasks if t.has_llm_curator]
    multi_with_es = [
        t
        for t in report.tasks
        if t.stratum in MULTI_REPO_STRATA and t.has_expected_solution
    ]
    multi_without_es = [
        t
        for t in report.tasks
        if t.stratum in MULTI_REPO_STRATA and not t.has_expected_solution
    ]

    lines.append(f"Total tasks scanned: {len(report.tasks)}")
    lines.append(f"  llm_curator enabled: {len(enabled)}")
    lines.append(f"  multi-repo with expected_solution.json: {len(multi_with_es)}")
    lines.append(
        f"  multi-repo missing expected_solution.json (pending): "
        f"{len(multi_without_es)}"
    )

    if report.failures:
        lines.append("\nFAILURES:")
        for f in report.failures:
            lines.append(f"  - {f}")
    else:
        lines.append("\nAll gates pass.")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    p.add_argument(
        "path",
        type=Path,
        help="Root directory to walk (e.g. benchmarks/).",
    )
    p.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if not args.path.exists():
        print(f"path does not exist: {args.path}", file=sys.stderr)
        return 1
    report = validate(args.path)
    if args.emit_json:
        print(
            json.dumps(
                {
                    "ok": report.ok(),
                    "failures": list(report.failures),
                    "tasks": [
                        {
                            "task_dir": str(t.task_dir),
                            "stratum": t.stratum,
                            "has_llm_curator": t.has_llm_curator,
                            "has_expected_solution": t.has_expected_solution,
                        }
                        for t in report.tasks
                    ],
                },
                indent=2,
            )
        )
    else:
        print(_format_text_report(report))
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
