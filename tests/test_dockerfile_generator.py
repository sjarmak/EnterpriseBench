"""Tests for Dockerfile generator.

Ensures:
1. Node.js is installed via official tarball download, not apt packages.
2. Agent user is created and switched to (USER agent) BEFORE git clone commands.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "sandbox"))

from dockerfile_generator import (
    _setup_lines,
    generate_hybrid_dockerfile,
    generate_sg_only_dockerfile,
    generate_standard_dockerfile,
)

# ---------------------------------------------------------------------------
# Minimal task data fixtures
# ---------------------------------------------------------------------------

TASK_DATA_PYTHON = {
    "task": {"id": "test-task-001"},
    "metadata": {"languages": ["python"]},
    "repos": [
        {
            "url": "https://github.com/psf/requests",
            "rev": "v2.31.0",
            "path": "requests",
            "role": "primary",
        }
    ],
}

TASK_DATA_GO = {
    "task": {"id": "test-task-002"},
    "metadata": {"languages": ["go"]},
    "repos": [
        {
            "url": "https://github.com/grpc/grpc-go",
            "rev": "v1.60.0",
            "path": "grpc-go",
            "role": "primary",
        }
    ],
}

TASK_DATA_JS = {
    "task": {"id": "test-task-003"},
    "metadata": {"languages": ["javascript"]},
    "repos": [
        {
            "url": "https://github.com/expressjs/express",
            "rev": "v4.18.2",
            "path": "express",
            "role": "primary",
        }
    ],
}


# ---------------------------------------------------------------------------
# _setup_lines tests
# ---------------------------------------------------------------------------


class TestSetupLinesNodeInstall:
    """Verify _setup_lines installs Node.js via tarball, not apt."""

    def test_non_node_base_installs_node_via_tarball(self) -> None:
        """Non-node base images should install Node.js via tarball from nodejs.org."""
        lines = _setup_lines("python:3.11-bookworm")
        text = "\n".join(lines)
        assert "nodejs.org" in text, "Expected Node.js tarball download from nodejs.org"
        assert "tar" in text, "Expected tarball extraction with tar"

    def test_non_node_base_does_not_use_nodesource(self) -> None:
        """Must NOT use NodeSource apt repository."""
        lines = _setup_lines("python:3.11-bookworm")
        text = "\n".join(lines)
        assert (
            "nodesource" not in text.lower()
        ), "Must not use NodeSource apt repo — use tarball instead"
        assert (
            "apt-get install -y nodejs" not in text
        ), "Must not install Node.js via apt — use tarball instead"

    def test_node_base_skips_node_install(self) -> None:
        """Node.js base images already have Node — should not install again."""
        lines = _setup_lines("node:20-bookworm")
        text = "\n".join(lines)
        assert "nodejs.org" not in text, "Node base image should not re-install Node.js"

    def test_tarball_installs_to_usr_local(self) -> None:
        """Tarball should be extracted to /usr/local for PATH availability."""
        lines = _setup_lines("golang:1.21-bookworm")
        text = "\n".join(lines)
        assert "/usr/local" in text, "Tarball should be extracted to /usr/local"

    def test_tarball_uses_strip_components(self) -> None:
        """tar command should use --strip-components=1 to flatten the archive."""
        lines = _setup_lines("ubuntu:22.04")
        text = "\n".join(lines)
        assert (
            "--strip-components" in text
        ), "tar should use --strip-components to flatten the node-v* directory"


# ---------------------------------------------------------------------------
# Full Dockerfile generation tests
# ---------------------------------------------------------------------------


class TestGeneratedDockerfilesNodeInstall:
    """Verify generated Dockerfiles use tarball pattern end-to-end."""

    def test_standard_dockerfile_python_uses_tarball(self) -> None:
        content = generate_standard_dockerfile(TASK_DATA_PYTHON, source="upstream")
        assert "nodejs.org" in content
        assert "nodesource" not in content.lower()

    def test_standard_dockerfile_go_uses_tarball(self) -> None:
        content = generate_standard_dockerfile(TASK_DATA_GO, source="upstream")
        assert "nodejs.org" in content
        assert "nodesource" not in content.lower()

    def test_standard_dockerfile_js_skips_node_install(self) -> None:
        """JS tasks use node: base image — no extra Node.js install needed."""
        content = generate_standard_dockerfile(TASK_DATA_JS, source="upstream")
        assert "nodejs.org" not in content

    def test_sg_only_dockerfile_uses_tarball(self) -> None:
        content = generate_sg_only_dockerfile(TASK_DATA_PYTHON)
        assert "nodejs.org" in content
        assert "nodesource" not in content.lower()


# ---------------------------------------------------------------------------
# Fixtures for user-before-clone tests
# ---------------------------------------------------------------------------

TASK_DATA_MULTI_REPO = {
    "task": {"id": "test-multi-repo"},
    "repos": [
        {
            "url": "https://github.com/psf/requests",
            "rev": "v2.31.0",
            "path": "requests",
            "role": "primary",
        },
        {
            "url": "https://github.com/urllib3/urllib3",
            "rev": "2.1.0",
            "path": "urllib3",
            "role": "dependency",
        },
    ],
    "metadata": {"languages": ["python"]},
}

TASK_DATA_SHA_REV = {
    "task": {"id": "test-sha-rev"},
    "repos": [
        {
            "url": "https://github.com/psf/requests",
            "rev": "a1b2c3d4e5f6",
            "path": "requests",
            "role": "primary",
        },
    ],
    "metadata": {"languages": ["python"]},
}


def _line_index(lines: list[str], pattern: str) -> int | None:
    """Return index of the first line matching a regex pattern, or None."""
    compiled = re.compile(pattern)
    for i, line in enumerate(lines):
        if compiled.search(line):
            return i
    return None


def _all_line_indices(lines: list[str], pattern: str) -> list[int]:
    """Return indices of ALL lines matching a regex pattern."""
    compiled = re.compile(pattern)
    return [i for i, line in enumerate(lines) if compiled.search(line)]


# ---------------------------------------------------------------------------
# User-before-clone tests
# ---------------------------------------------------------------------------


class TestUserBeforeClone:
    """Verify USER agent directive appears before any git clone command."""

    def test_standard_user_before_clone(self) -> None:
        content = generate_standard_dockerfile(TASK_DATA_MULTI_REPO)
        lines = content.splitlines()

        user_idx = _line_index(lines, r"^USER\s+agent")
        clone_indices = _all_line_indices(lines, r"git\s+clone")

        assert (
            user_idx is not None
        ), "USER agent directive not found in standard Dockerfile"
        assert (
            len(clone_indices) >= 2
        ), f"Expected at least 2 clone commands, found {len(clone_indices)}"
        for ci in clone_indices:
            assert (
                user_idx < ci
            ), f"USER agent (line {user_idx}) must appear before git clone (line {ci})"

    def test_hybrid_user_before_clone(self) -> None:
        content = generate_hybrid_dockerfile(TASK_DATA_MULTI_REPO)
        lines = content.splitlines()

        user_idx = _line_index(lines, r"^USER\s+agent")
        clone_indices = _all_line_indices(lines, r"git\s+clone")

        assert (
            user_idx is not None
        ), "USER agent directive not found in hybrid Dockerfile"
        assert (
            len(clone_indices) >= 2
        ), f"Expected at least 2 clone commands, found {len(clone_indices)}"
        for ci in clone_indices:
            assert (
                user_idx < ci
            ), f"USER agent (line {user_idx}) must appear before git clone (line {ci})"

    def test_sg_only_has_user_agent(self) -> None:
        """SG-only has no clones, but should still set USER agent."""
        content = generate_sg_only_dockerfile(TASK_DATA_MULTI_REPO)
        lines = content.splitlines()

        user_idx = _line_index(lines, r"^USER\s+agent")
        assert (
            user_idx is not None
        ), "USER agent directive not found in sg_only Dockerfile"

    def test_sha_rev_user_before_clone(self) -> None:
        """SHA-based revisions also get USER agent before clone."""
        content = generate_standard_dockerfile(TASK_DATA_SHA_REV, source="upstream")
        lines = content.splitlines()

        user_idx = _line_index(lines, r"^USER\s+agent")
        clone_indices = _all_line_indices(lines, r"git\s+clone")

        assert user_idx is not None, "USER agent not found for SHA-based clone"
        assert len(clone_indices) >= 1
        for ci in clone_indices:
            assert user_idx < ci


class TestUseraddBeforeUserAgent:
    """Verify useradd comes before USER agent (must create user before switching)."""

    def test_useradd_before_user_directive(self) -> None:
        content = generate_standard_dockerfile(TASK_DATA_PYTHON)
        lines = content.splitlines()

        useradd_idx = _line_index(lines, r"useradd.*agent")
        user_idx = _line_index(lines, r"^USER\s+agent")

        assert useradd_idx is not None, "useradd agent not found"
        assert user_idx is not None, "USER agent not found"
        assert useradd_idx < user_idx, "useradd must come before USER agent"


class TestRootForInstalls:
    """Ensure apt-get and npm install run as root (before USER agent)."""

    def test_apt_before_user_switch(self) -> None:
        content = generate_standard_dockerfile(TASK_DATA_PYTHON)
        lines = content.splitlines()

        apt_idx = _line_index(lines, r"apt-get\s+install")
        user_idx = _line_index(lines, r"^USER\s+agent")

        assert apt_idx is not None, "apt-get install not found"
        assert user_idx is not None, "USER agent not found"
        assert (
            apt_idx < user_idx
        ), "apt-get install must run before USER agent (as root)"

    def test_npm_install_before_user_switch(self) -> None:
        content = generate_standard_dockerfile(TASK_DATA_PYTHON)
        lines = content.splitlines()

        npm_idx = _line_index(lines, r"npm\s+install.*claude")
        user_idx = _line_index(lines, r"^USER\s+agent")

        assert npm_idx is not None, "npm install claude not found"
        assert user_idx is not None, "USER agent not found"
        assert npm_idx < user_idx, "npm install must run before USER agent (as root)"


class TestWorkspaceOwnership:
    """Verify /workspace is created with proper ownership for agent user."""

    def test_workspace_setup_before_user_switch(self) -> None:
        """Workspace directory must be created/owned before switching to agent."""
        content = generate_standard_dockerfile(TASK_DATA_PYTHON)
        lines = content.splitlines()

        workspace_idx = _line_index(lines, r"mkdir.*workspace|chown.*agent.*workspace")
        user_idx = _line_index(lines, r"^USER\s+agent")

        assert workspace_idx is not None, "Workspace directory setup not found"
        assert user_idx is not None, "USER agent not found"
        assert (
            workspace_idx < user_idx
        ), "Workspace must be created/owned before switching to agent user"


# ---------------------------------------------------------------------------
# sg_only mode marker tests
# ---------------------------------------------------------------------------


class TestSgOnlyModeMarker:
    """Verify sg_only Dockerfiles contain /tmp/.sg_only_mode marker,
    and standard/hybrid Dockerfiles do NOT."""

    def test_sg_only_contains_marker(self) -> None:
        """sg_only Dockerfile must create /tmp/.sg_only_mode marker file."""
        content = generate_sg_only_dockerfile(TASK_DATA_PYTHON)
        assert (
            "/tmp/.sg_only_mode" in content
        ), "sg_only Dockerfile must contain /tmp/.sg_only_mode marker"

    def test_sg_only_marker_uses_touch(self) -> None:
        """Marker should be created via 'RUN touch /tmp/.sg_only_mode'."""
        content = generate_sg_only_dockerfile(TASK_DATA_PYTHON)
        assert (
            "RUN touch /tmp/.sg_only_mode" in content
        ), "Marker must be created with 'RUN touch /tmp/.sg_only_mode'"

    def test_sg_only_marker_before_user_agent(self) -> None:
        """Marker must be created as root (before USER agent line)."""
        content = generate_sg_only_dockerfile(TASK_DATA_PYTHON)
        lines = content.splitlines()

        marker_idx = _line_index(lines, r"touch\s+/tmp/\.sg_only_mode")
        user_idx = _line_index(lines, r"^USER\s+agent")

        assert marker_idx is not None, "sg_only_mode marker not found"
        assert user_idx is not None, "USER agent not found"
        assert (
            marker_idx < user_idx
        ), "Marker must be created before USER agent (as root for consistency)"

    def test_sg_only_marker_has_comment(self) -> None:
        """Marker line should have an explanatory comment."""
        content = generate_sg_only_dockerfile(TASK_DATA_PYTHON)
        lines = content.splitlines()

        marker_idx = _line_index(lines, r"touch\s+/tmp/\.sg_only_mode")
        assert marker_idx is not None, "sg_only_mode marker not found"

        # Check for a comment on the line before the marker
        assert marker_idx > 0, "Marker should not be the first line"
        preceding_line = lines[marker_idx - 1]
        assert preceding_line.startswith(
            "#"
        ), f"Expected a comment before the marker, got: {preceding_line!r}"

    def test_standard_does_not_contain_marker(self) -> None:
        """Standard Dockerfile must NOT contain sg_only_mode marker."""
        content = generate_standard_dockerfile(TASK_DATA_PYTHON)
        assert (
            "/tmp/.sg_only_mode" not in content
        ), "Standard Dockerfile must NOT contain sg_only_mode marker"

    def test_hybrid_does_not_contain_marker(self) -> None:
        """Hybrid Dockerfile must NOT contain sg_only_mode marker."""
        content = generate_hybrid_dockerfile(TASK_DATA_PYTHON)
        assert (
            "/tmp/.sg_only_mode" not in content
        ), "Hybrid Dockerfile must NOT contain sg_only_mode marker"

    def test_sg_only_multi_repo_contains_marker(self) -> None:
        """Marker should be present regardless of repo count."""
        content = generate_sg_only_dockerfile(TASK_DATA_MULTI_REPO)
        assert "RUN touch /tmp/.sg_only_mode" in content
