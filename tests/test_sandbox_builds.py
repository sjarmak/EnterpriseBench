"""
Docker sandbox build smoke tests.

Validates Dockerfile templates and build_all.sh without requiring Docker daemon.
Checks Dockerfile syntax, pinned tag existence, and script validity.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
TEMPLATE_DIR = REPO_ROOT / "scripts" / "sandbox" / "templates"
BUILD_ALL = REPO_ROOT / "scripts" / "sandbox" / "build_all.sh"

DOCKERFILES = sorted(TEMPLATE_DIR.glob("*.Dockerfile"))

# Valid Dockerfile instructions (uppercase)
VALID_INSTRUCTIONS = {
    "FROM",
    "RUN",
    "COPY",
    "ADD",
    "WORKDIR",
    "ENV",
    "EXPOSE",
    "LABEL",
    "CMD",
    "ENTRYPOINT",
    "ARG",
    "VOLUME",
    "USER",
    "HEALTHCHECK",
    "SHELL",
    "STOPSIGNAL",
    "ONBUILD",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_git_clone_urls(dockerfile_text: str) -> list[tuple[str, str]]:
    """Extract (url, tag) pairs from 'git clone --branch <tag> <url>' lines."""
    results = []
    pattern = re.compile(
        r"git\s+clone\s+"
        r"(?:--depth\s+\d+\s+)?"
        r"--branch\s+(\S+)\s+"
        r"(https://github\.com/\S+?)(?:\.git)?\s+"
    )
    for match in pattern.finditer(dockerfile_text):
        tag, url = match.group(1), match.group(2)
        # Normalize: strip trailing .git if present
        url = url.rstrip("/")
        results.append((url, tag))
    return results


def _docker_available() -> bool:
    """Check if Docker daemon is accessible."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _network_available() -> bool:
    """Check basic network connectivity to GitHub."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "https://github.com/grpc/grpc-go.git"],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# 1. Dockerfile template validation
# ---------------------------------------------------------------------------


class TestDockerfileTemplates:
    """Validate Dockerfile syntax and structure for each template."""

    def test_templates_exist(self) -> None:
        assert TEMPLATE_DIR.exists(), f"Template dir missing: {TEMPLATE_DIR}"
        assert len(DOCKERFILES) >= 3, (
            f"Expected at least 3 Dockerfiles, found {len(DOCKERFILES)}: "
            f"{[d.name for d in DOCKERFILES]}"
        )

    @pytest.mark.parametrize(
        "dockerfile",
        DOCKERFILES,
        ids=[d.stem for d in DOCKERFILES],
    )
    def test_dockerfile_syntax(self, dockerfile: Path) -> None:
        lines = dockerfile.read_text().splitlines()
        has_from = False
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Continuation lines (backslash from previous line) are fine
            if i > 1 and lines[i - 2].rstrip().endswith("\\"):
                continue
            instruction = stripped.split()[0].upper()
            # Remove any AS alias from FROM
            if instruction == "FROM":
                has_from = True
            assert instruction in VALID_INSTRUCTIONS or instruction.startswith("--"), (
                f"{dockerfile.name}:{i} — unknown instruction '{instruction}': {stripped}"
            )
        assert has_from, f"{dockerfile.name} missing FROM instruction"

    @pytest.mark.parametrize(
        "dockerfile",
        DOCKERFILES,
        ids=[d.stem for d in DOCKERFILES],
    )
    def test_dockerfile_has_workspace(self, dockerfile: Path) -> None:
        text = dockerfile.read_text()
        assert "/workspace" in text, f"{dockerfile.name} does not reference /workspace"

    @pytest.mark.parametrize(
        "dockerfile",
        DOCKERFILES,
        ids=[d.stem for d in DOCKERFILES],
    )
    def test_dockerfile_has_health_check_copy(self, dockerfile: Path) -> None:
        text = dockerfile.read_text()
        assert "health_check.sh" in text, (
            f"{dockerfile.name} does not COPY health_check.sh"
        )

    @pytest.mark.parametrize(
        "dockerfile",
        DOCKERFILES,
        ids=[d.stem for d in DOCKERFILES],
    )
    def test_dockerfile_has_test_runner_copy(self, dockerfile: Path) -> None:
        text = dockerfile.read_text()
        assert "test_runner.sh" in text, (
            f"{dockerfile.name} does not COPY test_runner.sh"
        )

    @pytest.mark.parametrize(
        "dockerfile",
        DOCKERFILES,
        ids=[d.stem for d in DOCKERFILES],
    )
    def test_git_clones_are_pinned(self, dockerfile: Path) -> None:
        """Every git clone must use --branch with a specific tag."""
        text = dockerfile.read_text()
        clone_lines = [
            line.strip()
            for line in text.splitlines()
            if "git clone" in line and "github.com" in line
        ]
        for line in clone_lines:
            assert "--branch" in line, (
                f"{dockerfile.name}: unpinned git clone: {line}"
            )
            assert "--depth" in line, (
                f"{dockerfile.name}: git clone without --depth (should be shallow): {line}"
            )


# ---------------------------------------------------------------------------
# 2. Verify pinned tags exist on remote (network-dependent)
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestPinnedTagsExist:
    """Verify that git tags referenced in Dockerfiles exist on GitHub."""

    @pytest.mark.parametrize(
        "dockerfile",
        DOCKERFILES,
        ids=[d.stem for d in DOCKERFILES],
    )
    def test_tags_exist_on_remote(self, dockerfile: Path) -> None:
        if not _network_available():
            pytest.skip("Network unavailable — skipping remote tag verification")

        text = dockerfile.read_text()
        clone_refs = _parse_git_clone_urls(text)
        assert len(clone_refs) > 0, f"{dockerfile.name}: no git clone URLs found"

        for url, tag in clone_refs:
            result = subprocess.run(
                ["git", "ls-remote", "--tags", "--refs", f"{url}.git", tag],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, (
                f"git ls-remote failed for {url} tag {tag}"
            )
            assert tag in result.stdout, (
                f"Tag '{tag}' not found in {url}. "
                f"ls-remote output: {result.stdout[:200]}"
            )


# ---------------------------------------------------------------------------
# 3. build_all.sh validation
# ---------------------------------------------------------------------------


class TestBuildAllScript:
    """Validate build_all.sh is syntactically correct."""

    def test_build_all_exists(self) -> None:
        assert BUILD_ALL.exists(), f"Missing {BUILD_ALL}"

    def test_build_all_syntax_valid(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(BUILD_ALL)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"build_all.sh has syntax errors:\n{result.stderr}"
        )

    def test_build_all_references_all_templates(self) -> None:
        text = BUILD_ALL.read_text()
        for dockerfile in DOCKERFILES:
            stem = dockerfile.stem  # e.g., "go_multi_repo"
            assert stem in text, (
                f"build_all.sh does not reference template '{stem}'"
            )


# ---------------------------------------------------------------------------
# 4. Optional Docker build test (only if daemon is available)
# ---------------------------------------------------------------------------


@pytest.mark.docker
class TestDockerBuild:
    """Optionally run a quick Docker build if the daemon is available."""

    @pytest.mark.parametrize(
        "dockerfile",
        DOCKERFILES,
        ids=[d.stem for d in DOCKERFILES],
    )
    def test_docker_build(self, dockerfile: Path, tmp_path: Path) -> None:
        if not _docker_available():
            pytest.skip("Docker daemon not available — skipping build test")

        # Copy Dockerfile and helper scripts into build context
        build_ctx = tmp_path / "build"
        build_ctx.mkdir()

        shutil.copy2(dockerfile, build_ctx / "Dockerfile")

        health_check = REPO_ROOT / "scripts" / "sandbox" / "health_check.sh"
        test_runner = REPO_ROOT / "scripts" / "sandbox" / "test_runner.sh"
        if health_check.exists():
            shutil.copy2(health_check, build_ctx / "health_check.sh")
        if test_runner.exists():
            shutil.copy2(test_runner, build_ctx / "test_runner.sh")

        tag = f"eb-test-{dockerfile.stem}"
        result = subprocess.run(
            ["docker", "build", "-t", tag, str(build_ctx)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        # Clean up image regardless of outcome
        subprocess.run(
            ["docker", "rmi", tag],
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Docker build failed for {dockerfile.name}:\n{result.stderr[-500:]}"
        )
