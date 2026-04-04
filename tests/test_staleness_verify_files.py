"""Tests for the --verify-files flag in scripts/infra/check_repo_staleness.py."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import textwrap

import pytest

sys.path.insert(
    0,
    str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "infra"),
)
from check_repo_staleness import (
    RequiredFileEntry,
    format_verify_files_report,
    scan_required_files,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_TASK_TOML = textwrap.dedent("""\
    difficulty_stratum = "dual_repo"
    mcp_suite = "eb_v1"

    [task]
    id = "test-task-001"
    suite = "test_suite"
    task_type = "api_contract"
    difficulty = "medium"
    session_type = "single"
    description = "A test task"
    prompt = "Do the thing."

    [[repos]]
    url = "https://github.com/org/repo-alpha"
    rev = "v1.0.0"
    path = "repo-alpha"
    role = "primary"

    [[repos]]
    url = "https://github.com/org/repo-beta"
    rev = "abc123"
    path = "repo-beta"
    role = "consumer"

    [ground_truth]
    tiers = ["deterministic"]

    [[ground_truth.required_files]]
    path = "src/main.py"
    repo = "repo-alpha"
    confidence = 0.95
    source = "deterministic"

    [[ground_truth.required_files]]
    path = "lib/util.go"
    repo = "repo-beta"
    confidence = 0.80
    source = "deterministic"
""")

TASK_NO_REQUIRED_FILES = textwrap.dedent("""\
    [task]
    id = "no-rf-001"
    suite = "test_suite"
    task_type = "config_drift"
    difficulty = "easy"
    session_type = "single"
    description = "Task without required files"
    prompt = "Nothing."

    [[repos]]
    url = "https://github.com/org/repo-gamma"
    rev = "v2.0"
    path = "repo-gamma"
    role = "primary"

    [ground_truth]
    tiers = ["deterministic"]
