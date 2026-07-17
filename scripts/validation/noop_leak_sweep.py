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

Method — reproduce the no-op condition offline. Nothing about the condition is
re-derived here; each piece comes from the definition production itself uses, so
a copy cannot quietly drift from the real harness. Checks run through the real
scorer's boundary (``eb_verify.scorer_guard.run_verifier_subprocess``, the shared
ladder behind the Python runners), with the environment a checkpoint really gets
(``eb_verify.runner.checkpoint_env``), over:

  * WORKSPACE: a scratch dir holding ONLY ``instruction.md``, planted where the
    harness puts it (``$WORKSPACE/instruction.md``) and rendered by production's
    own ``run_task._build_instruction_text`` — raw instruction text plus the
    output appendix, which carries the answer-schema keywords. No
    ``agent_output/`` and no repo source — a no-op leaves the cloned repos
    pristine and writes nothing, so any check that still scores >0 is crediting
    instruction.md or the answer key, never the agent.
  * TASK_DIR: the real task directory (mirrors ``/workspace/.task``): the answer
    key — ``expected_solution.json``, ``ground_truth.json``.

Any check scoring >0 under that condition is a LEAK. Repo-source-pristine leaks
(a check crediting UNCHANGED cloned source) are out of this sweep's scope — it
plants no repo source, only instruction.md — and are covered by the manual audit
recorded in docs/internal/NOOP_LEAK_AUDIT.md, which found every repo-path reader
gates on an agent-written artifact.

