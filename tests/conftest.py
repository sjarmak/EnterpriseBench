"""Shared pytest fixtures for eb_verify tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "network: requires network access (git ls-remote)")
    config.addinivalue_line("markers", "docker: requires Docker daemon")


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
