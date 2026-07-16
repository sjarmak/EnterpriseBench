#!/usr/bin/env python3
"""No-op leak sweep — benchmark-defensibility guard (bead EnterpriseBench-b5vk6).

Discovered from EnterpriseBench-hpcsv: a NO-OP agent (writes nothing, makes no
code change) scored 1.00 on the ansible-galaxy-tar root-cause checkpoint because
``check_root_cause.sh`` globs ``$WORKSPACE/*.md`` and matches the planted
``instruction.md`` — the answer key, in effect, grading itself. hpcsv fixes that
one task; this sweep answers the systemic question: can a no-op agent score >0
on ANY checkpoint because the expected evidence already exists in the
agent-visible tree (instruction.md, the ``$TASK_DIR`` answer key, or an
eb_verify plugin that defaults to pass)?

Method — reproduce the no-op condition offline, faithfully to the real scorer
(scripts/sandbox/test_runner.sh runs each check as ``bash check.sh $WORKSPACE``
with ``WORKSPACE``/``TASK_DIR`` exported):

  * WORKSPACE: a scratch dir holding ONLY ``instruction.md`` (planted where the
    harness puts it, at ``$WORKSPACE/instruction.md``) plus empty repo dirs. No
    ``agent_output/``. A no-op leaves pristine repos; empty dirs are the
    conservative proxy — a score under empty repos means the credited evidence
    came from instruction.md or the answer key, never from the agent.
  * TASK_DIR: the real task directory (mirrors ``/workspace/.task``): the answer
    key — ``expected_solution.json``, ``ground_truth.json``.

Any check scoring >0 under that condition is a LEAK. Repo-source-pristine leaks
(a check crediting UNCHANGED cloned source) are out of this sweep's scope — it
plants empty repo dirs, not the pinned trees — and are covered by the manual
audit recorded in docs/internal/NOOP_LEAK_AUDIT.md, which found every repo-path
reader gates on an agent-written artifact.

Usage:
    python3 scripts/validation/noop_leak_sweep.py                 # sweep benchmarks/
    python3 scripts/validation/noop_leak_sweep.py benchmarks/incident_response
    python3 scripts/validation/noop_leak_sweep.py --json
    python3 scripts/validation/noop_leak_sweep.py --allow ansible-galaxy-tar-regression-prove-001:root_cause

Exit codes:
    0 = no leaks outside the --allow set
    1 = at least one leaking checkpoint outside the --allow set
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EB_VERIFY_PARENT = REPO_ROOT / "lib"  # PYTHONPATH root: `import eb_verify`
SKIP_TREE_PARTS = frozenset({"_archived", "mined"})
CHECK_TIMEOUT_SEC = 60
SCORE_EPS = 1e-6

# task.toml repo entries carry a ``name = "..."`` on a line the block scopes to a
# repo; this pulls those names so the scratch workspace mirrors the cloned dirs.
_REPO_NAME_RE = re.compile(r'name\s*=\s*"([^"]+)"')
_SCORE_RE = re.compile(r'"score"\s*:\s*([0-9]*\.?[0-9]+)')


@dataclass(frozen=True)
class Leak:
    task_id: str
    task_path: str  # relative to benchmarks/
    checkpoint: str  # verifier basename with the check_ prefix stripped
    check_file: str
    score: float


def _iter_task_dirs(root: Path):
    for toml in root.rglob("task.toml"):
        if SKIP_TREE_PARTS & set(toml.parts):
            continue
        yield toml.parent


def _repo_dir_names(task_dir: Path) -> list[str]:
    toml = task_dir / "task.toml"
    if not toml.exists():
        return []
    names: list[str] = []
    for line in toml.read_text(errors="ignore").splitlines():
        if "repo" in line.lower():
            m = _REPO_NAME_RE.search(line)
            if m:
                names.append(m.group(1))
    return names


def _parse_score(stdout: str) -> float | None:
    """The score a check attested, or None if it printed no parseable score.

    Prefers strict JSON on the last object-looking line (what test_runner's
    structural scanner credits); falls back to a tolerant regex so a check that
    prints diagnostics around its verdict is still read rather than silently
    dropped to None (which would hide a leak).
    """
    text = stdout.strip()
    if not text:
        return None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "score" in obj:
            try:
                return float(obj["score"])
            except (TypeError, ValueError):
                return None
    m = _SCORE_RE.findall(text)
    if m:
        try:
            return float(m[-1])
        except ValueError:
            return None
    return None


def _checkpoint_name(check_file: Path) -> str:
    stem = check_file.stem
    return stem[len("check_"):] if stem.startswith("check_") else stem


def _run_task(task_dir: Path) -> list[tuple[str, Path, float | None]]:
    checks_dir = task_dir / "checks"
    if not checks_dir.is_dir():
        return []
    instruction = task_dir / "instruction.md"
    out: list[tuple[str, Path, float | None]] = []
    with tempfile.TemporaryDirectory(prefix="noop_ws_") as ws_str:
        ws = Path(ws_str)
        if instruction.exists():
            (ws / "instruction.md").write_text(instruction.read_text(errors="ignore"))
        for name in _repo_dir_names(task_dir):
            (ws / name).mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["WORKSPACE"] = str(ws)
        env["TASK_DIR"] = str(task_dir)  # mirrors /workspace/.task
        env["PYTHONPATH"] = os.pathsep.join(
            [str(EB_VERIFY_PARENT), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        for check in sorted(checks_dir.glob("*.sh")):
            try:
                proc = subprocess.run(
                    ["bash", str(check), str(ws)],
                    env=env,
                    cwd=str(ws),
                    capture_output=True,
                    text=True,
                    timeout=CHECK_TIMEOUT_SEC,
                )
                score = _parse_score(proc.stdout)
            except (subprocess.TimeoutExpired, OSError):
                score = None
            out.append((_checkpoint_name(check), check, score))
    return out


def sweep(root: Path, benchmarks_root: Path) -> tuple[list[Leak], int, int]:
    """Return (leaks, n_tasks, n_checks) for every task under ``root``."""
    leaks: list[Leak] = []
    n_tasks = 0
    n_checks = 0
    for task_dir in sorted(_iter_task_dirs(root)):
        n_tasks += 1
        for checkpoint, check_file, score in _run_task(task_dir):
            n_checks += 1
            if score is not None and score > SCORE_EPS:
                try:
                    rel = task_dir.relative_to(benchmarks_root)
                except ValueError:
                    rel = task_dir
                leaks.append(
                    Leak(
                        task_id=task_dir.name,
                        task_path=str(rel),
                        checkpoint=checkpoint,
                        check_file=check_file.name,
                        score=score,
                    )
                )
    return leaks, n_tasks, n_checks


def _parse_allow(values: list[str]) -> set[str]:
    """Allow entries as ``task_id`` (whole task) or ``task_id:checkpoint``."""
    return {v.strip() for v in values if v.strip()}


def _is_allowed(leak: Leak, allow: set[str]) -> bool:
    return leak.task_id in allow or f"{leak.task_id}:{leak.checkpoint}" in allow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "path",
        nargs="?",
        default=str(REPO_ROOT / "benchmarks"),
        help="task, suite, or benchmarks/ root to sweep (default: benchmarks/)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="TASK[:CHECKPOINT]",
        help="known-open leak to not fail on (repeatable)",
    )
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    benchmarks_root = REPO_ROOT / "benchmarks"
    allow = _parse_allow(args.allow)

    leaks, n_tasks, n_checks = sweep(root, benchmarks_root)
    unexpected = [lk for lk in leaks if not _is_allowed(lk, allow)]

    if args.json:
        print(
            json.dumps(
                {
                    "tasks": n_tasks,
                    "checks": n_checks,
                    "leaks": [lk.__dict__ for lk in leaks],
                    "unexpected": [lk.__dict__ for lk in unexpected],
                },
                indent=2,
            )
        )
    else:
        print(f"tasks={n_tasks} checks={n_checks} leaks={len(leaks)} unexpected={len(unexpected)}")
        for lk in leaks:
            tag = "ALLOW " if _is_allowed(lk, allow) else "LEAK  "
            print(f"{tag}{lk.score:>5.2f}  {lk.task_path}  ::  {lk.check_file}")

    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
