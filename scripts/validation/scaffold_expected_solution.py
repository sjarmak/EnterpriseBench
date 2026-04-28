#!/usr/bin/env python3
"""Scaffold expected_solution.json from task.toml + ground_truth.json.

Mechanical helper — produces a starting structure that operators hand-curate
before shipping. For tasks whose checkpoint names match the standard
incident_investigation pattern, the scaffold is drafted directly from
ground_truth.json fields (root_cause, error_chain, affected_services,
remediation, required_files). For tasks with custom checkpoint names, the
scaffold emits stubs flagged with `_curation_required: true` so the
validator rejects them until a human fills them in.

Usage:
    python3 scripts/validation/scaffold_expected_solution.py benchmarks/.../task_dir
    python3 scripts/validation/scaffold_expected_solution.py benchmarks/.../task_dir --write
    python3 scripts/validation/scaffold_expected_solution.py benchmarks/incident_response/  # walk

The scaffold is printed to stdout unless --write is given. With --write the
file is created next to task.toml; existing files are NOT overwritten unless
--force is also passed.

This is a write-time tool, not a runtime gate. Operators run it once to
generate a starting point, then iterate by hand.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Tree directories the walker must skip — keep in sync with the matching
# constant in validate_expected_solutions.py.
_SKIP_TREE_PARTS = frozenset({"_archived", "mined"})

try:
    import tomllib
except ImportError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


# Standard checkpoint names used across the incident_investigation /
# error_provenance task families, mapped to the ground_truth.json field
# we draft from. Each value is the name of a draft helper below.
STANDARD_CHECKPOINT_HANDLERS: dict[str, str] = {
    "root_cause_identification": "root_cause",
    "error_chain_trace": "error_chain",
    "affected_services": "affected_services",
    "affected_components": "affected_services",
    "affected_resources": "affected_services",
    "affected_connectors": "affected_services",
    "remediation_proposal": "remediation",
}


@dataclass(frozen=True)
class Scaffolded:
    payload: dict[str, Any]
    has_curation_required: bool
    notes: tuple[str, ...]


def _parse_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise RuntimeError("No TOML parser available. Install tomli: pip install tomli")
    with open(path, "rb") as f:
        return tomllib.load(f)


def _draft_root_cause(gt: dict[str, Any]) -> tuple[str, list[str]] | None:
    rc = gt.get("root_cause") if isinstance(gt, dict) else None
    if not isinstance(rc, dict):
        return None
    file_ = rc.get("file") or ""
    func = rc.get("function") or ""
    summary = rc.get("summary") or ""
    mechanism = rc.get("mechanism") or ""

    pieces = [p for p in [summary, mechanism] if p]
    if file_:
        pieces.append(f"Bug location: {file_}{(' :: ' + func) if func else ''}.")
    expected = " ".join(pieces).strip()
    if not expected:
        return None

    criteria: list[str] = []
    if file_:
        criteria.append(f"Must identify {file_} as the root cause file")
    if func:
        criteria.append(f"Must reference function/method {func!r}")
    if mechanism:
        # First sentence of mechanism trimmed for a tight criterion
        first = mechanism.split(".")[0].strip()
        if first and first != mechanism.strip():
            criteria.append(
                f"Must explain the mechanism: {first}"
            )
        else:
            criteria.append("Must explain the underlying mechanism, not just the symptom")
    if summary and len(criteria) < 3:
        criteria.append("Must distinguish root cause from downstream symptoms")
    if len(criteria) < 2:
        # ensure the validator's >= 2 floor is met
        criteria.append("Must reference specific code, not just describe behavior")
    return expected, criteria


def _draft_error_chain(gt: dict[str, Any]) -> tuple[str, list[str]] | None:
    chain = gt.get("error_chain") if isinstance(gt, dict) else None
    if not isinstance(chain, list) or not chain:
        return None
    parts: list[str] = []
    components: list[str] = []
    for i, step in enumerate(chain, start=1):
        if not isinstance(step, dict):
            continue
        comp = step.get("component", "")
        action = step.get("action", "")
        if comp:
            components.append(comp)
        if comp and action:
            parts.append(f"({i}) {comp}: {action}")
        elif comp:
            parts.append(f"({i}) {comp}")
    expected = "Error chain: " + " ".join(parts) if parts else ""
    if not expected:
        return None

    criteria = ["Must trace the error chain in correct order"]
    bug_steps = [s for s in chain if isinstance(s, dict) and "BUG" in str(s.get("action", ""))]
    if bug_steps:
        bug = bug_steps[0]
        criteria.append(
            f"Must identify the buggy step at {bug.get('component', 'the failing component')}"
        )
    if components:
        # name the first and last components specifically
        first = components[0]
        last = components[-1]
        criteria.append(
            f"Must include the entry point ({first}) and the failing component ({last})"
        )
    if len(criteria) < 2:
        criteria.append("Must connect each step to the next, not list them in isolation")
    return expected, criteria


def _draft_affected_services(
    gt: dict[str, Any], required_files: list[dict[str, Any]]
) -> tuple[str, list[str]] | None:
    services = gt.get("affected_services") if isinstance(gt, dict) else None
    expected = ""
    criteria: list[str] = []
    if isinstance(services, list) and services:
        expected = "Affected components: " + "; ".join(
            str(s) for s in services if s
        )
        criteria.append(
            f"Must list at least {min(len(services), 3)} of the affected components/services"
        )

    file_paths = [
        rf.get("path", "")
        for rf in required_files
        if isinstance(rf, dict) and rf.get("path")
    ]
    if file_paths:
        if not expected:
            expected = "Affected components touch the files: " + ", ".join(
                file_paths[:5]
            )
        # Reference the most-confident file path explicitly
        criteria.append(
            f"Must cite specific source files (e.g. {file_paths[0]})"
        )
        if len(file_paths) >= 2:
            criteria.append(
                f"Must cover both implementation and reference paths (e.g. {file_paths[0]}, {file_paths[1]})"
            )

    if not expected:
        return None
    if len(criteria) < 2:
        criteria.append(
            "Must distinguish core failing components from downstream affected callers"
        )
    return expected, criteria


def _draft_remediation(gt: dict[str, Any]) -> tuple[str, list[str]] | None:
    rem = gt.get("remediation") if isinstance(gt, dict) else None
    if not isinstance(rem, str) or not rem.strip():
        return None
    fix_files = gt.get("fix_files") if isinstance(gt, dict) else None
    expected = rem.strip()

    criteria = [
        "Must propose a fix that addresses the root cause, not just the symptom",
    ]
    if isinstance(fix_files, list) and fix_files:
        first = fix_files[0]
        if isinstance(first, str):
            criteria.append(f"Must locate the fix in {first}")
            if len(fix_files) >= 2 and isinstance(fix_files[1], str):
                criteria.append(
                    f"Must touch both {first} and {fix_files[1]} (or equivalent)"
                )
    if len(criteria) < 2:
        criteria.append("Must explain why the proposed fix prevents the failure mode")
    return expected, criteria


def _required_files(task_toml: dict[str, Any], gt: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull required_files from either task.toml ground_truth or ground_truth.json."""
    rf: list[dict[str, Any]] = []
    tt_gt = task_toml.get("ground_truth")
    if isinstance(tt_gt, dict):
        for entry in tt_gt.get("required_files", []) or []:
            if isinstance(entry, dict):
                rf.append(entry)
    if isinstance(gt, dict):
        nested = gt.get("ground_truth")
        if isinstance(nested, dict):
            for entry in nested.get("required_files", []) or []:
                if isinstance(entry, dict):
                    rf.append(entry)
        for entry in gt.get("required_files", []) or []:
            if isinstance(entry, dict):
                rf.append(entry)
    return rf


