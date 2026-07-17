"""Unit tests for the no-op leak sweep's own mechanics (bead EnterpriseBench-h3f0p).

The corpus-wide guard (``tests/integrity/test_noop_leak_sweep.py``) shells out one
subprocess per check and answers "does anything leak?". These tests answer the
prior question — *is the sweep asking production's question?* — by pinning the
three places it can quietly drift from the real harness: what it plants in the
workspace, what it calls a checkpoint, and what it reports to CI. Drift in any of
them makes a clean sweep mean less than it appears to.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import noop_leak_sweep  # noqa: E402
from noop_leak_sweep import Leak, SweepResult  # noqa: E402
from run_task import _build_instruction_text  # noqa: E402

RAW_INSTRUCTION = "Find the root cause of the regression.\n"

TASK_TOML = """\
difficulty_stratum = "large_single"

[task]
id = "fixture-task-001"
suite = "incident_response"
difficulty = "hard"
session_type = "single"

[ground_truth]
require_grounded_citations = {grounded}

[[checkpoints]]
name = "root_cause_identified"
weight = 1.0
verifier = "checks/check_root_cause.sh"
"""

# The ``[task]`` block on its own, for fixtures that must break somewhere else.
_TASK_BLOCK = """\
[task]
id = "fixture-task-001"
suite = "incident_response"
difficulty = "hard"
session_type = "single"
"""

# Shapes that make ``parse_task`` raise, each a DIFFERENT class from a DIFFERENT
# line. Parametrising over them is the point: the catch has been patched by
# enumeration twice and been wrong twice, so the guard has to be against the
# failure CLASS. A narrow "also catch TypeError" fix passes `repos_as_scalars`
# and still fails `ground_truth_as_scalar`.
UNPARSEABLE_TASK_TOMLS = {
    # tomllib.TOMLDecodeError (a ValueError) — raised inside tomllib
    "toml_syntax_error": "not = valid = toml",
    # ValueError — parse_task's own explicit raise for a missing [task] block
    "no_task_block": 'difficulty_stratum = "large_single"\n',
    # KeyError — checkpoint entries subscript required keys directly
    "checkpoint_missing_weight": _TASK_BLOCK
    + '\n[[checkpoints]]\nname = "root_cause_identified"\nverifier = "checks/check_root_cause.sh"\n',
    # TypeError — `url=r["url"]` where r is a str, not a table
    "repos_as_scalars": 'repos = ["a", "b"]\n' + _TASK_BLOCK,
    # AttributeError — _parse_ground_truth calls .get on a str
    "ground_truth_as_scalar": 'ground_truth = "x"\n' + _TASK_BLOCK,
}

# One representative shape for tests about the CONSEQUENCES of a bad task.toml,
# which are identical whatever raised: the parse returned None.
A_BAD_TASK_TOML = "repos_as_scalars"

SCORING_CHECK = '#!/bin/bash\necho \'{"score": 0.0}\'\n'
LEAKING_CHECK = '#!/bin/bash\necho \'{"score": 1.0}\'\n'


def _make_task(
    tmp_path: Path,
    *,
    instruction: str | None = RAW_INSTRUCTION,
    grounded: bool = False,
) -> Path:
    """A minimal on-disk task: task.toml, a checks/ dir, and an instruction.md."""
    task_dir = tmp_path / "fixture-task-001"
    (task_dir / "checks").mkdir(parents=True)
    (task_dir / "task.toml").write_text(
        TASK_TOML.format(grounded="true" if grounded else "false")
    )
    if instruction is not None:
        (task_dir / "instruction.md").write_text(instruction)
    return task_dir


def _make_unparseable_task(
    tmp_path: Path, shape: str, check: str = SCORING_CHECK
) -> Path:
    """A fixture task whose task.toml raises out of ``parse_task``."""
    task_dir = _make_task(tmp_path)
    (task_dir / "task.toml").write_text(UNPARSEABLE_TASK_TOMLS[shape])
    (task_dir / "checks" / "check_root_cause.sh").write_text(check)
    return task_dir


def _plant(tmp_path: Path, **kw) -> tuple[Path, Path]:
    """Plant a fixture task's workspace exactly as the sweep does.

    Returns ``(task_dir, ws)``; the planted text is ``ws / "instruction.md"``.
    """
    task_dir = _make_task(tmp_path, **kw)
    ws = tmp_path / "ws"
    ws.mkdir()
    noop_leak_sweep._plant_workspace(
        task_dir, noop_leak_sweep._task_definition(task_dir), ws
    )
    return task_dir, ws


# --- what the sweep plants -------------------------------------------------


@pytest.mark.parametrize("grounded", [True, False])
def test_plant_is_productions_render_at_the_tasks_citations_flag(tmp_path, grounded):
    """The plant is production's own render, read at the task's real flag.

    The appendix varies on ``ground_truth.require_grounded_citations`` as well as
    on the mode, and production reads that flag from task.toml. Hardcoding it
    either way replants the subset/superset bug one axis over: defaulted to False
    the plant under-renders a grounded task; pinned to True it invents a citations
    block production would never emit.
    """
    task_dir, ws = _plant(tmp_path, grounded=grounded)

    planted = (ws / "instruction.md").read_text()
    assert planted == _build_instruction_text(
        task_dir, mode="baseline", require_grounded_citations=grounded
    )
    assert ('"citations"' in planted) is grounded


def test_planted_instruction_is_a_strict_superset_of_the_raw_file(tmp_path):
    """The bug being fixed: the raw file alone is less than the agent really sees.

    Deliberately keyed on the raw text rather than on the appendix's field names.
    Naming them here would mirror a literal owned by ``run_task``, so a legitimate
    rename there would fail this suite for a defect that is not in the sweep —
    while this assertion still catches production dropping the appendix outright,
    which is the drift that would make the equality test above vacuous.
    """
    _, ws = _plant(tmp_path)

    planted = (ws / "instruction.md").read_text()
    assert RAW_INSTRUCTION in planted
    assert planted != RAW_INSTRUCTION


def test_plant_skips_a_task_with_no_instruction(tmp_path):
    """No instruction.md means production plants nothing — so neither do we."""
    _, ws = _plant(tmp_path, instruction=None)

    assert list(ws.iterdir()) == []


# --- what the sweep calls a checkpoint -------------------------------------


def test_checkpoint_name_is_the_name_registered_in_task_toml(tmp_path):
    """`check_root_cause.sh` is the checkpoint `root_cause_identified`."""
    task_dir = _make_task(tmp_path)
    check = task_dir / "checks" / "check_root_cause.sh"
    check.write_text("#!/bin/bash\n")

    task = noop_leak_sweep._task_definition(task_dir)
    assert noop_leak_sweep._checkpoint_name(check, task) == "root_cause_identified"


def test_checkpoint_name_falls_back_to_filename_when_unregistered(tmp_path):
    """Discovery is a glob, so a check absent from task.toml is still audited."""
    task_dir = _make_task(tmp_path)
    check = task_dir / "checks" / "check_unregistered.sh"
    check.write_text("#!/bin/bash\n")

    task = noop_leak_sweep._task_definition(task_dir)
    assert noop_leak_sweep._checkpoint_name(check, task) == "unregistered"


def test_checkpoint_name_falls_back_to_filename_when_the_toml_will_not_parse(tmp_path):
    """A broken task.toml costs naming, not the audit."""
    task_dir = _make_unparseable_task(tmp_path, A_BAD_TASK_TOML)
    check = task_dir / "checks" / "check_root_cause.sh"

    assert noop_leak_sweep._checkpoint_name(check, None) == "root_cause"


# --- what the sweep does when task.toml will not parse ---------------------


@pytest.mark.parametrize("shape", sorted(UNPARSEABLE_TASK_TOMLS))
def test_every_unparseable_shape_degrades_to_none_and_warns(tmp_path, shape, capsys):
    """The catch is by CLASS: every shape degrades, and never silently.

    This is the one site the shape discriminates at — once the parse returns None,
    naming and the unproven tally behave identically whatever raised. Enumerating
    the shapes someone thought of is what made the catch wrong twice, so the guard
    is against the failure class.
    """
    task_dir = _make_unparseable_task(tmp_path, shape)

    assert noop_leak_sweep._task_definition(task_dir) is None
    assert "task.toml" in capsys.readouterr().err


def test_a_task_whose_toml_will_not_parse_is_unproven_not_clean(tmp_path, capsys):
    """An unparseable task.toml must complete the sweep AND be reported unproven.

    Both adjacent answers are wrong. Uncaught, the raise aborts the whole corpus
    audit over one bad file. Merely caught, the task gets a DEGRADED plant — the
    citations flag falls back to False, so the workspace can be a strict subset of
    what production renders — and its zero scores are then recorded as a clean
    bill of health. The truthful answer is neither: the sweep never learned this
    task's real no-op score, which is exactly the "unproven" state it already
    models as ``n_unproven`` -> exit 2.
    """
    _make_unparseable_task(tmp_path, A_BAD_TASK_TOML)

    result = noop_leak_sweep.sweep(tmp_path)  # must not raise

    assert result.n_tasks == 1
    assert result.n_checks == 1
    assert result.n_unproven == 1, (
        "a task whose task.toml will not parse was planted from a defaulted "
        "citations flag, so its 0.00 score is unproven, not a proven 'not a leak'"
    )
    assert not result.leaks
    assert "task.toml" in capsys.readouterr().err


def test_a_parseable_task_is_not_counted_unproven(tmp_path):
    """The off-direction: `n_unproven += 1` unconditionally would pass the test above."""
    task_dir = _make_task(tmp_path)
    (task_dir / "checks" / "check_root_cause.sh").write_text(SCORING_CHECK)

    result = noop_leak_sweep.sweep(tmp_path)

    assert (result.n_tasks, result.n_checks, result.n_unproven) == (1, 1, 0)
    assert not result.leaks


def test_an_unparseable_task_that_leaks_is_still_a_leak(tmp_path):
    """Unproven must not mask a finding.

    A degraded plant is a SUBSET of production's render, and a superset can only
    add matches — so a check scoring >0 against the smaller plant would score >0
    in production too. The leak is real, and stays exit 1 rather than being
    softened to "incomplete".
    """
    _make_unparseable_task(tmp_path, A_BAD_TASK_TOML, check=LEAKING_CHECK)

    result = noop_leak_sweep.sweep(tmp_path)

    assert len(result.leaks) == 1
    assert result.n_unproven == 1
    assert noop_leak_sweep.main([str(tmp_path)]) == 1


# --- what the sweep reports to CI ------------------------------------------

_LEAK = Leak(
    task_id="fixture-task-001",
    task_path="incident_response/fixture-task-001",
    checkpoint="root_cause_identified",
    check_file="check_root_cause.sh",
    score=1.0,
)

_ALLOW_LEAK = "fixture-task-001:root_cause_identified"


def _stub_sweep(monkeypatch, result: SweepResult) -> None:
    monkeypatch.setattr(noop_leak_sweep, "sweep", lambda root: result)


@pytest.mark.parametrize(
    "leaks,n_tasks,n_unproven,allow,expected",
    [
        ([], 1, 0, [], 0),  # clean
        ([], 1, 1, [], 2),  # a check went unproven
        ([], 0, 0, [], 2),  # swept nothing: not a clean bill of health
        ([_LEAK], 1, 1, [], 1),  # a real leak outranks incompleteness
        ([_LEAK], 1, 1, [_ALLOW_LEAK], 2),  # allowed leak leaves the incompleteness
        ([_LEAK], 1, 0, [_ALLOW_LEAK], 0),  # allowed leak, nothing else to report
    ],
)
def test_exit_code(monkeypatch, tmp_path, leaks, n_tasks, n_unproven, allow, expected):
    """The exit-code policy, as a table.

    Note the last two rows: ``--allow`` takes an entry named as task.toml
    registers the checkpoint (``root_cause_identified``), not the verifier's
    filename stem.
    """
    _stub_sweep(
        monkeypatch, SweepResult(leaks, n_tasks=n_tasks, n_checks=2, n_unproven=n_unproven)
    )
    argv = [str(tmp_path), *(a for entry in allow for a in ("--allow", entry))]

    assert noop_leak_sweep.main(argv) == expected


def test_incompleteness_is_reported_even_when_a_leak_sets_the_exit_code(
    monkeypatch, tmp_path, capsys
):
    """The exit code names one fact; both are still reported."""
    _stub_sweep(monkeypatch, SweepResult([_LEAK], n_tasks=1, n_checks=2, n_unproven=1))

    assert noop_leak_sweep.main([str(tmp_path)]) == 1
    assert "incomplete" in capsys.readouterr().err
