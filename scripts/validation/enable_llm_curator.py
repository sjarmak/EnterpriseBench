"""Batch-enable ``llm_curator`` in ``verification_modes`` for multi-repo tasks.

Bead EnterpriseBench-0rv.17: once a task has a sibling ``expected_solution.json``
file (created under bead 0rv.16), the LLM judge in ``lib/eb_verify/runner.py``
can produce an extra signal alongside the deterministic checks. Tasks opt in by
declaring ``verification_modes = ["deterministic", "llm_curator"]`` in their
``task.toml``.

Eligibility (criteria from bead 0rv.17):
- ``difficulty_stratum`` is one of ``dual_repo``, ``tri_repo``, ``multi_repo``,
  ``quad_repo`` (the four "multi-repo" strata).
- A sibling ``expected_solution.json`` file exists in the task directory.
- Single-repo strata (``calibration``, ``large_single``,
  ``monorepo_cross_package``) are explicitly excluded.

The mutation is intentionally a textual replacement on a single canonical line
(``verification_modes = ["deterministic"]``) so existing comments, ordering, and
formatting are preserved. All current task.toml files in the tree use this
canonical form (verified at script-write time), so the conservative replacement
is safe; any deviation triggers a hard skip with a warning.

Usage::

    python3 scripts/validation/enable_llm_curator.py benchmarks/
    python3 scripts/validation/enable_llm_curator.py benchmarks/ --dry-run
    python3 scripts/validation/enable_llm_curator.py benchmarks/ --json

Exit codes:
- 0: ran cleanly (all eligible tasks updated or already enabled)
- 1: at least one task could not be processed (parse error, unexpected format)
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
else:  # pragma: no cover - py3.10 fallback
    import tomli as tomllib  # type: ignore[import-not-found]


MULTI_REPO_STRATA = frozenset(
    {"dual_repo", "tri_repo", "multi_repo", "quad_repo"}
)
EXCLUDED_DIR_NAMES = frozenset({"_archived", "mined"})

CANONICAL_DETERMINISTIC = 'verification_modes = ["deterministic"]'
CANONICAL_BOTH = 'verification_modes = ["deterministic", "llm_curator"]'


@dataclass(frozen=True)
class TaskOutcome:
    """Result of processing one ``task.toml``."""

    task_dir: Path
    stratum: str | None
    action: str  # "updated" | "already_enabled" | "skipped" | "error"
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "task_dir": str(self.task_dir),
            "stratum": self.stratum or "",
            "action": self.action,
            "reason": self.reason,
        }


@dataclass
class RunReport:
    outcomes: list[TaskOutcome] = field(default_factory=list)

    def add(self, outcome: TaskOutcome) -> None:
        self.outcomes.append(outcome)

    def by_action(self, action: str) -> list[TaskOutcome]:
        return [o for o in self.outcomes if o.action == action]

    def has_errors(self) -> bool:
        return any(o.action == "error" for o in self.outcomes)


def iter_task_dirs(root: Path) -> Iterator[Path]:
    """Yield directories containing a ``task.toml`` under ``root``.

    Skips ``_archived`` and ``mined`` subtrees so retired or candidate tasks
    are not mutated.
    """
    for task_toml in root.rglob("task.toml"):
        if any(part in EXCLUDED_DIR_NAMES for part in task_toml.parts):
            continue
        yield task_toml.parent


def _read_stratum(task_toml_path: Path) -> str | None:
    """Return the ``difficulty_stratum`` value from a ``task.toml``, if any.

    ``difficulty_stratum`` lives at the top level in current task.toml files
    (alongside ``mcp_suite`` and ``verification_modes``), not inside the
    ``[task]`` table. Fall back to the ``[task]`` table for older files.
    """
    try:
        data = tomllib.loads(task_toml_path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    value = data.get("difficulty_stratum")
    if not isinstance(value, str):
        section = data.get("task")
        if isinstance(section, dict):
            value = section.get("difficulty_stratum")
    return value if isinstance(value, str) else None


def process_task(task_dir: Path, *, dry_run: bool = False) -> TaskOutcome:
    """Process one task directory, returning a :class:`TaskOutcome`.

    The mutation rules:
    - Only multi-repo strata are eligible.
    - Skip if no sibling ``expected_solution.json`` exists.
    - Skip if ``verification_modes`` is already in canonical-both form.
    - Replace canonical-deterministic line with canonical-both.
    - Anything else (multi-line, custom mode list) is logged as an error so a
      human can decide.
    """
    task_toml = task_dir / "task.toml"
    if not task_toml.exists():
        return TaskOutcome(task_dir, None, "error", "task.toml missing")

    stratum = _read_stratum(task_toml)
    if stratum not in MULTI_REPO_STRATA:
        return TaskOutcome(
            task_dir,
            stratum,
            "skipped",
            f"stratum {stratum!r} is not multi-repo",
        )

    if not (task_dir / "expected_solution.json").exists():
        return TaskOutcome(
            task_dir,
            stratum,
            "skipped",
            "expected_solution.json missing — pending curation",
        )

    text = task_toml.read_text()

    if CANONICAL_BOTH in text:
        return TaskOutcome(task_dir, stratum, "already_enabled")

    if CANONICAL_DETERMINISTIC not in text:
        return TaskOutcome(
            task_dir,
            stratum,
            "error",
            "no canonical 'verification_modes = [\"deterministic\"]' line "
            "found — please update by hand",
        )

    if text.count(CANONICAL_DETERMINISTIC) > 1:
        return TaskOutcome(
            task_dir,
            stratum,
            "error",
            "multiple canonical verification_modes lines found — refusing to "
            "guess",
        )

    new_text = text.replace(CANONICAL_DETERMINISTIC, CANONICAL_BOTH, 1)

    if not dry_run:
        task_toml.write_text(new_text)

    return TaskOutcome(task_dir, stratum, "updated")


def run(root: Path, *, dry_run: bool = False) -> RunReport:
    report = RunReport()
    for task_dir in sorted(iter_task_dirs(root)):
        report.add(process_task(task_dir, dry_run=dry_run))
    return report


def _format_text_report(report: RunReport, *, dry_run: bool) -> str:
    lines: list[str] = []
    updated = report.by_action("updated")
    already = report.by_action("already_enabled")
    skipped = report.by_action("skipped")
    errors = report.by_action("error")

    if updated:
        prefix = "WOULD UPDATE" if dry_run else "UPDATED"
        lines.append(f"\n{prefix} ({len(updated)}):")
        for o in updated:
            lines.append(f"  {o.task_dir} ({o.stratum})")

    if already:
        lines.append(f"\nALREADY_ENABLED ({len(already)}):")
        for o in already:
            lines.append(f"  {o.task_dir} ({o.stratum})")

    if skipped:
        # Group by reason for readability.
        by_reason: dict[str, list[TaskOutcome]] = {}
        for o in skipped:
            by_reason.setdefault(o.reason, []).append(o)
        lines.append(f"\nSKIPPED ({len(skipped)}):")
        for reason, items in by_reason.items():
            lines.append(f"  reason: {reason} ({len(items)})")
            for o in items[:5]:
                lines.append(f"    {o.task_dir}")
            if len(items) > 5:
                lines.append(f"    ... and {len(items) - 5} more")

    if errors:
        lines.append(f"\nERRORS ({len(errors)}):")
        for o in errors:
            lines.append(f"  {o.task_dir}: {o.reason}")

    summary = (
        f"\nSummary: updated={len(updated)} already_enabled={len(already)} "
        f"skipped={len(skipped)} errors={len(errors)} "
        f"total={len(report.outcomes)}"
    )
    lines.append(summary)
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    p.add_argument(
        "path",
        type=Path,
        help="Root directory to walk (e.g. benchmarks/).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    p.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        help="Emit machine-readable JSON instead of a human report.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if not args.path.exists():
        print(f"path does not exist: {args.path}", file=sys.stderr)
        return 1
    report = run(args.path, dry_run=args.dry_run)
    if args.emit_json:
        print(
            json.dumps(
                {
                    "dry_run": args.dry_run,
                    "outcomes": [o.to_dict() for o in report.outcomes],
                },
                indent=2,
            )
        )
    else:
        print(_format_text_report(report, dry_run=args.dry_run))
    return 1 if report.has_errors() else 0


if __name__ == "__main__":
    raise SystemExit(main())
