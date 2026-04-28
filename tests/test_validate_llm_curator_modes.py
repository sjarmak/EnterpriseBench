"""Tests for scripts/validation/validate_llm_curator_modes.py (bead 0rv.17)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import dedent

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts" / "validation"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_llm_curator_modes as mod  # noqa: E402


def _write_task(
    base: Path,
    name: str,
    *,
    stratum: str | None,
    modes: list[str] | None,
    with_expected_solution: bool,
) -> Path:
    """Build a minimal task directory."""
    d = base / name
    d.mkdir(parents=True)
    stratum_line = (
        f'difficulty_stratum = "{stratum}"\n' if stratum is not None else ""
    )
    modes_line = (
        "verification_modes = ["
        + ", ".join(f'"{m}"' for m in modes)
        + "]\n"
        if modes is not None
        else ""
    )
    (d / "task.toml").write_text(
        dedent(
            f"""
            # Test task fixture

            {stratum_line}{modes_line}
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


def test_pass_when_eligible_multi_repo_has_curator(tmp_path: Path) -> None:
    """A correctly-configured multi-repo task passes all gates."""
    _write_task(
        tmp_path,
        "ok",
        stratum="dual_repo",
        modes=["deterministic", "llm_curator"],
        with_expected_solution=True,
    )

    report = mod.validate(tmp_path)

    assert report.ok()
    assert report.failures == []


def test_fail_when_curator_without_expected_solution(tmp_path: Path) -> None:
    """Gate A: ``llm_curator`` requires a sibling expected_solution.json."""
    _write_task(
        tmp_path,
        "bad",
        stratum="dual_repo",
        modes=["deterministic", "llm_curator"],
        with_expected_solution=False,
    )

    report = mod.validate(tmp_path)

    assert not report.ok()
    assert any("no expected_solution.json sibling" in f for f in report.failures)


@pytest.mark.parametrize(
    "stratum",
    ["calibration", "large_single", "monorepo_cross_package"],
)
def test_fail_when_single_repo_has_curator(
    tmp_path: Path, stratum: str
) -> None:
    """Gate B: single-repo strata must not have ``llm_curator`` enabled."""
    _write_task(
        tmp_path,
        "bad",
        stratum=stratum,
        modes=["deterministic", "llm_curator"],
        with_expected_solution=True,
    )

    report = mod.validate(tmp_path)

    assert not report.ok()
    assert any("single-repo stratum" in f for f in report.failures)


def test_fail_when_multi_repo_with_es_missing_curator(tmp_path: Path) -> None:
    """Gate C: a multi-repo task with expected_solution.json must opt in."""
    _write_task(
        tmp_path,
        "lazy",
        stratum="tri_repo",
        modes=["deterministic"],
        with_expected_solution=True,
    )

    report = mod.validate(tmp_path)

    assert not report.ok()
    assert any("missing llm_curator" in f for f in report.failures)


def test_pass_when_multi_repo_without_expected_solution(
    tmp_path: Path,
) -> None:
    """Gate C does not fire when curation is genuinely pending."""
    _write_task(
        tmp_path,
        "pending",
        stratum="dual_repo",
        modes=["deterministic"],
        with_expected_solution=False,
    )

    report = mod.validate(tmp_path)

    assert report.ok()


def test_pass_for_single_repo_without_curator(tmp_path: Path) -> None:
    """Single-repo tasks with deterministic-only modes are fine."""
    _write_task(
        tmp_path,
        "single",
        stratum="large_single",
        modes=["deterministic"],
        with_expected_solution=True,
    )

    report = mod.validate(tmp_path)

    assert report.ok()


def test_main_emits_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--json`` emits a parseable payload with task details."""
    _write_task(
        tmp_path,
        "ok",
        stratum="dual_repo",
        modes=["deterministic", "llm_curator"],
        with_expected_solution=True,
    )

    rc = mod.main([str(tmp_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["failures"] == []
    assert payload["tasks"][0]["has_llm_curator"] is True


def test_main_returns_nonzero_when_validation_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI returns exit code 1 on any gate failure."""
    _write_task(
        tmp_path,
        "bad",
        stratum="dual_repo",
        modes=["deterministic", "llm_curator"],
        with_expected_solution=False,
    )

    rc = mod.main([str(tmp_path)])

    assert rc == 1
    out = capsys.readouterr().out
    assert "FAILURES" in out