def _stub_for_custom(name: str) -> dict[str, Any]:
    return {
        "expected_solution": (
            f"TODO: write the canonical solution for checkpoint {name!r}. "
            "Reference specific files, functions, and the causal chain. "
            "Curate from ground_truth.json + Sourcegraph at the pinned revision."
        ),
        "evaluation_criteria": [
            f"TODO: replace with concrete criterion 1 for {name}",
            f"TODO: replace with concrete criterion 2 for {name}",
        ],
        "_curation_required": True,
    }


def scaffold(task_dir: Path) -> dict[str, Any]:
    """Generate a scaffold expected_solution.json payload for a task directory."""
    return scaffold_with_notes(task_dir).payload


def scaffold_with_notes(task_dir: Path) -> Scaffolded:
    task_toml_path = task_dir / "task.toml"
    if not task_toml_path.exists():
        raise FileNotFoundError(f"task.toml not found in {task_dir}")
    task_toml = _parse_toml(task_toml_path)

    task = task_toml.get("task") or {}
    task_id = task.get("id") or task_dir.name

    gt: dict[str, Any] = {}
    gt_path = task_dir / "ground_truth.json"
    if gt_path.exists():
        try:
            gt = json.loads(gt_path.read_text())
        except json.JSONDecodeError:
            gt = {}

    required_files = _required_files(task_toml, gt)

    drafters: dict[str, Callable[[], tuple[str, list[str]] | None]] = {
        "root_cause": lambda: _draft_root_cause(gt),
        "error_chain": lambda: _draft_error_chain(gt),
        "affected_services": lambda: _draft_affected_services(gt, required_files),
        "remediation": lambda: _draft_remediation(gt),
    }

    checkpoints: dict[str, Any] = {}
    notes: list[str] = []
    has_curation_required = False

    for cp in task_toml.get("checkpoints", []) or []:
        name = cp.get("name") if isinstance(cp, dict) else None
        if not isinstance(name, str) or not name:
            continue

        handler = STANDARD_CHECKPOINT_HANDLERS.get(name)
        drafted = drafters[handler]() if handler in drafters else None

        if drafted:
            expected, criteria = drafted
            checkpoints[name] = {
                "expected_solution": expected,
                "evaluation_criteria": criteria,
            }
            notes.append(f"drafted {name} from ground_truth.{handler}")
        else:
            checkpoints[name] = _stub_for_custom(name)
            has_curation_required = True
            notes.append(
                f"stubbed {name} with _curation_required=true "
                f"({'no handler' if not handler else 'handler returned no data'})"
            )

    payload = {"task_id": task_id, "checkpoints": checkpoints}
    return Scaffolded(
        payload=payload,
        has_curation_required=has_curation_required,
        notes=tuple(notes),
    )


