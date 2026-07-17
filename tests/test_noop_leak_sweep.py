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

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))

import noop_leak_sweep  # noqa: E402
from noop_leak_sweep import Leak, SweepResult  # noqa: E402
from run_task import _build_instruction_text  # noqa: E402

# Answer-schema keywords production's output appendix carries into EVERY
# workspace, in every mode. A check globbing workspace-level *.md for any of them
# — the hpcsv shape — leaks in production; a sweep that plants only the raw
# instruction.md would score it clean.
APPENDIX_KEYWORDS = (
    "source_files",
    "error_chain",
    "trigger_conditions",
    "code_paths",
    "severity",
    "related_issues",
)

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


def _make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


# --- what the sweep plants -------------------------------------------------


def test_planted_workspace_carries_the_production_output_appendix(tmp_path):
    task_dir = _make_task(tmp_path)
    ws = _make_workspace(tmp_path)

    noop_leak_sweep._plant_workspace(task_dir, ws)

    planted = (ws / "instruction.md").read_text()
    missing = [kw for kw in APPENDIX_KEYWORDS if kw not in planted]
    assert not missing, (
        f"planted workspace is missing output-appendix keywords {missing}, which "
        "production puts in /workspace/instruction.md in every mode. A check "
        "keyed on them would leak in production and read clean here."
    )


def test_planted_instruction_is_the_production_baseline_render(tmp_path):
    """The plant is production's own render, not a re-derivation of it."""
    task_dir = _make_task(tmp_path)
    ws = _make_workspace(tmp_path)

    noop_leak_sweep._plant_workspace(task_dir, ws)

    assert (ws / "instruction.md").read_text() == _build_instruction_text(
        task_dir, mode="baseline"
    )


def test_planted_instruction_is_a_strict_superset_of_the_raw_file(tmp_path):
    """The bug being fixed: the raw file alone is less than the agent really sees."""
    task_dir = _make_task(tmp_path)
    ws = _make_workspace(tmp_path)

    noop_leak_sweep._plant_workspace(task_dir, ws)

    planted = (ws / "instruction.md").read_text()
    assert RAW_INSTRUCTION in planted
    assert planted != RAW_INSTRUCTION


def test_planted_workspace_honours_require_grounded_citations(tmp_path):
    """The appendix varies on the task's citations flag, not only on the mode.

    Production reads ``ground_truth.require_grounded_citations`` from task.toml
    and passes it in (run_task.py ``_setup_container``); when it is set, the
    appendix grows a ``citations`` block naming ``evidence_span`` and a verbatim
    quoting requirement. Defaulting the flag to False would replant the very bug
    this bead fixes — a workspace that is a strict subset of production's — just
    along the citations axis instead of the mode axis.
    """
    task_dir = _make_task(tmp_path, grounded=True)
    ws = _make_workspace(tmp_path)

    noop_leak_sweep._plant_workspace(task_dir, ws)

    planted = (ws / "instruction.md").read_text()
    assert planted == _build_instruction_text(
        task_dir, mode="baseline", require_grounded_citations=True
    )
    assert '"citations"' in planted
    assert "evidence_span" in planted


def test_planted_workspace_omits_citations_when_the_task_does_not_require_them(tmp_path):
    """The flag is read from the task, not hardcoded on: a plant that always
    carried the citations block would be a strict SUPERSET for most of the corpus
    and could invent a leak that production cannot produce."""
    task_dir = _make_task(tmp_path, grounded=False)
    ws = _make_workspace(tmp_path)

    noop_leak_sweep._plant_workspace(task_dir, ws)

    planted = (ws / "instruction.md").read_text()
    assert planted == _build_instruction_text(task_dir, mode="baseline")
    assert '"citations"' not in planted


def test_plant_skips_a_task_with_no_instruction(tmp_path):
    """No instruction.md means production plants nothing — so neither do we."""
    task_dir = _make_task(tmp_path, instruction=None)
    ws = _make_workspace(tmp_path)

    noop_leak_sweep._plant_workspace(task_dir, ws)

    assert list(ws.iterdir()) == []


# --- what the sweep calls a checkpoint -------------------------------------


def test_checkpoint_name_is_the_name_registered_in_task_toml(tmp_path):
    """`check_root_cause.sh` is the checkpoint `root_cause_identified`."""
    task_dir = _make_task(tmp_path)
    check = task_dir / "checks" / "check_root_cause.sh"
    check.write_text("#!/bin/bash\n")

    assert noop_leak_sweep._checkpoint_name(check, task_dir) == "root_cause_identified"


def test_checkpoint_name_falls_back_to_filename_when_unregistered(tmp_path):
    """Discovery is a glob, so a check absent from task.toml is still audited."""
    task_dir = _make_task(tmp_path)
    check = task_dir / "checks" / "check_unregistered.sh"
    check.write_text("#!/bin/bash\n")

    assert noop_leak_sweep._checkpoint_name(check, task_dir) == "unregistered"


def test_unparseable_task_toml_falls_back_loudly(tmp_path, capsys):
    """A broken task.toml costs naming, not the audit — and never does so silently."""
    task_dir = _make_task(tmp_path)
    (task_dir / "task.toml").write_text("not = valid = toml")
    check = task_dir / "checks" / "check_root_cause.sh"
    check.write_text("#!/bin/bash\n")

    assert noop_leak_sweep._checkpoint_name(check, task_dir) == "root_cause"
    assert "task.toml" in capsys.readouterr().err


