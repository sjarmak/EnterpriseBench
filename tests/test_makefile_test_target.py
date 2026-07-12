"""The canonical `make test` target must actually execute the suite.

Regression guard for a target that pointed at a directory holding no tests, so
`make test` collected nothing on every invocation. A command that runs zero
tests must never be mistakable for a passing suite.

Every subprocess here is either `--collect-only` or aimed at a path with no
tests in it. None of them executes the real suite, which contains this file.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    shutil.which("make") is None, reason="make is not installed"
)

COLLECTED_RE = re.compile(r"(\d+)/?\d* tests collected|collected (\d+) items")


def _make(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _configured(var: str) -> str:
    """Read a variable straight off the Makefile, no regex-scraping."""
    result = _make("-s", f"print-{var}")
    assert result.returncode == 0, (
        f"`make print-{var}` failed; the Makefile must expose its test "
        f"configuration for introspection.\n{result.stdout}{result.stderr}"
    )
    return result.stdout.strip()


def test_configured_test_paths_collect_at_least_one_test() -> None:
    """The paths `make test` hands pytest must contain tests.

    This is the bug in one assertion: the target used to point at a directory
    with zero test files, so the suite silently never ran.
    """
    paths = _configured("PYTEST_PATHS").split()
    assert paths, "PYTEST_PATHS is empty; `make test` would scan the whole repo"

    result = subprocess.run(
        ["python3", "-m", "pytest", *paths, "-q", "--collect-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PYTHONPATH": "lib"},
    )
    assert result.returncode == 0, (
        f"pytest could not collect from PYTEST_PATHS={paths!r}\n"
        f"{result.stdout[-3000:]}{result.stderr[-2000:]}"
    )

    match = COLLECTED_RE.search(result.stdout)
    assert match, f"could not parse a collection count from:\n{result.stdout[-2000:]}"
    collected = int(match.group(1) or match.group(2))
    assert collected > 0, f"`make test` collects {collected} tests from {paths!r}"


def test_zero_collection_fails_loudly(tmp_path: Path) -> None:
    """Pointed at a directory with no tests, `make test` must fail and say so.

    pytest exits 5 on zero collection, which surfaces as a bare `Error 5`. The
    target has to translate that into a message naming the real problem.
    """
    empty = tmp_path / "no_tests_here"
    empty.mkdir()

    result = _make("test", f"PYTEST_PATHS={empty}")

    assert result.returncode != 0, "a run that collected 0 tests reported success"
    assert "collected 0 tests" in (result.stdout + result.stderr).lower(), (
        "zero-collection must be reported explicitly, not as a bare `Error 5`\n"
        f"{result.stdout[-2000:]}{result.stderr[-2000:]}"
    )


def test_empty_test_paths_is_rejected() -> None:
    """`make test PYTEST_PATHS=` must refuse to run rather than scan the repo.

    With no path arguments pytest walks the rootdir, which pulls in the whole
    repository (this file included) — so the target must reject empty input
    instead of launching a recursive full-tree collection.
    """
    result = _make("test", "PYTEST_PATHS=")

    assert result.returncode != 0, "empty PYTEST_PATHS was accepted"
    assert "pytest_paths is empty" in (result.stdout + result.stderr).lower(), (
        "an empty PYTEST_PATHS must be named as the failure\n"
        f"{result.stdout[-2000:]}{result.stderr[-2000:]}"
    )