def _walk_task_dirs(root: Path) -> list[Path]:
    """Walk root and return task dirs, refusing symlinks that escape the tree.

    Mirror of the same helper in validate_expected_solutions.py — kept
    duplicated rather than shared because both scripts are intentionally
    standalone CLIs. Update both when the walker semantics change.
    """
    root_resolved = root.resolve()
    if (root_resolved / "task.toml").exists():
        return [root_resolved]
    out: list[Path] = []
    for tt in root_resolved.rglob("task.toml"):
        if any(p in _SKIP_TREE_PARTS for p in tt.parts):
            continue
        parent = tt.parent.resolve()
        try:
            parent.relative_to(root_resolved)
        except ValueError:
            logger.warning(
                "skipping %s: resolves outside tree root %s (symlink escape)",
                tt, root_resolved,
            )
            continue
        out.append(parent)
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write expected_solution.json next to task.toml",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing expected_solution.json (default: skip)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-checkpoint notes",
    )
    args = parser.parse_args(argv)

    target = args.path.resolve()
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return 2

    task_dirs = _walk_task_dirs(target)
    if not task_dirs:
        print(f"error: no task.toml under {target}", file=sys.stderr)
        return 2

    written = 0
    skipped = 0
    flagged = 0

    for d in task_dirs:
        try:
            result = scaffold_with_notes(d)
        except (FileNotFoundError, json.JSONDecodeError, RuntimeError) as exc:
            print(f"FAIL {d}: {exc}", file=sys.stderr)
            continue

        out_path = d / "expected_solution.json"
        if args.write:
            if out_path.exists() and not args.force:
                skipped += 1
                if not args.quiet:
                    print(f"SKIP {d.name} (file exists, use --force)")
                continue
            out_path.write_text(json.dumps(result.payload, indent=2) + "\n")
            written += 1
            tag = " [needs curation]" if result.has_curation_required else ""
            if not args.quiet:
                print(f"WROTE {d.name}{tag}")
                for note in result.notes:
                    print(f"  - {note}")
        else:
            print(f"# {d.name}")
            print(json.dumps(result.payload, indent=2))
            print()
        if result.has_curation_required:
            flagged += 1

    if args.write:
        print(
            f"\nWrote {written}, skipped {skipped}, "
            f"{flagged} flagged with _curation_required",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
