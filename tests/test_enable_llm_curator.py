"""Tests for scripts/validation/enable_llm_curator.py (bead 0rv.17)."""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts" / "validation"
sys.path.insert(0, str(SCRIPTS_DIR))

import enable_llm_curator as mod  # noqa: E402


def _write_task(
    base: Path,
    name: str,
    *,
    stratum: str | None,
    modes_line: str = 'verification_modes = ["deterministic"]',
    with_expected_solution: bool = True,
    extra_top: str = "",
) -> Path:
    """Build a minimal task directory for a unit test."""
    d = base / name
    d.mkdir(parents=True)
    stratum_line = (
        f'difficulty_stratum = "{stratum}"\n' if stratum is not None else ""
    )
    (d / "task.toml").write_text(
        dedent(
            f"""
            # Test task fixture

            {stratum_line}{modes_line}
            {extra_top}

            [task]
            id = "{name}"
            suite = "incident_response"
            difficulty = "hard"
            """
        ).strip()
        + "\n"
    )
    if with_expected_solution:
        (d / "expected_solution.json").write_text(
            '{"task_id": "' + name + '", "checkpoints": {}}\n'
        )
    return d


def test_iter_task_dirs_skips_archived_and_mined(tmp_path: Path) -> None:
    """``_archived`` and ``mined`` subtrees are excluded from iteration."""
    _write_task(tmp_path / "active", "good", stratum="dual_repo")
    _write_task(tmp_path / "_archived", "old", stratum="dual_repo")
    _write_task(tmp_path / "mined", "candidate", stratum="dual_repo")

    dirs = list(mod.iter_task_dirs(tmp_path))
    names = sorted(d.name for d in dirs)
    assert names == ["good"]


@pytest.mark.parametrize(
    "stratum",
    ["dual_repo", "tri_repo", "multi_repo", "quad_repo"],
)
def test_process_task_updates_multi_repo_with_expected_solution(
    tmp_path: Path, stratum: str
) -> None:
    """Eligible multi-repo tasks get ``llm_curator`` appended."""
    d = _write_task(tmp_path, "t", stratum=stratum)

    outcome = mod.process_task(d)

    assert outcome.action == "updated"
    assert outcome.stratum == stratum
    assert mod.CANONICAL_BOTH in (d / "task.toml").read_text()


@pytest.mark.parametrize(
    "stratum",
    ["calibration", "large_single", "monorepo_cross_package"],
)
def test_process_task_skips_single_repo_strata(
    tmp_path: Path, stratum: str
) -> None:
    """Single-repo strata are explicitly excluded by acceptance criterion."""
    d = _write_task(tmp_path, "t", stratum=stratum)

    outcome = mod.process_task(d)

    assert outcome.action == "skipped"
    assert "not multi-repo" in outcome.reason
    assert mod.CANONICAL_DETERMINISTIC in (d / "task.toml").read_text()
    assert mod.CANONICAL_BOTH not in (d / "task.toml").read_text()


def test_process_task_skips_when_expected_solution_missing(
    tmp_path: Path,
) -> None:
    """A multi-repo task without expected_solution.json must not be enabled."""
    d = _write_task(
        tmp_path,
        "t",
        stratum="dual_repo",
        with_expected_solution=False,
    )

    outcome = mod.process_task(d)

    assert outcome.action == "skipped"
    assert "expected_solution.json missing" in outcome.reason


def test_process_task_already_enabled_is_idempotent(tmp_path: Path) -> None:
    """Re-running on an already-enabled task is a no-op."""
    d = _write_task(
        tmp_path,
        "t",
        stratum="dual_repo",
        modes_line=mod.CANONICAL_BOTH,
    )

    outcome = mod.process_task(d)

    assert outcome.action == "already_enabled"


def test_process_task_dry_run_does_not_write(tmp_path: Path) -> None:
    """``--dry-run`` plans the change but leaves the file untouched."""
    d = _write_task(tmp_path, "t", stratum="dual_repo")
    before = (d / "task.toml").read_text()

    outcome = mod.process_task(d, dry_run=True)

    assert outcome.action == "updated"
    assert (d / "task.toml").read_text() == before


def test_process_task_errors_on_unknown_modes_format(tmp_path: Path) -> None:
    """A non-canonical modes line should error so a human reviews it."""
    d = _write_task(
        tmp_path,
        "t",
        stratum="dual_repo",
        modes_line='verification_modes = ["custom_mode"]',
    )

    outcome = mod.process_task(d)

    assert outcome.action == "error"
    assert "no canonical" in outcome.reason


def test_process_task_errors_on_missing_task_toml(tmp_path: Path) -> None:
    """A directory without task.toml is reported as an error."""
    d = tmp_path / "broken"
    d.mkdir()
    (d / "expected_solution.json").write_text("{}")

    outcome = mod.process_task(d)

    assert outcome.action == "error"
    assert "task.toml missing" in outcome.reason


def test_run_aggregates_outcomes(tmp_path: Path) -> None:
    """``run`` walks the tree and tallies actions across many tasks."""
    _write_task(tmp_path / "a", "good", stratum="dual_repo")
    _write_task(tmp_path / "b", "single", stratum="large_single")
    _write_task(
        tmp_path / "c",
        "no_es",
        stratum="tri_repo",
        with_expected_solution=False,
    )

    report = mod.run(tmp_path)

    assert {o.action for o in report.outcomes} == {"updated", "skipped"}
    assert len(report.by_action("updated")) == 1
    assert len(report.by_action("skipped")) == 2
    assert not report.has_errors()


def test_main_returns_nonzero_on_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI returns exit code 1 if any task errored."""
    d = tmp_path / "broken"
    d.mkdir()
    (d / "expected_solution.json").write_text("{}")
    # Missing task.toml — script should report an error for this dir.
    (d / "task.toml").write_text(
        'difficulty_stratum = "dual_repo"\n'
        'verification_modes = ["deterministic", "custom"]\n'
    )

    rc = mod.main([str(tmp_path)])

    assert rc == 1
    out = capsys.readouterr().out
    assert "ERRORS" in out


def test_main_emits_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--json`` emits a parseable payload."""
    import json

    _write_task(tmp_path, "t", stratum="dual_repo")

    rc = mod.main([str(tmp_path), "--dry-run", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert isinstance(payload["outcomes"], list)
    assert payload["outcomes"][0]["action"] == "updated"
