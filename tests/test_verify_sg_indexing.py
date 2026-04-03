"""Tests for scripts/infra/verify_sg_indexing.py."""

import json
import os
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT, "scripts", "infra", "verify_sg_indexing.py")

# Import the module for unit testing
sys.path.insert(0, os.path.join(ROOT, "scripts", "infra"))
from verify_sg_indexing import (
    IndexingSummary,
    RepoStatus,
    SuiteStatus,
    compute_summary,
    format_json,
    format_summary,
    load_index,
)


@pytest.fixture
def sample_index() -> dict:
    """Minimal valid index for testing."""
    return {
        "suites": {
            "suite_a": {
                "_status": "pending_verification",
                "_indexed_count": 1,
                "_repo_count": 2,
                "_task_count": 3,
                "repos": [
                    {
                        "name": "org/repo1",
                        "url": "https://github.com/org/repo1",
                        "_indexed": True,
                    },
                    {
                        "name": "org/repo2",
                        "url": "https://github.com/org/repo2",
                        "_indexed": False,
                    },
                ],
            },
            "suite_b": {
                "_status": "pending_verification",
                "_indexed_count": 0,
                "_repo_count": 1,
                "_task_count": 1,
                "repos": [
                    {
                        "name": "org/repo3",
                        "url": "https://github.com/org/repo3",
                        "_indexed": False,
                    },
                ],
            },
        },
        "repos": [
            {
                "sg_name": "sg-evals/org/repo1",
                "github_repo": "org/repo1",
                "_indexed": True,
            },
            {
                "sg_name": "sg-evals/org/repo2",
                "github_repo": "org/repo2",
                "_indexed": False,
            },
            {
                "sg_name": "sg-evals/org/repo3",
                "github_repo": "org/repo3",
                "_indexed": False,
            },
        ],
    }


@pytest.fixture
def sample_index_file(sample_index: dict, tmp_path: os.PathLike) -> str:
    """Write sample index to a temp file and return path."""
    path = os.path.join(str(tmp_path), "test_index.json")
    with open(path, "w") as f:
        json.dump(sample_index, f)
    return path


class TestComputeSummary:
    """Test the compute_summary function."""

    def test_total_repos_count(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        assert summary.total_repos == 3

    def test_indexed_count(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        assert summary.indexed_count == 1

    def test_pending_count(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        assert summary.pending_count == 2

    def test_suite_count(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        assert len(summary.suites) == 2

    def test_suite_a_breakdown(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        suite_a = next(s for s in summary.suites if s.name == "suite_a")
        assert suite_a.total == 2
        assert suite_a.indexed == 1
        assert suite_a.pending == 1

    def test_suite_b_breakdown(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        suite_b = next(s for s in summary.suites if s.name == "suite_b")
        assert suite_b.total == 1
        assert suite_b.indexed == 0
        assert suite_b.pending == 1

    def test_suites_sorted_by_name(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        names = [s.name for s in summary.suites]
        assert names == sorted(names)

    def test_empty_index(self) -> None:
        summary = compute_summary({"repos": [], "suites": {}})
        assert summary.total_repos == 0
        assert summary.indexed_count == 0
        assert summary.pending_count == 0
        assert len(summary.suites) == 0

    def test_all_indexed(self) -> None:
        data = {
            "repos": [
                {"sg_name": "a", "_indexed": True},
                {"sg_name": "b", "_indexed": True},
            ],
            "suites": {},
        }
        summary = compute_summary(data)
        assert summary.indexed_count == 2
        assert summary.pending_count == 0

    def test_suite_without_repos_key(self) -> None:
        """Suite entry missing 'repos' key should default to empty."""
        data = {
            "repos": [{"sg_name": "a", "_indexed": False}],
            "suites": {"empty_suite": {"_status": "pending_verification"}},
        }
        summary = compute_summary(data)
        suite = summary.suites[0]
        assert suite.total == 0
        assert suite.indexed == 0


class TestFormatSummary:
    """Test human-readable output formatting."""

    def test_contains_header(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        output = format_summary(summary)
        assert "Sourcegraph Indexing Status" in output

    def test_contains_totals(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        output = format_summary(summary)
        assert "Total repos:   3" in output
        assert "Indexed:       1" in output
        assert "Pending:       2" in output

    def test_contains_suite_breakdown(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        output = format_summary(summary)
        assert "suite_a: 1/2 indexed, 1 pending" in output
        assert "suite_b: 0/1 indexed, 1 pending" in output


class TestFormatJson:
    """Test JSON output formatting."""

    def test_valid_json(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        output = format_json(summary)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_json_structure(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        output = format_json(summary)
        parsed = json.loads(output)
        assert parsed["total_repos"] == 3
        assert parsed["indexed_count"] == 1
        assert parsed["pending_count"] == 2
        assert "suite_a" in parsed["suites"]
        assert "suite_b" in parsed["suites"]

    def test_json_suite_repos(self, sample_index: dict) -> None:
        summary = compute_summary(sample_index)
        output = format_json(summary)
        parsed = json.loads(output)
        suite_a_repos = parsed["suites"]["suite_a"]["repos"]
        assert len(suite_a_repos) == 2
        indexed_names = [r["name"] for r in suite_a_repos if r["indexed"]]
        assert "org/repo1" in indexed_names


class TestLoadIndex:
    """Test file loading."""

    def test_load_valid_file(self, sample_index_file: str) -> None:
        data = load_index(sample_index_file)
        assert "repos" in data
        assert "suites" in data

    def test_load_nonexistent_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_index("/nonexistent/path.json")


class TestCLI:
    """Test the script as a CLI tool."""

    def test_runs_with_real_index(self) -> None:
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0
        assert "Sourcegraph Indexing Status" in result.stdout

    def test_json_output(self) -> None:
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, "--json"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert "total_repos" in parsed

    def test_check_api_stub(self) -> None:
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, "--check-api"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0
        assert "stub" in result.stdout.lower()

    def test_custom_index_path(self, sample_index_file: str) -> None:
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, "--index-path", sample_index_file],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0

    def test_missing_index_path(self) -> None:
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, "--index-path", "/nonexistent/path.json"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()

    def test_help_flag(self) -> None:
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, "--help"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0
        assert "verify" in result.stdout.lower() or "indexing" in result.stdout.lower()


class TestDataclassImmutability:
    """Verify dataclasses are frozen."""

    def test_repo_status_frozen(self) -> None:
        r = RepoStatus(name="a", url="b", indexed=True)
        with pytest.raises(AttributeError):
            r.name = "c"  # type: ignore[misc]

    def test_suite_status_frozen(self) -> None:
        s = SuiteStatus(name="a", repos=(), total=0, indexed=0, pending=0)
        with pytest.raises(AttributeError):
            s.name = "c"  # type: ignore[misc]

    def test_indexing_summary_frozen(self) -> None:
        summary = IndexingSummary(
            total_repos=0, indexed_count=0, pending_count=0, suites=()
        )
        with pytest.raises(AttributeError):
            summary.total_repos = 1  # type: ignore[misc]
