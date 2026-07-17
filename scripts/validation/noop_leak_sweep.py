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

Method — reproduce the no-op condition offline from production's own definitions,
so a copy here cannot drift from the real harness. Checks run through the scorer
boundary (``eb_verify.scorer_guard.run_verifier_subprocess``) with the
environment a checkpoint really gets (``eb_verify.runner.checkpoint_env``), over:

  * WORKSPACE: a scratch dir holding ONLY ``instruction.md``, planted where the
    harness puts it and rendered by production's own renderer (see
    ``_plant_workspace``). No ``agent_output/`` and no repo source — a no-op
    leaves the cloned repos pristine and writes nothing, so any check that still
    scores >0 is crediting instruction.md or the answer key, never the agent.
  * TASK_DIR: the real task directory (mirrors ``/workspace/.task``): the answer
    key — ``expected_solution.json``, ``ground_truth.json``.

Any check scoring >0 under that condition is a LEAK. Repo-source-pristine leaks
(a check crediting UNCHANGED cloned source) are out of this sweep's scope — it
plants no repo source, only instruction.md — and are covered by the manual audit
recorded in docs/internal/NOOP_LEAK_AUDIT.md, which found every repo-path reader
gates on an agent-written artifact. That doc also records the sweep's reviewed
faithfulness limitations, including the ``json.loads`` vs ``parse_score`` oracle
gap that ``n_unproven`` exists to keep honest.

Usage (an --allow entry names the checkpoint as ``task.toml`` registers it —
``root_cause_identified``, not the verifier's filename stem ``root_cause``):
    python3 scripts/validation/noop_leak_sweep.py                 # sweep benchmarks/
    python3 scripts/validation/noop_leak_sweep.py benchmarks/incident_response
    python3 scripts/validation/noop_leak_sweep.py --json
    python3 scripts/validation/noop_leak_sweep.py --allow ansible-galaxy-tar-regression-prove-001:root_cause_identified

Exit codes (a leak outranks incompleteness — a finding beats an absence of proof;
when both hold, exit is 1 and the incompleteness is still reported on stderr):
    0 = every check scored under a faithful plant, and no leaks outside --allow
    1 = at least one leaking checkpoint outside the --allow set
    2 = no such leak, but the sweep could not trust its own result: the path
        swept no tasks, or some check's verdict is unproven (see sweep())
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS_ROOT = REPO_ROOT / "benchmarks"  # corpus root; task paths are shown relative to it
sys.path.insert(0, str(REPO_ROOT / "lib"))  # `import eb_verify`
sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))  # `import run_task`
sys.path.insert(0, str(Path(__file__).resolve().parent))  # `import enable_llm_curator`
from eb_verify.runner import checkpoint_env  # noqa: E402
from eb_verify.scorer_guard import run_verifier_subprocess  # noqa: E402
from eb_verify.task_parser import TaskDefinition, parse_task  # noqa: E402
from enable_llm_curator import iter_task_dirs  # noqa: E402

# Importing run_task executes its module-level _load_env_local, which mutates this
# process's os.environ (SOURCEGRAPH_*/SG_*/SRC_* keys) when a .env.local exists.
# Lifting the renderer into a side-effect-free module is EnterpriseBench-n97lo.
from run_task import _build_instruction_text, _checkpoint_verifier_name  # noqa: E402

CHECK_TIMEOUT_SEC = 60
SCORE_EPS = 1e-6


@dataclass(frozen=True)
class Leak:
    task_id: str
    task_path: str  # relative to benchmarks/
    checkpoint: str  # the name task.toml registers, i.e. what --allow matches
    check_file: str
    score: float


@dataclass(frozen=True)
class SweepResult:
    leaks: list[Leak]
    n_tasks: int
    n_checks: int
    n_unproven: int  # no verdict, or scored against a degraded plant; see sweep()


def _task_definition(task_dir: Path) -> TaskDefinition | None:
    """Parse ``task.toml``; ``None`` if it will not parse.

    Degrading rather than raising keeps one bad file from aborting the rest of the
    corpus. It is only honest because sweep() then counts this task's checks
    unproven.
    """
    task_toml = task_dir / "task.toml"
    try:
        return parse_task(task_toml)
    except Exception as exc:
        # parse_task raises whatever the failing operation raises — ValueError,
        # KeyError, TypeError, AttributeError — so the catch stays by class rather
        # than by enumeration (evening out that contract is EnterpriseBench-20nhr).
        # Exception and never BaseException, so an operator's Ctrl-C stays uncaught.
        print(
            f"warning: {task_toml}: {exc!r}; falling back to filenames for "
            "checkpoint names and to no grounded-citations appendix",
            file=sys.stderr,
        )
        return None


