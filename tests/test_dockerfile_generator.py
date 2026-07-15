"""Tests for Dockerfile generator.

Ensures:
1. Node.js is installed via official tarball download, not apt packages.
2. Agent user is created and switched to (USER agent) BEFORE git clone commands.
3. Every generated image carries a python3 that can import eb_verify, so
   python-invoking checkpoints cannot silently score 0.0.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import docker_available

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "sandbox"))

import dockerfile_generator
from dockerfile_generator import (
    _setup_lines,
    base_image_for_languages,
    generate_hybrid_dockerfile,
    generate_sg_only_dockerfile,
    generate_standard_dockerfile,
    image_provides_python,
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

TASK_DATA_JAVA = {
    "task": {"id": "test-task-004"},
    "metadata": {"languages": ["java"]},
    "repos": [
        {
            "url": "https://github.com/FasterXML/jackson-databind",
            "rev": "2.16.0",
            "path": "jackson-databind",
            "role": "primary",
        }
    ],
}

# Bases with no python3 on PATH, so _setup_lines has to install one. Verified
# with `docker run <image> command -v python3`.
PYTHONLESS_BASES = [
    "eclipse-temurin:17-jdk-jammy",
    "ubuntu:22.04",
    "mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim",
]

# Bases that already ship python3 (buildpack-deps lineage), all 3.11+.
PYTHON_BEARING_BASES = [
    "python:3.11-bookworm",
    "golang:1.21-bookworm",
    "rust:1.75-bookworm",
    "node:20-bookworm",
    "gcc:13-bookworm",
]


def _eb_verify_modules() -> list[str]:
    """Every importable module under lib/eb_verify, as dotted names.

    Discovered from the filesystem rather than listed here, so a module added
    later is covered without anyone remembering to add it. That is the whole
    point: the gap this test exists to catch was one module out of 32
    (parsers.manifests, whose bare ``import tomllib`` fails on 3.10) that no
    test ever imported.

    ``eb_verify.__main__`` is excluded — importing it runs the CLI's argparse
    and exits, so it is not an import target.
    """
    lib_dir = REPO_ROOT / "lib"
    modules = []
    for path in sorted((lib_dir / "eb_verify").rglob("*.py")):
        parts = list(path.relative_to(lib_dir).with_suffix("").parts)
        if parts[-1] == "__main__":
            continue
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules.append(".".join(parts))
    return modules


EB_VERIFY_MODULES = _eb_verify_modules()

# These import numpy at module scope, which none of the generated images
# install -- not even the python-bearing 3.11 bases. That is a gap in the
# library's packaging, orthogonal to whether an image has an interpreter, so it
# is marked here rather than chased from this bead.
NUMPY_DEPENDENT_MODULES = {
    "eb_verify.fact_coverage",
    "eb_verify.fact_coverage_calibration",
    "eb_verify.plugins.fact_triples",
}


def _module_param(module: str):
    """Mark the numpy-dependent modules xfail, strictly.

    Strict is the point: whoever puts numpy on the images should be told this
    exemption has expired, by a failing XPASS. A silently-tolerated xfail is the
    same class of bug as the silently-zeroing checkpoint this file exists to
    prevent -- it just fails green instead of red.
    """
    if module in NUMPY_DEPENDENT_MODULES:
        return pytest.param(
            module,
            marks=pytest.mark.xfail(
                reason=f"{module} imports numpy, which no generated image installs",
                strict=True,
            ),
        )
    return module


EB_VERIFY_MODULE_PARAMS = [_module_param(m) for m in EB_VERIFY_MODULES]

# Imports each named module in the container, reporting per-module outcomes as
# JSON instead of dying on the first failure -- one bad module should name
# itself, not mask the other 31.
_IMPORT_PROBE = """
import importlib, json, sys

results = {}
for name in json.loads(sys.argv[1]):
    try:
        importlib.import_module(name)
        results[name] = None
    except BaseException as exc:  # SystemExit is not an Exception
        results[name] = f"{type(exc).__name__}: {exc}"
