#!/usr/bin/env python3
"""Validator for expected_solution.json files.

Each active task under benchmarks/ may carry an expected_solution.json that
is consumed by the LLM judge in lib/eb_verify/runner.py. This validator
enforces the structural contract so that scaffolds and partial curations
fail loudly instead of silently disabling the judge for unmapped checkpoints.

Gates (CRITICAL/HIGH from PLAN-REVIEW on bead EnterpriseBench-0rv.16):

- C1: every task.toml [[checkpoints]].name has a key in expected_solution.json
- H1: file paths referenced in evaluation_criteria exist at the pinned SHA
      (opt-in via --check-paths, requires GITHUB_TOKEN)
- H2: no checkpoint may carry "_curation_required": true
- H3: high-weight (> 0.30) checkpoints want >= 3 evaluation_criteria
      (emitted as warning, not error)

Usage:
    python3 scripts/validation/validate_expected_solutions.py benchmarks/incident_response/incident-investigation-004
    python3 scripts/validation/validate_expected_solutions.py benchmarks/  # walk tree
    python3 scripts/validation/validate_expected_solutions.py benchmarks/ --json
    python3 scripts/validation/validate_expected_solutions.py benchmarks/ --check-paths

Exit codes:
    0 = all validated tasks passed
    1 = at least one task failed validation
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


# Path-like fragments inside evaluation_criteria text. Conservative: only flag
# strings that look like real source paths. The first segment must be purely
# letters/underscore/hyphen (no digits, no dots) — matches typical source-tree
# roots like `src/`, `pkg/`, `staging/`, `internal/` while rejecting prose
# like `v1.2.3/foo.go` or `version 1.2/something.go`. Subsequent segments
# tolerate digits and dots since real paths like `staging/src/k8s.io/...`
# include them.
_PATH_PATTERN = re.compile(
    r"\b([A-Za-z][A-Za-z_-]*/[A-Za-z0-9_./-]+\.(?:go|py|java|rb|rs|ts|tsx|js|jsx|c|cc|cpp|h|hpp|kt|swift|scala|sh|toml|yaml|yml|json|md|tf|hcl|proto|sql))\b"
)

# Tree directories that the walker must skip (archives, mined-but-not-active).
_SKIP_TREE_PARTS = frozenset({"_archived", "mined"})

# Threshold above which we expect more granular evaluation criteria.
HIGH_WEIGHT_THRESHOLD = 0.30
HIGH_WEIGHT_MIN_CRITERIA = 3
DEFAULT_MIN_CRITERIA = 2


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one task's expected_solution.json."""

    task_id: str
    task_dir: Path
    ok: bool
    skipped: bool = False
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _parse_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise RuntimeError("No TOML parser available. Install tomli: pip install tomli")
    with open(path, "rb") as f:
        return tomllib.load(f)


def _checkpoint_weights(task_toml: dict[str, Any]) -> dict[str, float]:
    """Return {name: weight} from task.toml's [[checkpoints]] entries."""
    out: dict[str, float] = {}
    for cp in task_toml.get("checkpoints", []) or []:
        name = cp.get("name")
        if not isinstance(name, str) or not name:
            continue
        try:
            out[name] = float(cp.get("weight", 0.0))
        except (TypeError, ValueError):
            out[name] = 0.0
    return out


