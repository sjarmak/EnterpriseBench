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

Method — reproduce the no-op condition offline. Each check is run through the
real scorer's own boundary (``eb_verify.scorer_guard.run_verifier_subprocess``,
the shared ladder behind the Python runners), so "did this check reach a score"
is defined once, by the codebase, not re-derived here:

  * WORKSPACE: a scratch dir holding ONLY ``instruction.md`` (planted where the
    harness puts it, at ``$WORKSPACE/instruction.md``). No ``agent_output/`` and
    no repo source — a no-op leaves the cloned repos pristine and writes nothing,
    so any check that still scores >0 is crediting instruction.md or the answer
    key, never the agent.
  * TASK_DIR: the real task directory (mirrors ``/workspace/.task``): the answer
    key — ``expected_solution.json``, ``ground_truth.json``.

Any check scoring >0 under that condition is a LEAK. Repo-source-pristine leaks
(a check crediting UNCHANGED cloned source) are out of this sweep's scope — it
plants no repo source, only instruction.md — and are covered by the manual audit
recorded in docs/internal/NOOP_LEAK_AUDIT.md, which found every repo-path reader
gates on an agent-written artifact.

Usage:
    python3 scripts/validation/noop_leak_sweep.py                 # sweep benchmarks/
    python3 scripts/validation/noop_leak_sweep.py benchmarks/incident_response
    python3 scripts/validation/noop_leak_sweep.py --json
    python3 scripts/validation/noop_leak_sweep.py --allow ansible-galaxy-tar-regression-prove-001:root_cause

The sweep scores each check with ``json.loads`` (via the shared scorer
boundary), which is STRICTER than the ``parse_score`` awk state machine
``scripts/sandbox/test_runner.sh`` runs in the production container — that one
credits a real ``score`` key even when some other value in the payload is
malformed JSON. The two therefore *could* diverge on a check that emits
malformed-but-``parse_score``-credited output; a divergence there would be a
false negative (a production leak this sweep misses). Empirically they do not:
under the no-op condition every check emits strictly-valid JSON, so ``json.loads``
parses all of them and the two parsers agree on every leak decision. The
invariant that guarantees this is "no check goes unscored" — surfaced here as
``errored`` and frozen by ``tests/integrity/test_noop_leak_sweep.py``: the moment
a check's no-op output stops parsing, ``errored`` rises and the guard fails
loudly instead of silently dropping that check to "not a leak". Aligning the
sweep onto ``parse_score`` itself (so the oracles cannot diverge by construction)
is tracked as follow-up.

Exit codes:
    0 = every check scored, and no leaks outside the --allow set
    1 = at least one leaking checkpoint outside the --allow set
    2 = the sweep could not trust its own result: the path swept no tasks, or a
        check failed to produce a verdict (errored > 0) so its "not a leak"
        is unproven
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_ROOT = REPO_ROOT / "benchmarks"  # corpus root; task paths are shown relative to it
EB_VERIFY_PARENT = REPO_ROOT / "lib"  # PYTHONPATH root: `import eb_verify`
sys.path.insert(0, str(EB_VERIFY_PARENT))
from eb_verify.scorer_guard import run_verifier_subprocess  # noqa: E402

SKIP_TREE_PARTS = frozenset({"_archived", "mined"})
CHECK_TIMEOUT_SEC = 60
SCORE_EPS = 1e-6


@dataclass(frozen=True)
class Leak:
    task_id: str
    task_path: str  # relative to benchmarks/
    checkpoint: str  # verifier basename with the check_ prefix stripped
    check_file: str
    score: float


@dataclass(frozen=True)
class SweepResult:
    leaks: list[Leak]
    n_tasks: int
    n_checks: int
    n_errored: int  # checks that reached no verdict (InfraError -> unscored)


def _iter_task_dirs(root: Path) -> Iterator[Path]:
    for toml in root.rglob("task.toml"):
        if SKIP_TREE_PARTS & set(toml.parts):
            continue
        yield toml.parent


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
        env = dict(os.environ)
        env["WORKSPACE"] = str(ws)
        env["TASK_DIR"] = str(task_dir)  # mirrors /workspace/.task
        env["PYTHONPATH"] = os.pathsep.join(
            [str(EB_VERIFY_PARENT), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        for check in sorted(checks_dir.glob("*.sh")):
            checkpoint = _checkpoint_name(check)
            # run through the real scorer's boundary: a verdict dict carries a
            # validated score; an InfraError (timeout, crash, no verdict) is not
            # a dict, and a check that never reached a score can't be a leak.
            verdict = run_verifier_subprocess(
                check.name,
                base_dir=checks_dir,
                argv_prefix=("bash",),
                argv_suffix=(str(ws),),
                cwd=ws,
                env=env,
                timeout=CHECK_TIMEOUT_SEC,
                checkpoint=checkpoint,
            )
            score = verdict["score"] if isinstance(verdict, dict) else None
            out.append((checkpoint, check, score))
    return out


def sweep(root: Path) -> SweepResult:
    """Sweep every task under ``root`` under the no-op condition.

    ``n_errored`` counts checks that reached no verdict (a ``None`` score from the
    scorer boundary — timeout, crash, unparseable output). Such a check is NOT a
    proven "not a leak": the sweep simply never learned its no-op score, so a
    caller that cares about a trustworthy audit must treat ``n_errored > 0`` as an
    incomplete run, not a clean one.
    """
    leaks: list[Leak] = []
    n_tasks = 0
    n_checks = 0
    n_errored = 0
    for task_dir in sorted(_iter_task_dirs(root)):
        n_tasks += 1
        for checkpoint, check_file, score in _run_task(task_dir):
            n_checks += 1
            if score is None:
                n_errored += 1
                continue
            if score > SCORE_EPS:
                try:
                    rel = task_dir.relative_to(BENCHMARKS_ROOT)
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
    return SweepResult(leaks, n_tasks, n_checks, n_errored)


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
    # A mistyped or moved path makes rglob yield nothing, which would otherwise
    # read as tasks=0 leaks=0 exit 0 — a clean bill of health for an audit that
    # never ran. Fail loudly instead.
    if not root.is_dir():
        print(f"error: sweep path is not a directory: {root}", file=sys.stderr)
        return 2
    allow = _parse_allow(args.allow)

    result = sweep(root)
    leaks = result.leaks
    unexpected = [lk for lk in leaks if not _is_allowed(lk, allow)]

    if args.json:
        print(
            json.dumps(
                {
                    "tasks": result.n_tasks,
                    "checks": result.n_checks,
                    "errored": result.n_errored,
                    "leaks": [asdict(lk) for lk in leaks],
                    "unexpected": [asdict(lk) for lk in unexpected],
                },
                indent=2,
            )
        )
    else:
        print(
            f"tasks={result.n_tasks} checks={result.n_checks} "
            f"errored={result.n_errored} leaks={len(leaks)} "
            f"unexpected={len(unexpected)}"
        )
        for lk in leaks:
            tag = "ALLOW " if _is_allowed(lk, allow) else "LEAK  "
            print(f"{tag}{lk.score:>5.2f}  {lk.task_path}  ::  {lk.check_file}")

    # An unscored check (errored) or a path that swept nothing means the audit's
    # "not a leak" verdict is unproven for part of the corpus — exit 2, distinct
    # from the exit-1 "a real leak exists" signal, so CI can tell them apart.
    if result.n_tasks == 0 or result.n_errored:
        print(
            f"error: sweep incomplete (tasks={result.n_tasks} "
            f"errored={result.n_errored}); result is not a trustworthy audit",
            file=sys.stderr,
        )
        return 2
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
