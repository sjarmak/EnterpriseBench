"""Tests for scripts/validation/validate_expected_solutions.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts" / "validation"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_expected_solutions as ves  # noqa: E402


@pytest.fixture
def task_dir(tmp_path: Path) -> Path:
    """Build a minimal task directory with task.toml and ground_truth.json."""
    d = tmp_path / "fake-task-001"
    d.mkdir()
    (d / "task.toml").write_text(
        dedent(
            """
            [task]
            id = "fake-task-001"
            suite = "incident_response"
            difficulty = "hard"
            session_type = "single"

            [[repos]]
            url = "https://github.com/foo/bar"
            rev = "v1.0.0"
            path = "bar"
            role = "primary"

            [[checkpoints]]
            name = "root_cause_identification"
            weight = 0.4
            verifier = "checks/check_root_cause.sh"

            [[checkpoints]]
            name = "remediation_proposal"
            weight = 0.2
            verifier = "checks/check_remediation.sh"
            """
        ).strip()
    )
    return d


def _write_solution(task_dir: Path, payload: dict[str, Any]) -> Path:
    p = task_dir / "expected_solution.json"
    p.write_text(json.dumps(payload, indent=2))
    return p


def test_valid_solution_passes(task_dir: Path) -> None:
    _write_solution(
        task_dir,
        {
            "task_id": "fake-task-001",
            "checkpoints": {
                "root_cause_identification": {
                    "expected_solution": "Root cause is foo in bar/baz.go",
                    "evaluation_criteria": [
                        "Must mention bar/baz.go",
                        "Must mention foo function",
                        "Must explain the failure mode",
                    ],
                },
                "remediation_proposal": {
                    "expected_solution": "Fix is to update bar/baz.go",
                    "evaluation_criteria": [
                        "Must propose updating bar/baz.go",
                        "Must address the root cause",
                    ],
                },
            },
        },
    )
    result = ves.validate_task(task_dir)
    assert result.ok, result.errors


def test_missing_file_treated_as_skip(task_dir: Path) -> None:
    """Tasks without expected_solution.json are skipped, not failed."""
    result = ves.validate_task(task_dir)
    assert result.skipped


def test_task_id_mismatch_fails(task_dir: Path) -> None:
    _write_solution(
        task_dir,
        {
            "task_id": "WRONG-ID",
            "checkpoints": {
                "root_cause_identification": {
                    "expected_solution": "x",
                    "evaluation_criteria": ["a", "b"],
                },
                "remediation_proposal": {
                    "expected_solution": "y",
                    "evaluation_criteria": ["a", "b"],
                },
            },
        },
    )
    result = ves.validate_task(task_dir)
    assert not result.ok
    assert any("task_id" in e for e in result.errors)


def test_missing_checkpoint_fails(task_dir: Path) -> None:
    """C1: Every task.toml checkpoint must have a key in expected_solution."""
    _write_solution(
        task_dir,
        {
            "task_id": "fake-task-001",
            "checkpoints": {
                "root_cause_identification": {
                    "expected_solution": "x",
                    "evaluation_criteria": ["a", "b"],
                },
                # remediation_proposal MISSING
            },
        },
    )
    result = ves.validate_task(task_dir)
    assert not result.ok
    assert any("remediation_proposal" in e for e in result.errors)


def test_extra_checkpoint_fails(task_dir: Path) -> None:
    """A checkpoint key not declared in task.toml should fail (typo guard)."""
    _write_solution(
        task_dir,
        {
            "task_id": "fake-task-001",
            "checkpoints": {
                "root_cause_identification": {
                    "expected_solution": "x",
                    "evaluation_criteria": ["a", "b"],
                },
                "remediation_proposal": {
                    "expected_solution": "y",
                    "evaluation_criteria": ["a", "b"],
                },
                "made_up_checkpoint": {
                    "expected_solution": "z",
                    "evaluation_criteria": ["a", "b"],
                },
            },
        },
    )
    result = ves.validate_task(task_dir)
    assert not result.ok
    assert any("made_up_checkpoint" in e for e in result.errors)


def test_empty_expected_solution_fails(task_dir: Path) -> None:
    _write_solution(
        task_dir,
        {
            "task_id": "fake-task-001",
            "checkpoints": {
                "root_cause_identification": {
                    "expected_solution": "",
                    "evaluation_criteria": ["a", "b"],
                },
                "remediation_proposal": {
                    "expected_solution": "y",
                    "evaluation_criteria": ["a", "b"],
                },
            },
        },
    )
    result = ves.validate_task(task_dir)
    assert not result.ok
    assert any("expected_solution" in e and "empty" in e for e in result.errors)


def test_too_few_criteria_fails(task_dir: Path) -> None:
    _write_solution(
        task_dir,
        {
            "task_id": "fake-task-001",
            "checkpoints": {
                "root_cause_identification": {
                    "expected_solution": "x",
                    "evaluation_criteria": ["only one"],
                },
                "remediation_proposal": {
                    "expected_solution": "y",
                    "evaluation_criteria": ["a", "b"],
                },
            },
        },
    )
    result = ves.validate_task(task_dir)
    assert not result.ok
    assert any(
        "evaluation_criteria" in e and "root_cause_identification" in e
        for e in result.errors
    )


def test_high_weight_checkpoint_wants_three_criteria(task_dir: Path) -> None:
    """H3: weight > 0.30 wants >= 3 criteria — warning, not fail."""
    _write_solution(
        task_dir,
        {
            "task_id": "fake-task-001",
            "checkpoints": {
                # root_cause weight=0.4, only 2 criteria → warning
                "root_cause_identification": {
                    "expected_solution": "x",
                    "evaluation_criteria": ["a", "b"],
                },
                "remediation_proposal": {
                    "expected_solution": "y",
                    "evaluation_criteria": ["a", "b"],
                },
            },
        },
    )
    result = ves.validate_task(task_dir)
    assert result.ok  # only a warning
    assert any("weight" in w and "0.4" in w for w in result.warnings)


def test_curation_required_flag_fails(task_dir: Path) -> None:
    """H2: any checkpoint flagged _curation_required: true must fail."""
    _write_solution(
        task_dir,
        {
            "task_id": "fake-task-001",
            "checkpoints": {
                "root_cause_identification": {
                    "expected_solution": "x",
                    "evaluation_criteria": ["a", "b"],
                    "_curation_required": True,
                },
                "remediation_proposal": {
                    "expected_solution": "y",
                    "evaluation_criteria": ["a", "b"],
                },
            },
        },
    )
    result = ves.validate_task(task_dir)
    assert not result.ok
    assert any("_curation_required" in e for e in result.errors)


def test_invalid_json_fails(task_dir: Path) -> None:
    (task_dir / "expected_solution.json").write_text("{ invalid json")
    result = ves.validate_task(task_dir)
    assert not result.ok
    assert any("parse" in e.lower() or "json" in e.lower() for e in result.errors)


def test_top_level_keys_required(task_dir: Path) -> None:
    _write_solution(task_dir, {"task_id": "fake-task-001"})  # checkpoints missing
    result = ves.validate_task(task_dir)
    assert not result.ok
    assert any("checkpoints" in e for e in result.errors)


def test_existing_repo_example_validates(task_dir: Path) -> None:
    """The reference example must pass validation."""
    real_task_dir = (
        REPO_ROOT
        / "benchmarks"
        / "incident_response"
        / "incident-investigation-004"
    )
    if not (real_task_dir / "expected_solution.json").exists():
        pytest.skip("reference task missing")
    result = ves.validate_task(real_task_dir)
    assert result.ok, result.errors


def test_walk_skips_symlink_outside_tree(tmp_path: Path) -> None:
    """Path-traversal guard: a task.toml symlinked from outside is skipped."""
    real_outside = tmp_path / "outside"
    real_outside.mkdir()
    (real_outside / "task.toml").write_text("[task]\nid = 'evil'\n")

    inside = tmp_path / "tree"
    inside.mkdir()
    # Symlinked task dir that resolves outside the tree root
    (inside / "evil-task").symlink_to(real_outside)

    found = ves._walk_task_dirs(inside)
    # The symlinked dir resolves outside the tree, so it must be skipped
    for d in found:
        assert real_outside not in d.parents
        assert d != real_outside


def test_path_pattern_rejects_version_prefix() -> None:
    """Regex tightening: 'v1.2.3/foo.go' looks like a version, not a path."""
    crit = [
        "Reproduces on v1.2.3/something.go but not on src/real/path.go",
    ]
    paths = ves._extract_paths_from_criteria(crit)
    # Only the real-looking path should be extracted, not the version-y one
    assert "src/real/path.go" in paths
    assert not any(p.startswith("v1.") for p in paths), paths


def test_github_url_quotes_path_and_ref(monkeypatch) -> None:
    """URL-encoding guard: a ref with '?' must not split the query string."""
    captured: dict[str, str] = {}

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):  # noqa: ARG001
        captured["url"] = req.full_url
        return FakeResp()

    monkeypatch.setattr(ves.urllib.request, "urlopen", fake_urlopen)
    ves._github_path_exists(
        "https://github.com/foo/bar",
        "abc?token=x",
        "src/path with space.go",
        "tok",
    )
    # Both ref and path must be percent-encoded
    assert "ref=abc%3Ftoken%3Dx" in captured["url"]
    assert "path%20with%20space.go" in captured["url"]


def test_github_path_with_dotdot_rejected(monkeypatch) -> None:
    """Defense-in-depth: '..' in path returns False without making a request."""
    called = False

    def should_not_be_called(*args, **kwargs):  # noqa: ARG001
        nonlocal called
        called = True
        raise AssertionError("should not have made a request")

    monkeypatch.setattr(ves.urllib.request, "urlopen", should_not_be_called)
    result = ves._github_path_exists(
        "https://github.com/foo/bar", "main", "../escape.go", "tok"
    )
    assert result is False
    assert called is False


def test_path_attribution_records_each_checkpoint(monkeypatch, task_dir: Path) -> None:
    """Path-attribution fix: a path referenced in multiple checkpoints
    produces an error per checkpoint, not just the first."""
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    # Force the GitHub check to return False so an error is recorded
    monkeypatch.setattr(
        ves, "_github_path_exists", lambda *args, **kwargs: False
    )
    _write_solution(
        task_dir,
        {
            "task_id": "fake-task-001",
            "checkpoints": {
                "root_cause_identification": {
                    "expected_solution": "x",
                    "evaluation_criteria": [
                        "Must reference path/to/file.go",
                        "Must trace to path/to/file.go",
                    ],
                },
                "remediation_proposal": {
                    "expected_solution": "y",
                    "evaluation_criteria": [
                        "Must fix path/to/file.go",
                        "Must keep tests green",
                    ],
                },
            },
        },
    )
    result = ves.validate_task(task_dir, check_paths=True)
    assert not result.ok
    rc_errs = [e for e in result.errors if "root_cause_identification" in e]
    rem_errs = [e for e in result.errors if "remediation_proposal" in e]
    assert rc_errs and rem_errs, result.errors


def test_path_existence_check_skipped_without_token(task_dir: Path, monkeypatch) -> None:
    """H1: file-path-at-SHA check needs GITHUB_TOKEN; skip with warning otherwise."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    _write_solution(
        task_dir,
        {
            "task_id": "fake-task-001",
            "checkpoints": {
                "root_cause_identification": {
                    "expected_solution": "Bug is in path/to/missing.go",
                    "evaluation_criteria": [
                        "Must reference path/to/missing.go",
                        "Must explain why",
                    ],
                },
                "remediation_proposal": {
                    "expected_solution": "y",
                    "evaluation_criteria": ["a", "b"],
                },
            },
        },
    )
    result = ves.validate_task(task_dir, check_paths=True)
    # Without token, path check is skipped with warning, structural check still passes
    assert result.ok
    assert any("GITHUB_TOKEN" in w for w in result.warnings)