def test_structurally_incomplete_task_toml_falls_back_loudly(tmp_path, capsys):
    """A checkpoint missing a required key degrades naming; it must not abort the sweep.

    ``parse_task`` converts a missing ``[task]`` block into a ValueError but
    subscripts ``c["name"]``/``c["weight"]``/``c["verifier"]`` directly, so a
    structurally-valid TOML with an incomplete checkpoint raises a bare KeyError —
    a different class from the syntax errors above, and one no corpus task has
    today. Catching only (OSError, ValueError) let it escape ``sweep``'s per-task
    loop and abort all 141 tasks with a traceback, whose exit code CI reads as an
    infra flake rather than an integrity failure. A guard that dies on one bad
    task.toml is a guard that stops guarding the other 140.
    """
    task_dir = _make_task(tmp_path)
    (task_dir / "task.toml").write_text(
        '[task]\n'
        'id = "fixture-task-001"\n'
        'suite = "incident_response"\n'
        'difficulty = "hard"\n'
        'session_type = "single"\n'
        '\n'
        '[[checkpoints]]\n'
        'name = "root_cause_identified"\n'
        'verifier = "checks/check_root_cause.sh"\n'  # no `weight` -> KeyError
    )
    check = task_dir / "checks" / "check_root_cause.sh"
    check.write_text("#!/bin/bash\n")

    assert noop_leak_sweep._checkpoint_name(check, task_dir) == "root_cause"
    assert "task.toml" in capsys.readouterr().err


def test_a_fresh_sweep_rereads_an_edited_task_toml(tmp_path):
    """The parse cache is scoped to one sweep, so a re-sweep must see disk edits.

    Caching a file's contents is only defensible because task.toml cannot change
    *during* a sweep. Across sweeps it plainly can — fix a task, re-sweep to
    confirm — and an unbounded process-global cache would answer the second sweep
    with the first sweep's parse.
    """
    task_dir = _make_task(tmp_path)
    check = task_dir / "checks" / "check_root_cause.sh"
    check.write_text('#!/bin/bash\necho \'{"score": 0.0}\'\n')

    assert noop_leak_sweep._checkpoint_name(check, task_dir) == "root_cause_identified"

    (task_dir / "task.toml").write_text(
        TASK_TOML.format(grounded="false").replace(
            "root_cause_identified", "renamed_checkpoint"
        )
    )
    noop_leak_sweep.sweep(tmp_path)

    assert noop_leak_sweep._checkpoint_name(check, task_dir) == "renamed_checkpoint"


# --- what the sweep reports to CI ------------------------------------------

_LEAK = Leak(
    task_id="fixture-task-001",
    task_path="incident_response/fixture-task-001",
    checkpoint="root_cause_identified",
    check_file="check_root_cause.sh",
    score=1.0,
)


def _stub_sweep(monkeypatch, result: SweepResult) -> None:
    monkeypatch.setattr(noop_leak_sweep, "sweep", lambda root: result)


def test_clean_sweep_exits_0(monkeypatch, tmp_path):
    _stub_sweep(monkeypatch, SweepResult([], n_tasks=1, n_checks=2, n_errored=0))
    assert noop_leak_sweep.main([str(tmp_path)]) == 0


def test_incomplete_sweep_without_a_leak_exits_2(monkeypatch, tmp_path):
    _stub_sweep(monkeypatch, SweepResult([], n_tasks=1, n_checks=2, n_errored=1))
    assert noop_leak_sweep.main([str(tmp_path)]) == 2


def test_a_real_leak_outranks_incompleteness_in_the_exit_code(monkeypatch, tmp_path, capsys):
    """A leak plus an errored check is a leak: exit 1, not 2.

    Both facts stay true, so both are reported — but the exit code names the
    worse one. Exit 2 ("could not trust the result") understates a run that
    positively found a real leak.
    """
    _stub_sweep(monkeypatch, SweepResult([_LEAK], n_tasks=1, n_checks=2, n_errored=1))

    assert noop_leak_sweep.main([str(tmp_path)]) == 1
    assert "incomplete" in capsys.readouterr().err


def test_an_allowed_leak_does_not_mask_incompleteness(monkeypatch, tmp_path):
    """--allow silences the leak, so the unproven check is what's left to report."""
    _stub_sweep(monkeypatch, SweepResult([_LEAK], n_tasks=1, n_checks=2, n_errored=1))
    argv = [str(tmp_path), "--allow", "fixture-task-001:root_cause_identified"]
    assert noop_leak_sweep.main(argv) == 2


def test_allow_matches_the_checkpoint_name_registered_in_task_toml(monkeypatch, tmp_path):
    """An operator allowlists the name they read in task.toml, not a filename stem."""
    _stub_sweep(monkeypatch, SweepResult([_LEAK], n_tasks=1, n_checks=1, n_errored=0))
    argv = [str(tmp_path), "--allow", "fixture-task-001:root_cause_identified"]
    assert noop_leak_sweep.main(argv) == 0


def test_sweeping_zero_tasks_is_not_a_clean_bill_of_health(monkeypatch, tmp_path):
    _stub_sweep(monkeypatch, SweepResult([], n_tasks=0, n_checks=0, n_errored=0))
    assert noop_leak_sweep.main([str(tmp_path)]) == 2