""")


def _create_task(tmp_path: pathlib.Path, suite: str, name: str, content: str) -> None:
    """Create a task.toml file in the expected directory structure."""
    task_dir = tmp_path / suite / name
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.toml").write_text(content)


# ---------------------------------------------------------------------------
# Tests: CLI flag recognition
# ---------------------------------------------------------------------------


class TestVerifyFilesFlag:
    def test_help_shows_verify_files(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/infra/check_repo_staleness.py", "--help"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert "--verify-files" in result.stdout

    def test_verify_files_flag_accepted(self, tmp_path: pathlib.Path) -> None:
        """The flag should be accepted without error even with empty benchmarks dir."""
        benchmarks = tmp_path / "benchmarks"
        benchmarks.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                "scripts/infra/check_repo_staleness.py",
                "--verify-files",
                "--benchmarks-dir",
                str(benchmarks),
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "No ground_truth.required_files" in result.stdout


# ---------------------------------------------------------------------------
# Tests: scan_required_files
# ---------------------------------------------------------------------------


class TestScanRequiredFiles:
    def test_basic_scan(self, tmp_path: pathlib.Path) -> None:
        _create_task(tmp_path, "suite_a", "task-001", SAMPLE_TASK_TOML)
        entries = scan_required_files(tmp_path)
        assert len(entries) == 2
        assert all(isinstance(e, RequiredFileEntry) for e in entries)

    def test_cross_reference_repos(self, tmp_path: pathlib.Path) -> None:
        _create_task(tmp_path, "suite_a", "task-001", SAMPLE_TASK_TOML)
        entries = scan_required_files(tmp_path)

        alpha_entry = next(e for e in entries if e.repo_name == "repo-alpha")
        assert alpha_entry.repo_url == "https://github.com/org/repo-alpha"
        assert alpha_entry.pinned_rev == "v1.0.0"
        assert alpha_entry.file_path == "src/main.py"
        assert alpha_entry.confidence == 0.95

        beta_entry = next(e for e in entries if e.repo_name == "repo-beta")
        assert beta_entry.repo_url == "https://github.com/org/repo-beta"
        assert beta_entry.pinned_rev == "abc123"
        assert beta_entry.file_path == "lib/util.go"

    def test_task_id_extracted(self, tmp_path: pathlib.Path) -> None:
        _create_task(tmp_path, "suite_a", "task-001", SAMPLE_TASK_TOML)
        entries = scan_required_files(tmp_path)
        assert all(e.task_id == "test-task-001" for e in entries)

    def test_task_path_relative(self, tmp_path: pathlib.Path) -> None:
        _create_task(tmp_path, "suite_a", "task-001", SAMPLE_TASK_TOML)
        entries = scan_required_files(tmp_path)
        assert all("suite_a/task-001/task.toml" in e.task_path for e in entries)

    def test_skips_archived(self, tmp_path: pathlib.Path) -> None:
        _create_task(tmp_path, "_archived", "old-task", SAMPLE_TASK_TOML)
        entries = scan_required_files(tmp_path)
        assert entries == []

    def test_skips_tasks_without_required_files(self, tmp_path: pathlib.Path) -> None:
        _create_task(tmp_path, "suite_b", "no-rf", TASK_NO_REQUIRED_FILES)
        entries = scan_required_files(tmp_path)
        assert entries == []

    def test_multiple_tasks(self, tmp_path: pathlib.Path) -> None:
        _create_task(tmp_path, "suite_a", "task-001", SAMPLE_TASK_TOML)
        _create_task(tmp_path, "suite_b", "no-rf", TASK_NO_REQUIRED_FILES)
        entries = scan_required_files(tmp_path)
        assert len(entries) == 2  # only from SAMPLE_TASK_TOML

    def test_sorted_by_task_id_then_path(self, tmp_path: pathlib.Path) -> None:
        _create_task(tmp_path, "suite_a", "task-001", SAMPLE_TASK_TOML)
        entries = scan_required_files(tmp_path)
        keys = [(e.task_id, e.file_path) for e in entries]
        assert keys == sorted(keys)

    def test_empty_dir(self, tmp_path: pathlib.Path) -> None:
        entries = scan_required_files(tmp_path)
        assert entries == []

    def test_frozen_dataclass(self, tmp_path: pathlib.Path) -> None:
        _create_task(tmp_path, "suite_a", "task-001", SAMPLE_TASK_TOML)
        entries = scan_required_files(tmp_path)
        with pytest.raises(AttributeError):
            entries[0].task_id = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: format_verify_files_report
# ---------------------------------------------------------------------------


class TestFormatReport:
    def _sample_entries(self) -> list[RequiredFileEntry]:
        return [
            RequiredFileEntry(
                task_id="task-001",
                task_path="suite/task-001/task.toml",
                file_path="src/main.py",
                repo_name="repo-alpha",
                repo_url="https://github.com/org/repo-alpha",
                pinned_rev="v1.0.0",
                confidence=0.95,
            ),
            RequiredFileEntry(
                task_id="task-001",
                task_path="suite/task-001/task.toml",
                file_path="lib/util.go",
                repo_name="repo-beta",
                repo_url="https://github.com/org/repo-beta",
                pinned_rev="abc123",
                confidence=0.80,
            ),
        ]

    def test_human_readable_format(self) -> None:
        report = format_verify_files_report(self._sample_entries())
        assert "Found 2 required_files" in report
        assert "[task-001]" in report
        assert "repo-alpha/src/main.py" in report
        assert "@ v1.0.0" in report
        assert "confidence: 0.95" in report

    def test_json_format(self) -> None:
        report = format_verify_files_report(self._sample_entries(), json_output=True)
        data = json.loads(report)
        assert data["total_required_files"] == 2
        assert len(data["entries"]) == 2
        assert data["entries"][0]["task_id"] == "task-001"
        assert data["entries"][0]["pinned_rev"] == "v1.0.0"

    def test_empty_entries_human(self) -> None:
        report = format_verify_files_report([])
        assert "No ground_truth.required_files" in report

    def test_empty_entries_json(self) -> None:
        report = format_verify_files_report([], json_output=True)
        data = json.loads(report)
        assert data["total_required_files"] == 0
        assert data["entries"] == []


# ---------------------------------------------------------------------------
# Tests: CLI JSON output
# ---------------------------------------------------------------------------


class TestVerifyFilesCLI:
    def test_json_output(self, tmp_path: pathlib.Path) -> None:
        _create_task(tmp_path, "suite_a", "task-001", SAMPLE_TASK_TOML)
        result = subprocess.run(
            [
                sys.executable,
                "scripts/infra/check_repo_staleness.py",
                "--verify-files",
                "--json",
                "--benchmarks-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["total_required_files"] == 2


# ---------------------------------------------------------------------------
# Tests: existing staleness functionality unchanged
# ---------------------------------------------------------------------------


class TestExistingStalenessUnchanged:
    def test_staleness_check_still_works(self, tmp_path: pathlib.Path) -> None:
        """Verify the original staleness check works after adding --verify-files."""
        data = [
            {
                "url": "https://github.com/a/b",
                "pinned_rev": "v1",
                "last_verified": "2020-01-01",
            }
        ]
        manifest = tmp_path / "repo_versions.json"
        manifest.write_text(json.dumps(data))

        result = subprocess.run(
            [
                sys.executable,
                "scripts/infra/check_repo_staleness.py",
                "--json",
                "--manifest",
                str(manifest),
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["stale_count"] == 1
        assert result.returncode == 1

    def test_no_stale_still_returns_zero(self, tmp_path: pathlib.Path) -> None:
        from datetime import date

        today = date.today().isoformat()
        data = [
            {
                "url": "https://github.com/a/b",
                "pinned_rev": "v1",
                "last_verified": today,
            }
        ]
        manifest = tmp_path / "repo_versions.json"
        manifest.write_text(json.dumps(data))

        result = subprocess.run(
            [
                sys.executable,
                "scripts/infra/check_repo_staleness.py",
                "--manifest",
                str(manifest),
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "up to date" in result.stdout