def _declared_repos(task_toml: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every well-formed repo entry from task.toml [[repos]]."""
    repos = task_toml.get("repos") or []
    if not isinstance(repos, list):
        return []
    return [
        r for r in repos
        if isinstance(r, dict)
        and isinstance(r.get("url"), str)
        and isinstance(r.get("rev"), str)
    ]


def _extract_paths_from_criteria(criteria: list[Any]) -> list[str]:
    """Pull file-like path fragments out of the prose criteria."""
    seen: set[str] = set()
    paths: list[str] = []
    for c in criteria:
        if not isinstance(c, str):
            continue
        for match in _PATH_PATTERN.finditer(c):
            p = match.group(1)
            if p not in seen:
                seen.add(p)
                paths.append(p)
    return paths


def _github_path_exists(
    repo_url: str, ref: str, path: str, token: str
) -> bool | None:
    """Return True/False for path existence at ref via GitHub Contents API.

    Returns None on transport errors (network, rate limit) so callers can
    distinguish a real "not found" from a flaky check.
    """
    m = re.match(r"https?://github\.com/([^/]+)/([^/.]+)(?:\.git)?/?$", repo_url)
    if not m:
        return None
    owner, name = m.group(1), m.group(2)
    # Reject paths that try to escape the repo's contents tree. Anything
    # containing ".." resolves to a different GitHub Contents API resource,
    # not the file the criterion claims to reference — fail closed.
    if ".." in Path(path).parts:
        return False
    quoted_path = urllib.parse.quote(path, safe="/")
    quoted_ref = urllib.parse.quote(ref, safe="")
    api = (
        f"https://api.github.com/repos/{owner}/{name}/contents/"
        f"{quoted_path}?ref={quoted_ref}"
    )
    req = urllib.request.Request(
        api,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "eb-validator",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        logger.warning("GitHub API HTTP %s for %s@%s:%s", exc.code, repo_url, ref, path)
        return None
    except urllib.error.URLError as exc:
        logger.warning("GitHub API URL error for %s: %s", repo_url, exc)
        return None


def _validate_payload_structure(
    payload: Any,
    task_id_from_toml: str | None,
    weights: dict[str, float],
) -> tuple[list[str], list[str]]:
    """Structural checks: schema, task_id, checkpoint coverage."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(payload, dict):
        errors.append("expected_solution.json must be a JSON object")
        return errors, warnings

    if "task_id" not in payload:
        errors.append("missing top-level 'task_id'")
    elif task_id_from_toml is not None and payload["task_id"] != task_id_from_toml:
        errors.append(
            f"task_id mismatch: expected_solution has {payload['task_id']!r} "
            f"but task.toml declares {task_id_from_toml!r}"
        )

    if "checkpoints" not in payload:
        errors.append("missing top-level 'checkpoints' map")
        return errors, warnings

    checkpoints = payload["checkpoints"]
    if not isinstance(checkpoints, dict):
        errors.append("'checkpoints' must be an object keyed by checkpoint name")
        return errors, warnings

    expected_names = set(weights.keys())
    actual_names = set(checkpoints.keys())

    # C1: every task.toml checkpoint has a key
    for name in sorted(expected_names - actual_names):
        errors.append(
            f"missing checkpoint {name!r}: declared in task.toml but absent from "
            "expected_solution.json (would silently disable the LLM judge for it)"
        )

    # Typo guard: extra keys not declared in task.toml
    for name in sorted(actual_names - expected_names):
        errors.append(
            f"unknown checkpoint {name!r}: not declared in task.toml [[checkpoints]] "
            "(probable typo)"
        )

    # Per-checkpoint structural checks
    for name, body in checkpoints.items():
        if name not in expected_names:
            continue  # already flagged as extra
        if not isinstance(body, dict):
            errors.append(f"checkpoint {name!r}: must be an object")
            continue

        if body.get("_curation_required") is True:
            errors.append(
                f"checkpoint {name!r}: _curation_required=true — scaffold must be "
                "hand-curated before this file can ship"
            )

        sol = body.get("expected_solution")
        if not isinstance(sol, str) or not sol.strip():
            errors.append(f"checkpoint {name!r}: expected_solution is missing or empty")

        crit = body.get("evaluation_criteria")
        if not isinstance(crit, list):
            errors.append(
                f"checkpoint {name!r}: evaluation_criteria must be a list of strings"
            )
            continue
        if not all(isinstance(c, str) and c.strip() for c in crit):
            errors.append(
                f"checkpoint {name!r}: evaluation_criteria entries must be "
                "non-empty strings"
            )
            continue

        # H3: high-weight checkpoints want more granular criteria
        weight = weights.get(name, 0.0)
        if len(crit) < DEFAULT_MIN_CRITERIA:
            errors.append(
                f"checkpoint {name!r}: evaluation_criteria has {len(crit)} entries, "
                f"minimum is {DEFAULT_MIN_CRITERIA}"
            )
        elif weight > HIGH_WEIGHT_THRESHOLD and len(crit) < HIGH_WEIGHT_MIN_CRITERIA:
            warnings.append(
                f"checkpoint {name!r}: weight={weight} exceeds {HIGH_WEIGHT_THRESHOLD} "
                f"but only {len(crit)} evaluation_criteria — recommend "
                f">= {HIGH_WEIGHT_MIN_CRITERIA} for granular scoring"
            )

    return errors, warnings


def _validate_paths(
    payload: dict[str, Any],
    task_toml: dict[str, Any],
    token: str | None,
) -> tuple[list[str], list[str]]:
    """H1: best-effort check that referenced paths exist at the pinned SHA."""
    errors: list[str] = []
    warnings: list[str] = []

    if not token:
        warnings.append(
            "path-existence check skipped: GITHUB_TOKEN not set "
            "(unauthenticated requests are too rate-limited to be useful)"
        )
        return errors, warnings

    repos = _declared_repos(task_toml)
    if not repos:
        warnings.append("path-existence check skipped: no usable repo declared")
        return errors, warnings

    checkpoints = payload.get("checkpoints", {}) or {}
    # Multi-repo tasks reference paths from any declared repo. Cache per-repo
    # lookups, but resolve a path against ALL repos before flagging — a dual-
    # repo task may have one criterion citing a primary-repo file and another
    # citing a dependency-repo file.
    path_status: dict[str, list[tuple[str, str, bool | None]]] = {}
    for name, body in checkpoints.items():
        if not isinstance(body, dict):
            continue
        crit = body.get("evaluation_criteria")
        if not isinstance(crit, list):
            continue
        for path in _extract_paths_from_criteria(crit):
            if path not in path_status:
                path_status[path] = [
                    (r["url"], r["rev"], _github_path_exists(r["url"], r["rev"], path, token))
                    for r in repos
                ]
            results = path_status[path]
            # Path is OK if ANY declared repo has it.
            if any(r[2] is True for r in results):
                continue
            transport_failures = [r for r in results if r[2] is None]
            if transport_failures and not any(r[2] is False for r in results):
                # All checks were transport errors — warn, don't fail
                warnings.append(
                    f"checkpoint {name!r}: could not verify path {path!r} against "
                    f"any of {len(repos)} declared repo(s) (transport error)"
                )
            else:
                checked = ", ".join(f"{u}@{rev}" for u, rev, _ in results)
                errors.append(
                    f"checkpoint {name!r}: referenced path {path!r} not found in "
                    f"any declared repo ({checked})"
                )

    return errors, warnings


def validate_task(task_dir: Path, *, check_paths: bool = False) -> ValidationResult:
    """Validate one task directory's expected_solution.json (if present)."""
    expected_path = task_dir / "expected_solution.json"
    task_toml_path = task_dir / "task.toml"

    if not task_toml_path.exists():
        return ValidationResult(
            task_id=task_dir.name,
            task_dir=task_dir,
            ok=False,
            errors=("task.toml missing",),
        )

    try:
        task_toml = _parse_toml(task_toml_path)
    except Exception as exc:
        return ValidationResult(
            task_id=task_dir.name,
            task_dir=task_dir,
            ok=False,
            errors=(f"failed to parse task.toml: {exc}",),
        )

    task_section = task_toml.get("task")
    if not isinstance(task_section, dict):
        task_section = {}
    declared_id = task_section.get("id")
    task_id_from_toml = declared_id if isinstance(declared_id, str) else task_dir.name

    if not expected_path.exists():
        return ValidationResult(
            task_id=task_id_from_toml,
            task_dir=task_dir,
            ok=True,
            skipped=True,
        )

    try:
        payload = json.loads(expected_path.read_text())
    except json.JSONDecodeError as exc:
        return ValidationResult(
            task_id=task_id_from_toml,
            task_dir=task_dir,
            ok=False,
            errors=(f"failed to parse expected_solution.json: {exc}",),
        )

    errors, warnings = _validate_payload_structure(
        payload, task_id_from_toml, _checkpoint_weights(task_toml)
    )

    if check_paths and isinstance(payload, dict) and not errors:
        path_errors, path_warnings = _validate_paths(
            payload, task_toml, os.environ.get("GITHUB_TOKEN")
        )
        errors.extend(path_errors)
        warnings.extend(path_warnings)

    return ValidationResult(
        task_id=task_id_from_toml,
        task_dir=task_dir,
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _walk_task_dirs(root: Path) -> list[Path]:
    """Yield every task directory under root, skipping archives and symlink escapes.

    Resolves each candidate's parent dir and confirms it's inside the
    resolved root tree — guards against a poisoned repo using symlinks
    (e.g., benchmarks/evil-task -> /etc) to redirect the walker outside.
    """
    root_resolved = root.resolve()
    if (root_resolved / "task.toml").exists():
        return [root_resolved]
    results: list[Path] = []
    for tt in root_resolved.rglob("task.toml"):
        if any(part in _SKIP_TREE_PARTS for part in tt.parts):
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
        results.append(parent)
    return sorted(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        type=Path,
        help="Single task directory or a tree to walk (e.g. benchmarks/)",
    )
    parser.add_argument(
        "--check-paths",
        action="store_true",
        help="Verify path-like criteria text resolves at the pinned SHA "
        "(needs GITHUB_TOKEN; warns and skips otherwise)",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--quiet", action="store_true", help="Only print failures")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    target = args.path.resolve()
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return 2

    task_dirs = _walk_task_dirs(target)
    if not task_dirs:
        print(f"error: no task.toml under {target}", file=sys.stderr)
        return 2

    results = [
        validate_task(d, check_paths=args.check_paths) for d in task_dirs
    ]

    if args.json:
        out = [
            {
                "task_id": r.task_id,
                "task_dir": str(r.task_dir),
                "ok": r.ok,
                "skipped": r.skipped,
                "errors": list(r.errors),
                "warnings": list(r.warnings),
            }
            for r in results
        ]
        print(json.dumps(out, indent=2))
    else:
        failed = 0
        skipped = 0
        passed = 0
        for r in results:
            if r.skipped:
                skipped += 1
                if not args.quiet:
                    print(f"SKIP {r.task_id} (no expected_solution.json)")
                continue
            if r.ok:
                passed += 1
                if not args.quiet:
                    suffix = (
                        f" ({len(r.warnings)} warning{'s' if len(r.warnings) != 1 else ''})"
                        if r.warnings
                        else ""
                    )
                    print(f"PASS {r.task_id}{suffix}")
                for w in r.warnings:
                    if not args.quiet:
                        print(f"  warn: {w}")
            else:
                failed += 1
                print(f"FAIL {r.task_id}")
                for e in r.errors:
                    print(f"  error: {e}")
                for w in r.warnings:
                    print(f"  warn: {w}")
        print(
            f"\n{passed} passed, {failed} failed, {skipped} skipped "
            f"(of {len(results)} tasks)"
        )

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