Usage (an --allow entry names the checkpoint as ``task.toml`` registers it —
``root_cause_identified``, not the verifier's filename stem ``root_cause``):
    python3 scripts/validation/noop_leak_sweep.py                 # sweep benchmarks/
    python3 scripts/validation/noop_leak_sweep.py benchmarks/incident_response
    python3 scripts/validation/noop_leak_sweep.py --json
    python3 scripts/validation/noop_leak_sweep.py --allow ansible-galaxy-tar-regression-prove-001:root_cause_identified

Exit codes (a leak outranks incompleteness — a finding beats an absence of proof;
when both hold, exit is 1 and the incompleteness is still reported on stderr):
    0 = every check scored, and no leaks outside the --allow set
    1 = at least one leaking checkpoint outside the --allow set
    2 = no such leak, but the sweep could not trust its own result: the path
        swept no tasks, or a check failed to produce a verdict (errored > 0) so
        its "not a leak" is unproven
"""

from __future__ import annotations

import argparse
import functools
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

# Production's own instruction renderer and verifier-naming rule — the single
# source of what the agent sees and what a checkpoint is called (why that
# matters: _plant_workspace, _checkpoint_name).
#
# The cost, accepted knowingly: importing run_task runs its module-level
# _load_env_local, which mutates this process's os.environ (SOURCEGRAPH_*/SG_*/
# SRC_* keys) if a .env.local exists. Harmless for a sweep — it reads no
# credentials and reaches no network — but it is why this import must never be
# treated as free. Lifting _build_instruction_text into a side-effect-free
# renderer module is EnterpriseBench-n97lo.
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
    n_errored: int  # checks that reached no verdict (InfraError -> unscored)


@functools.lru_cache(maxsize=None)
def _task_definition(task_dir: Path) -> TaskDefinition | None:
    """Parse ``task.toml`` once per task; ``None`` if it cannot be read.

    Two callers need it — checkpoint naming and the citations flag — and the
    sweep re-reads each task once per check, so the parse is cached. A task.toml
    is immutable for a sweep's lifetime, which is what makes caching safe.
    """
    task_toml = task_dir / "task.toml"
    try:
        return parse_task(task_toml)
    except (OSError, ValueError, KeyError) as exc:
        # A broken task.toml costs naming and the citations flag, not the audit:
        # the check still runs and can still be caught leaking. Degrade rather
        # than drop the task — but never do it silently.
        #
        # KeyError is in the set because parse_task's error contract is uneven: a
        # missing [task] block becomes a ValueError, but the checkpoint/repo/
        # ground-truth entries subscript required keys directly, so an incomplete
        # one raises a bare KeyError. Left uncaught it escapes sweep()'s per-task
        # loop and aborts all 141 tasks over one bad file — and a traceback's exit
        # code is neither 1 nor 2, so CI reads the crash as an infra flake rather
        # than an integrity failure. Evening out that contract upstream is
        # EnterpriseBench-20nhr; catching it here does not wait on that.
        print(
            f"warning: {task_toml}: {exc!r}; falling back to filenames for "
            "checkpoint names and to no grounded-citations appendix",
            file=sys.stderr,
        )
        return None


def _checkpoint_name(check_file: Path, task_dir: Path) -> str:
    """The checkpoint name an operator would write in ``--allow``.

    That is the name registered in task.toml (``root_cause_identified``), not the
    filename stem (``root_cause``) — they differ for most checks in the corpus.

    Naming ONLY — never discovery. Checks are found by globbing ``checks/*.sh``,
    a superset of the task.toml manifest, so an unregistered check is still
    audited; it falls back to production's own stem rule, which is what decides
    the ``.verifiers/<name>`` key inside the real container.
    """
    task = _task_definition(task_dir)
    for cp in task.checkpoints if task else ():
        if Path(cp.verifier).name == check_file.name:
            return cp.name
    return _checkpoint_verifier_name(check_file)


def _plant_workspace(task_dir: Path, ws: Path) -> None:
    """Plant exactly the ``instruction.md`` the harness puts before a no-op agent.

    Production writes ``/workspace/instruction.md`` from
    ``run_task._build_instruction_text``: the task's raw instruction.md PLUS an
    output appendix carrying the answer-schema keywords (``source_files``,
    ``error_chain``, ``trigger_conditions``, ...). Planting the raw file instead
    would make this workspace a strict SUBSET of production's, so a check keyed on
    an appendix keyword — the hpcsv shape, a workspace-level ``*.md`` glob — could
    leak in production yet read clean here.

    ``baseline`` is the smallest true render: mcp_only/hybrid/cli only prepend a
    retrieval preamble on top of this exact text, so a check that stays clean
    against the baseline plant stays clean in every mode.

    Mode is not the only axis, though. The appendix ALSO varies on the task's
    ``ground_truth.require_grounded_citations``, which production reads from
    task.toml and passes in: when set, the appendix grows a ``citations`` block
    naming ``evidence_span`` and demanding verbatim quoted spans. That flag is
    read here for the same reason the render is not re-derived — defaulting it
    would rebuild the strict-subset bug on a second axis. ``repos`` is not passed
    because it only feeds the non-baseline preamble.
    """
    task = _task_definition(task_dir)
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


def _run_task(task_dir: Path) -> list[tuple[str, Path, float | None]]:
    """Score every check of one task under the no-op condition.

    Scores come from the shared scorer boundary, which parses with ``json.loads``
    — STRICTER than the ``parse_score`` awk state machine
    ``scripts/sandbox/test_runner.sh`` runs in the production container, which
    credits a real ``score`` key even when some other value in the payload is
    malformed JSON. The two therefore *could* diverge on a check emitting
    malformed-but-``parse_score``-credited output, and a divergence there is a
    false negative: a production leak this sweep misses. Empirically they do not —
    under the no-op condition every check emits strictly-valid JSON, so both
    parsers agree on every leak decision. The invariant holding that together is
    "no check goes unscored", surfaced as ``errored`` and frozen by
    ``tests/integrity/test_noop_leak_sweep.py``: the moment a check's no-op output
    stops parsing, ``errored`` rises and the guard fails loudly instead of quietly
    recording "not a leak". Aligning the sweep onto ``parse_score`` itself (so the
    two oracles cannot diverge by construction) is tracked as follow-up.
    """
    checks_dir = task_dir / "checks"
    if not checks_dir.is_dir():
        return []
    out: list[tuple[str, Path, float | None]] = []
    with tempfile.TemporaryDirectory(prefix="noop_ws_") as ws_str:
        ws = Path(ws_str)
        _plant_workspace(task_dir, ws)
        # The shared definition of what a checkpoint runs with (WORKSPACE,
        # TASK_DIR=/workspace/.task, PYTHONPATH, PYTHONSAFEPATH) — "one
        # definition, because tests that re-derive it are not a guard on it".
        # Re-deriving it here silently dropped PYTHONSAFEPATH=1, the host half of
        # the scorer-shadowing guard (bead 5cfxa) that production also exports.
        env = checkpoint_env(ws, task_dir, task_dir.name)
        for check in sorted(checks_dir.glob("*.sh")):
            checkpoint = _checkpoint_name(check, task_dir)
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

    ``n_errored`` counts checks that reached no verdict (a ``None`` score from the
    scorer boundary — timeout, crash, unparseable output). Such a check is NOT a
    proven "not a leak": the sweep simply never learned its no-op score, so a
    caller that cares about a trustworthy audit must treat ``n_errored > 0`` as an
    incomplete run, not a clean one.

    Deliberately serial. The whole corpus (141 tasks / 470 checks) sweeps in a
    couple of seconds despite one subprocess per check, because the no-op
    condition is the very one that makes checks exit early: with no
    ``agent_output/`` to read, a check bails in ~1ms. There is no runtime here
    worth a process pool's complexity.
    """
    # Scope the parse cache to this sweep: a second sweep in one process (fix a
    # task, re-sweep to confirm; the integrity suite) must see task.toml edits
    # made since the first, not the parse it happened to warm.
    _task_definition.cache_clear()
    leaks: list[Leak] = []
    n_tasks = 0
    n_checks = 0
    n_errored = 0
    for task_dir in sorted(iter_task_dirs(root)):
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

    # Both facts are reported; the exit code can only name one, so it names the
    # definite finding over the absence of proof (see "Exit codes" above).
    incomplete = result.n_tasks == 0 or bool(result.n_errored)
    if incomplete:
        print(
            f"error: sweep incomplete (tasks={result.n_tasks} "
            f"errored={result.n_errored}); result is not a trustworthy audit",
            file=sys.stderr,
        )

    if unexpected:
        return 1
    return 2 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
