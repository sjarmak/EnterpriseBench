"""Shared pytest fixtures for eb_verify tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Import provenance: prepend THIS repo's lib/ so every test imports the package
# under test, not whatever tree a machine-global editable install
# (site-packages __editable__*.pth) happens to point at. conftest.py is imported
# before any test module in its subtree is collected, so this runs before the
# first `import eb_verify`. Without it, a bare `pytest` (no PYTHONPATH) on a box
# with a stale editable install silently exercises a different worktree's
# eb_verify/eb_metrics — see EnterpriseBench-iqp6x. Guarded by
# tests/integrity/test_eb_verify_import_provenance.py.
_LIB = str(Path(__file__).resolve().parent.parent / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)


def pytest_configure(config):
    config.addinivalue_line("markers", "network: requires network access (git ls-remote)")
    config.addinivalue_line("markers", "docker: requires Docker daemon")
    config.addinivalue_line("markers", "security: exercises a scoring/verifier trust boundary")


def docker_available() -> bool:
    """True if the Docker daemon is reachable.

    Not the same question as "is the binary installed": a `shutil.which` check
    passes on a host whose daemon is down, and the docker-marked tests then
    error instead of skipping.
    """
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def valid_task_path() -> Path:
    return FIXTURES_DIR / "valid_task.toml"


@pytest.fixture
def invalid_task_path() -> Path:
    return FIXTURES_DIR / "invalid_task.toml"


@pytest.fixture
def chain_task_path() -> Path:
    return FIXTURES_DIR / "chain_task.toml"


@pytest.fixture
def example_task_path() -> Path:
    return REPO_ROOT / "benchmarks" / "EXAMPLE_TASK.toml"


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temp dir with a mock repo structure."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # Create a mock repo
    repo = workspace / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('hello')\n")
    return workspace