print(json.dumps(results))
"""


def _run_python(tag: str, code: str, *args: str) -> subprocess.CompletedProcess:
    """Run *code* on *tag*'s python3, with lib/ mounted as eb_verify's import path."""
    return subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{REPO_ROOT / 'lib'}:/eb_lib:ro",
            "-e", "PYTHONPATH=/eb_lib",
            tag, "python3", "-c", code, *args,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )


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


class TestSetupLinesPythonProvision:
    """Every image needs a python3: checks/*.sh shell out to it and eb_verify is
    imported through it. The provisioning is guarded on the base's actual
    behaviour, so it installs one exactly where one is missing."""

    @pytest.mark.parametrize("base", PYTHONLESS_BASES + PYTHON_BEARING_BASES)
    def test_every_base_provisions_python(self, base: str) -> None:
        assert dockerfile_generator._provisions_python(_setup_lines(base))

    @pytest.mark.parametrize("base", PYTHONLESS_BASES + PYTHON_BEARING_BASES)
    def test_install_is_guarded_on_the_interpreter_being_unusable(
        self, base: str
    ) -> None:
        """Unconditionally apt-installing python3 would put a distro interpreter
        on top of images that already ship their own. The guard has to be there,
        not just the install."""
        text = "\n".join(_setup_lines(base))
        assert "if ! python3 -c 'import tomllib'" in text
        assert "apt-get install -y python3 python3-tomli" in text

    def test_guard_tests_tomllib_not_merely_the_interpreter(self) -> None:
        """eb_verify needs a TOML parser at package-import time, and jammy's
        python3 is 3.10, which has no tomllib — task_parser falls back to
        `import tomli`. A `command -v python3` guard would call that image good,
        install no tomli, and still fail every eb_verify check."""
        text = "\n".join(_setup_lines("eclipse-temurin:17-jdk-jammy"))
        assert "import tomllib" in text
        assert "python3-tomli" in text

    def test_python_provisioned_as_root_before_user_agent(self) -> None:
        lines = _setup_lines("ubuntu:22.04")
        install_idx = next(i for i, ln in enumerate(lines) if "python3-tomli" in ln)
        user_idx = next(i for i, ln in enumerate(lines) if ln.startswith("USER agent"))
        assert install_idx < user_idx, "apt install must run as root, before USER agent"

    def test_provisioning_shares_the_apt_lists_with_the_base_install(self) -> None:
        """The install has to land in the same RUN as `apt-get update`; the
        lists are deleted at the end of it, so a later RUN would 404."""
        lines = _setup_lines("ubuntu:22.04")
        run_idx = next(i for i, ln in enumerate(lines) if ln.startswith("RUN apt-get update"))
        install_idx = next(i for i, ln in enumerate(lines) if "python3-tomli" in ln)
        cleanup_idx = next(i for i, ln in enumerate(lines) if "rm -rf /var/lib/apt/lists" in ln)
        assert run_idx < install_idx < cleanup_idx
        # ...and it is one RUN: every line between them is a continuation.
        assert all(lines[i].endswith("\\") for i in range(run_idx, cleanup_idx))


class TestImageProvidesPython:
    """image_provides_python is read off the lines the generator actually
    emits, so it cannot drift away from what gets built."""

    @pytest.mark.parametrize(
        "languages",
        [["java"], ["go"], ["python"], ["rust"], ["javascript"], ["c++"], ["csharp"], []],
    )
    def test_every_language_gets_an_interpreter(self, languages: list[str]) -> None:
        assert image_provides_python(languages) is True

    def test_unknown_language_falls_back_to_ubuntu_with_python(self) -> None:
        assert base_image_for_languages(["cobol"]) == "ubuntu:22.04"
        assert image_provides_python(["cobol"]) is True

    def test_reports_false_when_provisioning_is_removed(self, monkeypatch) -> None:
        """Drift guard: this reproduces the pre-fix generator. If someone drops
        the interpreter install, preflight must fail loudly rather than let
        every python-invoking checkpoint silently score 0.0."""
        monkeypatch.setattr(
            dockerfile_generator,
            "_setup_lines",
            lambda base: ["RUN apt-get install -y git curl", "USER agent"],
        )
        assert image_provides_python(["java"]) is False

    def test_survives_a_reflow_of_the_run_line(self) -> None:
        """The detector reads what the shell would run, not how the RUN line is
        wrapped. Rewrapping the install must not flip the answer — a regex tied
        to the current formatting would false-block every python task the day
        someone reformats the generator."""
        reflowed = [
            "RUN apt-get update && apt-get install -y \\",
            "    git curl ca-certificates jq xz-utils python3 python3-tomli && \\",
            "    rm -rf /var/lib/apt/lists/*",
        ]
        assert dockerfile_generator._provisions_python(reflowed)

        one_line = [
            "RUN apt-get update && apt-get install -y git python3 && rm -rf /var/lib/apt/lists/*"
        ]
        assert dockerfile_generator._provisions_python(one_line)

    def test_does_not_mistake_an_unrelated_apt_install_for_an_interpreter(self) -> None:
        assert not dockerfile_generator._provisions_python(
            ["RUN apt-get update && apt-get install -y git curl jq"]
        )

    def test_gutted_install_is_not_covered_by_the_guard_expression(self) -> None:
        """The interpreter must be read from the install's own arguments.

        A guard that merely *mentions* python3 installs nothing. Scanning from
        the first apt-get install to any later python3 counted this as
        provisioned, which let a python-less image through preflight -- the
        exact silent 0.0 the interpreter gate exists to prevent.
        """
        gutted = [
            "RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates \\",
            "    && if ! python3 -c 'import tomllib' 2>/dev/null; then :; fi \\",
            "    && rm -rf /var/lib/apt/lists/*",
        ]
        assert not dockerfile_generator._provisions_python(gutted)

    def test_the_toml_backport_alone_is_not_an_interpreter(self) -> None:
        """python3-tomli is a library for the interpreter, not the interpreter."""
        assert not dockerfile_generator._provisions_python(
            ["RUN apt-get update && apt-get install -y python3-tomli"]
        )


# ---------------------------------------------------------------------------
# Full Dockerfile generation tests
# ---------------------------------------------------------------------------


class TestGeneratedDockerfilesPython:
    """The interpreter must survive into the actual generated Dockerfiles."""

    def test_standard_java_dockerfile_installs_python(self) -> None:
        content = generate_standard_dockerfile(TASK_DATA_JAVA, source="upstream")
        assert "eclipse-temurin:17-jdk-jammy" in content
        assert "python3" in content and "python3-tomli" in content

    def test_hybrid_java_dockerfile_installs_python(self) -> None:
        content = generate_hybrid_dockerfile(TASK_DATA_JAVA, source="upstream")
        assert "python3" in content and "python3-tomli" in content

    def test_sg_only_dockerfile_installs_python(self) -> None:
        """sg_only is pinned to ubuntu:22.04 regardless of language."""
        content = generate_sg_only_dockerfile(TASK_DATA_JAVA)
        assert "ubuntu:22.04" in content
        assert "python3" in content and "python3-tomli" in content


@pytest.fixture(scope="session")
def build_setup_image(tmp_path_factory):
    """Build the generator's apt RUN block on a base image, yield the tag.

    Memoized and torn down: the two tests below overlap on five bases, and each
    image runs to ~1.5 GB. Building per test case and leaving the tags behind
    costs a full run five redundant builds and ~7.5 GB of resident images.
    """
    tags: dict[str, str] = {}

    def _build(base: str) -> str:
        if base in tags:
            return tags[base]
        # Just the apt RUN block, taken verbatim from the generator. The rest of
        # _setup_lines (npm install of the Claude CLI) is slow, network-heavy,
        # and has nothing to do with the interpreter.
        lines = _setup_lines(base)
        start = next(i for i, ln in enumerate(lines) if ln.startswith("RUN apt-get"))
        end = next(i for i, ln in enumerate(lines) if "rm -rf /var/lib/apt/lists" in ln)
        run_block = "\n".join(lines[start : end + 1])
        context = tmp_path_factory.mktemp("eb-python-e2e")
        (context / "Dockerfile").write_text(f"FROM {base}\n{run_block}\n")

        tag = f"eb-test-python-{base.replace(':', '-').replace('/', '-')}"
        build = subprocess.run(
            ["docker", "build", "-q", "-t", tag, str(context)],
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert build.returncode == 0, f"docker build failed for {base}:\n{build.stderr}"
        tags[base] = tag
        return tag

    yield _build

    for tag in tags.values():
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, timeout=120)


@pytest.fixture(scope="session")
def eb_verify_import_results(build_setup_image):
    """base -> {module: error-or-None} for every eb_verify module.

    One container per base rather than one per (base, module): the import
    attempt is cheap but the container start is not, and the parametrization is
    every base times every module.
    """
    cache: dict[str, dict[str, str | None]] = {}

    def _results(base: str) -> dict[str, str | None]:
        if base in cache:
            return cache[base]
        tag = build_setup_image(base)
        run = _run_python(tag, _IMPORT_PROBE, json.dumps(EB_VERIFY_MODULES))
        # A non-zero exit means python3 itself is missing or broken, not that
        # some module failed to import -- the probe reports those in its JSON.
        assert run.returncode == 0, (
            f"import probe could not run on {base}:\n{run.stdout}\n{run.stderr}"
        )
        cache[base] = json.loads(run.stdout)
        return cache[base]

    return _results


@pytest.mark.docker
@pytest.mark.skipif(not docker_available(), reason="docker daemon not available")
class TestPythonInterpreterE2E:
    """Build the generated provisioning for real. String assertions cannot catch
    a package missing from a base image's apt repo, a guard whose shell syntax
    is wrong, or an interpreter that imports eb_verify only on paper."""

    @pytest.mark.parametrize("module", EB_VERIFY_MODULE_PARAMS)
    @pytest.mark.parametrize("base", PYTHONLESS_BASES + PYTHON_BEARING_BASES)
    def test_eb_verify_module_imports_on_generated_image(
        self, base: str, module: str, eb_verify_import_results
    ) -> None:
        """Every eb_verify module, not just a representative one.

        Asserting a single module is what let the interpreter guarantee read as
        green while it was false: topological_order imports on 3.10, and
        parsers.manifests -- the one module with a bare ``import tomllib`` --
        does not.
        """
        error = eb_verify_import_results(base)[module]
        assert error is None, f"{module} does not import on {base}: {error}"

    @pytest.mark.parametrize("base", PYTHON_BEARING_BASES)
    def test_base_interpreter_is_not_shadowed(self, base: str, build_setup_image) -> None:
        """These images ship their own python. The guard must leave it alone
        rather than lay a distro interpreter over the top of it."""
        tag = build_setup_image(base)
        run = _run_python(tag, "import sys; print(sys.version_info[:2])")
        assert run.returncode == 0, run.stderr
        assert "(3, 11)" in run.stdout or "(3, 12)" in run.stdout, (
            f"{base} should still be on its own 3.11+ interpreter, got {run.stdout!r}"
        )


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