def _checkpoint_name(check_file: Path, task: TaskDefinition | None) -> str:
    """The checkpoint name an operator would write in ``--allow``.

    That is the name registered in task.toml (``root_cause_identified``), not the
    filename stem (``root_cause``) — they differ for most checks in the corpus.

    Naming ONLY, never discovery: checks are found by globbing ``checks/*.sh``, a
    superset of the task.toml manifest, so an unregistered check is still audited
    under production's own stem rule.
    """
    for cp in task.checkpoints if task else ():
        if Path(cp.verifier).name == check_file.name:
            return cp.name
    return _checkpoint_verifier_name(check_file)


def _plant_workspace(task_dir: Path, task: TaskDefinition | None, ws: Path) -> None:
    """Plant the ``instruction.md`` production puts before a no-op agent.

    Production renders it with ``run_task._build_instruction_text`` — the raw
    instruction text PLUS an output appendix carrying the answer-schema keywords.
    Planting the raw file would make this workspace a strict SUBSET of
    production's, hiding a leak keyed on an appendix keyword (the hpcsv shape).

    ``baseline`` is the smallest true render: other modes only prepend a retrieval
    preamble on top of this exact text. The appendix also varies on the task's
    ``require_grounded_citations``, so that flag is read from task.toml rather
    than defaulted — defaulting it would rebuild the subset bug on a second axis.
    """
    ground_truth = task.ground_truth if task else None
    instruction_text = _build_instruction_text(
        task_dir,
        mode="baseline",
        require_grounded_citations=bool(
            ground_truth and ground_truth.require_grounded_citations
        ),
    )
    if instruction_text is None:  # no instruction.md: production plants nothing
        return
    (ws / "instruction.md").write_text(instruction_text)


def _run_task(
    task_dir: Path, task: TaskDefinition | None
) -> list[tuple[str, Path, float | None]]:
    """Score every check of one task under the no-op condition."""
    checks_dir = task_dir / "checks"
    if not checks_dir.is_dir():
        return []
    out: list[tuple[str, Path, float | None]] = []
    with tempfile.TemporaryDirectory(prefix="noop_ws_") as ws_str:
        ws = Path(ws_str)
        _plant_workspace(task_dir, task, ws)
        # The shared definition of what a checkpoint runs with. Re-deriving it here
        # silently dropped PYTHONSAFEPATH=1, the host half of the scorer-shadowing
        # guard (bead 5cfxa) that production also exports.
        env = checkpoint_env(ws, task_dir, task_dir.name)
        for check in sorted(checks_dir.glob("*.sh")):
            checkpoint = _checkpoint_name(check, task)
            # A verdict dict carries a validated score; an InfraError (timeout,
            # crash, no verdict) is not a dict, and a check that never reached a
            # score can't be a leak.
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

    ``n_unproven`` counts checks the sweep never learned the real no-op score of,
    so their "not a leak" is unproven rather than clean. Two ways in: the scorer
    boundary reached no verdict (timeout, crash, output ``json.loads`` rejects), or
    the task's ``task.toml`` would not parse, so the plant may be a strict subset
    of production's render and a 0.00 against less evidence than the agent really
    gets does not transfer. A caller wanting a trustworthy audit must treat
    ``n_unproven > 0`` as an incomplete run.

    A leak found under a degraded plant is still a real leak — a superset render
    can only add matches — so it counts as BOTH, and exit 1 outranks exit 2.

    Serial: one subprocess per check, ~2s for the whole corpus, because the no-op
    condition is the one that makes checks bail early with no ``agent_output/`` to
    read.
    """
    leaks: list[Leak] = []
    n_tasks = 0
    n_checks = 0
    n_unproven = 0
    for task_dir in sorted(iter_task_dirs(root)):
        n_tasks += 1
        # iter_task_dirs only yields dirs that HAVE a task.toml, so None here
        # means "exists but will not parse" — anomalous, not routine.
        task = _task_definition(task_dir)
        degraded_plant = task is None
        for checkpoint, check_file, score in _run_task(task_dir, task):
            n_checks += 1
            if score is None or degraded_plant:
                n_unproven += 1
            if score is not None and score > SCORE_EPS:
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
    return SweepResult(leaks, n_tasks, n_checks, n_unproven)


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
                    "unproven": result.n_unproven,
                    "leaks": [asdict(lk) for lk in leaks],
                    "unexpected": [asdict(lk) for lk in unexpected],
                },
                indent=2,
            )
        )
    else:
        print(
            f"tasks={result.n_tasks} checks={result.n_checks} "
            f"unproven={result.n_unproven} leaks={len(leaks)} "
            f"unexpected={len(unexpected)}"
        )
        for lk in leaks:
            tag = "ALLOW " if _is_allowed(lk, allow) else "LEAK  "
            print(f"{tag}{lk.score:>5.2f}  {lk.task_path}  ::  {lk.check_file}")

    incomplete = result.n_tasks == 0 or bool(result.n_unproven)
    if incomplete:
        print(
            f"error: sweep incomplete (tasks={result.n_tasks} "
            f"unproven={result.n_unproven}); result is not a trustworthy audit",
            file=sys.stderr,
        )

    if unexpected:
        return 1
    return 2 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
