"""Tests for scripts/validate_tasks_preflight.py.

Tests the validation logic with synthetic task fixtures to ensure
each check correctly identifies issues.
"""

from __future__ import annotations

import json
import os
import stat
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Import from the script under test
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import validate_tasks_preflight as vtp

# The python-interpreter check is derived from the Dockerfile generator, so the
# drift tests patch the generator itself rather than a copy of its conclusions.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "sandbox"))
import dockerfile_generator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_benchmarks(tmp_path: Path) -> Path:
    """Create a minimal benchmarks directory structure."""
    return tmp_path / "benchmarks"


@pytest.fixture()
def minimal_task_toml() -> str:
    """A valid task.toml content as a TOML string."""
    return textwrap.dedent("""\
        difficulty_stratum = "dual_repo"
        mcp_suite = "eb_v1"
        repo_set_id = "test-ecosystem"
        org_scale = true
        verification_modes = ["deterministic"]

        [task]
        id = "test-task-001"
        suite = "customer_escalation"
        difficulty = "hard"
        session_type = "single"
        description = "Test task"
        prompt = "Do the thing."

        [[repos]]
        url = "https://github.com/test/repo"
        rev = "v1.0.0"
        path = "repo"

        [[checkpoints]]
        name = "check_one"
        weight = 0.60
        verifier = "checks/check_one.sh"
        description = "First check"

        [[checkpoints]]
        name = "check_two"
        weight = 0.40
        verifier = "checks/check_two.sh"
        description = "Second check"

        [artifacts]
        required = ["answer"]

        [tool_access]
        expected_mcp_benefit = "high"
        mcp_benefit_rationale = "Test rationale"
        sourcegraph_mirror_config = "configs/sg_mirrors/test-task-001.json"

        [ground_truth]
        tiers = ["deterministic"]

        [[ground_truth.required_files]]
        path = "src/main.go"
        repo = "repo"
        confidence = 0.95
        source = "deterministic"
    """)


def _create_task_dir(
    benchmarks: Path,
    suite: str,
    task_name: str,
    toml_content: str,
    *,
    create_instruction: bool = True,
    create_ground_truth: bool = True,
    create_checks: bool = True,
    create_environment: bool = True,
    ground_truth_data: dict[str, Any] | None = None,
) -> Path:
    """Helper to create a complete task directory."""
    task_dir = benchmarks / suite / task_name
    task_dir.mkdir(parents=True, exist_ok=True)

    # task.toml
    (task_dir / "task.toml").write_text(toml_content)

    # instruction.md
    if create_instruction:
        (task_dir / "instruction.md").write_text("# Test instruction\n")

    # ground_truth.json
    if create_ground_truth:
        gt_data = (
            ground_truth_data
            if ground_truth_data is not None
            else {
                "ground_truth": {
                    "required_files": [{"path": "src/main.go", "repo": "repo"}]
                }
            }
        )
        (task_dir / "ground_truth.json").write_text(json.dumps(gt_data))

    # checks directory with scripts
    if create_checks:
        checks_dir = task_dir / "checks"
        checks_dir.mkdir(exist_ok=True)
        for script_name in ["check_one.sh", "check_two.sh"]:
            script = checks_dir / script_name
            script.write_text("#!/bin/bash\nexit 0\n")
            script.chmod(script.stat().st_mode | stat.S_IEXEC)

    # environment with Dockerfiles
    if create_environment:
        env_dir = task_dir / "environment"
        env_dir.mkdir(exist_ok=True)
        (env_dir / "Dockerfile").write_text("FROM python:3.11\n")
        (env_dir / "Dockerfile.hybrid").write_text("FROM python:3.11\n")
        (env_dir / "Dockerfile.sg_only").write_text("FROM python:3.11\n")

    return task_dir


def _validate(
    task_dir: Path,
    sg_index: dict[str, bool] | None = None,
    mirror_task_ids: set[str] | None = None,
) -> vtp.TaskValidation:
    """Convenience wrapper that infers benchmarks_dir from task_dir structure."""
    # task_dir is benchmarks/suite/task_name, so grandparent is benchmarks
    benchmarks_dir = task_dir.parent.parent
    return vtp.validate_task(
        task_dir,
        None,
        None,
        sg_index or {},
        mirror_task_ids or set(),
        benchmarks_dir=benchmarks_dir,
    )


# ---------------------------------------------------------------------------
# Tests for collect_task_dirs
# ---------------------------------------------------------------------------


class TestCollectTaskDirs:
    def test_excludes_archived(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        _create_task_dir(tmp_benchmarks, "_archived", "old-task", minimal_task_toml)
        _create_task_dir(
            tmp_benchmarks, "customer_escalation", "good-task", minimal_task_toml
        )

        with patch.object(vtp, "BENCHMARKS_DIR", tmp_benchmarks):
            dirs = vtp.collect_task_dirs()
        assert len(dirs) == 1
        assert dirs[0].name == "good-task"

    def test_excludes_mined(self, tmp_benchmarks: Path, minimal_task_toml: str) -> None:
        _create_task_dir(tmp_benchmarks, "mined", "candidate", minimal_task_toml)
        _create_task_dir(
            tmp_benchmarks, "customer_escalation", "real-task", minimal_task_toml
        )

        with patch.object(vtp, "BENCHMARKS_DIR", tmp_benchmarks):
            dirs = vtp.collect_task_dirs()
        assert len(dirs) == 1

    def test_suite_filter(self, tmp_benchmarks: Path, minimal_task_toml: str) -> None:
        _create_task_dir(
            tmp_benchmarks, "customer_escalation", "task-a", minimal_task_toml
        )
        _create_task_dir(tmp_benchmarks, "technical_debt", "task-b", minimal_task_toml)

        with patch.object(vtp, "BENCHMARKS_DIR", tmp_benchmarks):
            dirs = vtp.collect_task_dirs(suite_filter="technical_debt")
        assert len(dirs) == 1
        assert dirs[0].name == "task-b"

    def test_task_id_filter(self, tmp_benchmarks: Path, minimal_task_toml: str) -> None:
        _create_task_dir(
            tmp_benchmarks, "customer_escalation", "task-a", minimal_task_toml
        )
        _create_task_dir(
            tmp_benchmarks, "customer_escalation", "task-b", minimal_task_toml
        )

        with patch.object(vtp, "BENCHMARKS_DIR", tmp_benchmarks):
            dirs = vtp.collect_task_dirs(task_id_filter="task-a")
        assert len(dirs) == 1
        assert dirs[0].name == "task-a"


# ---------------------------------------------------------------------------
# Tests for validate_task
# ---------------------------------------------------------------------------


class TestValidateTask:
    def test_fully_valid_task(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "good-task", minimal_task_toml
        )
        result = _validate(task_dir)
        # Should be ready (no errors, only warnings for schema/mirror)
        assert result.ready
        assert result.has_instruction
        assert result.has_ground_truth
        assert result.weights_valid
        assert result.scripts_valid
        assert result.has_environment_dir
        assert result.has_dockerfile
        assert result.has_dockerfile_hybrid

    def test_missing_instruction(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "no-instruction",
            minimal_task_toml,
            create_instruction=False,
        )
        result = _validate(task_dir)
        assert not result.ready
        assert not result.has_instruction
        assert any(i.check == "instruction" for i in result.issues)

    def test_missing_ground_truth(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "no-gt",
            minimal_task_toml,
            create_ground_truth=False,
        )
        result = _validate(task_dir)
        assert not result.ready
        assert not result.has_ground_truth

    def test_empty_ground_truth(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "empty-gt",
            minimal_task_toml,
            ground_truth_data={},
        )
        result = _validate(task_dir)
        assert not result.ready
        assert any(
            i.check == "ground_truth" and "empty" in i.message for i in result.issues
        )

    def test_missing_check_scripts(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "no-checks",
            minimal_task_toml,
            create_checks=False,
        )
        result = _validate(task_dir)
        assert not result.ready
        assert not result.scripts_valid

    def test_no_environment_dir(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "no-env",
            minimal_task_toml,
            create_environment=False,
        )
        result = _validate(task_dir)
        # Environment is a warning, not an error
        assert result.ready
        assert not result.has_environment_dir
        assert any(i.check == "environment" for i in result.issues)

    def test_bad_checkpoint_weights(self, tmp_benchmarks: Path) -> None:
        bad_toml = textwrap.dedent("""\
            difficulty_stratum = "dual_repo"
            mcp_suite = "eb_v1"
            repo_set_id = "test-ecosystem"
            org_scale = true
            verification_modes = ["deterministic"]

            [task]
            id = "test-weights-001"
            suite = "customer_escalation"
            difficulty = "hard"
            session_type = "single"
            prompt = "test"

            [[repos]]
            url = "https://github.com/test/repo"
            rev = "v1.0.0"
            path = "repo"

            [[checkpoints]]
            name = "check_one"
            weight = 0.30
            verifier = "checks/check_one.sh"

            [[checkpoints]]
            name = "check_two"
            weight = 0.30
            verifier = "checks/check_two.sh"

            [artifacts]
            required = ["answer"]

            [tool_access]
            expected_mcp_benefit = "high"
            mcp_benefit_rationale = "test"

            [ground_truth]
            tiers = ["deterministic"]

            [[ground_truth.required_files]]
            path = "src/main.go"
            repo = "repo"
        """)
        task_dir = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "bad-weights", bad_toml
        )
        result = _validate(task_dir)
        assert not result.ready
        assert not result.weights_valid
        assert any(i.check == "weights" for i in result.issues)

    def test_mirror_config_by_task_id(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "mirror-test", minimal_task_toml
        )
        # Task ID in toml is "test-task-001"
        result = _validate(task_dir, mirror_task_ids={"test-task-001"})
        assert result.has_mirror_config

    def test_missing_top_level_fields(self, tmp_benchmarks: Path) -> None:
        # toml without mcp_suite, verification_modes
        bare_toml = textwrap.dedent("""\
            difficulty_stratum = "dual_repo"

            [task]
            id = "bare-task-001"
            suite = "customer_escalation"
            difficulty = "hard"
            session_type = "single"
            prompt = "test"

            [[repos]]
            url = "https://github.com/test/repo"
            rev = "v1.0.0"
            path = "repo"

            [[checkpoints]]
            name = "check_one"
            weight = 1.0
            verifier = "checks/check_one.sh"

            [artifacts]
            required = ["answer"]

            [tool_access]
            expected_mcp_benefit = "low"
            mcp_benefit_rationale = "test"

            [ground_truth]
            tiers = ["deterministic"]

            [[ground_truth.required_files]]
            path = "src/main.go"
            repo = "repo"
        """)
        task_dir = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "bare-task", bare_toml
        )
        # Only one check script needed
        (task_dir / "checks" / "check_one.sh").write_text("#!/bin/bash\nexit 0\n")
        (task_dir / "checks" / "check_one.sh").chmod(0o755)

        result = _validate(task_dir)
        assert not result.top_level_fields_present
        assert any(i.check == "top_level_fields" for i in result.issues)


# ---------------------------------------------------------------------------
# Tests for generate_registry
# ---------------------------------------------------------------------------


class TestGenerateRegistry:
    def test_registry_structure(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "reg-task", minimal_task_toml
        )
        result = _validate(task_dir)
        registry = vtp.generate_registry([result])

        assert "summary" in registry
        assert "tasks" in registry
        assert "blocking_issues" in registry
        assert registry["summary"]["total_tasks"] == 1
        assert "customer_escalation" in registry["tasks"]
        assert len(registry["tasks"]["customer_escalation"]) == 1

    def test_registry_counts(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        # One valid, one broken
        good = _create_task_dir(
            tmp_benchmarks, "customer_escalation", "good", minimal_task_toml
        )
        bad = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "bad",
            minimal_task_toml,
            create_instruction=False,
        )
        r1 = _validate(good)
        r2 = _validate(bad)
        registry = vtp.generate_registry([r1, r2])

        assert registry["summary"]["total_tasks"] == 2
        assert registry["summary"]["ready"] == 1
        assert registry["summary"]["blocked"] == 1
        assert len(registry["blocking_issues"]) > 0


# ---------------------------------------------------------------------------
# Tests for the two mirror-indexed candidate-matching code paths
# (EnterpriseBench-k9po: sg_name convention fix)
# ---------------------------------------------------------------------------


def _toml_with_sourcegraph_mirrors(mirror_id: str) -> str:
    return textwrap.dedent(f"""\
        difficulty_stratum = "dual_repo"
        mcp_suite = "eb_v1"
        repo_set_id = "test-ecosystem"
        org_scale = true
        verification_modes = ["deterministic"]

        [task]
        id = "test-task-mirrors"
        suite = "customer_escalation"
        difficulty = "hard"
        session_type = "single"
        description = "Test task"
        prompt = "Do the thing."

        [[repos]]
        url = "https://github.com/test/repo"
        rev = "v1.0.0"
        path = "repo"

        [[checkpoints]]
        name = "check_one"
        weight = 1.0
        verifier = "checks/check_one.sh"
        description = "Only check"

        [artifacts]
        required = ["answer"]

        [tool_access]
        expected_mcp_benefit = "high"
        mcp_benefit_rationale = "Test rationale"

        [[tool_access.sourcegraph_mirrors]]
        repo = "github.com/org/repo"
        mirror_id = "{mirror_id}"

        [ground_truth]
        tiers = ["deterministic"]

        [[ground_truth.required_files]]
        path = "src/main.go"
        repo = "repo"
        confidence = 0.95
        source = "deterministic"
    """)


class TestSourcegraphMirrorsCandidateMatching:
    """tool_access.sourcegraph_mirrors entries have no independent rev, so
    the org is stripped directly off mirror_id rather than routed through
    derive_mirror_name() (see validate_task, "10. Mirrors indexed")."""

    def test_pre_transformed_mirror_id_matches_indexed_entry(
        self, tmp_benchmarks: Path
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "test-task-mirrors",
            _toml_with_sourcegraph_mirrors("org/repo--v1.0.0"),
        )
        result = _validate(task_dir, sg_index={"sg-evals/repo--v1.0.0": True})
        assert result.mirrors_indexed is True
        assert not any(i.check == "mirrors_indexed" for i in result.issues)

    def test_pre_transformed_mirror_id_not_yet_indexed(
        self, tmp_benchmarks: Path
    ) -> None:
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "test-task-mirrors",
            _toml_with_sourcegraph_mirrors("org/repo--v1.0.0"),
        )
        result = _validate(task_dir, sg_index={"sg-evals/repo--v1.0.0": False})
        assert result.mirrors_indexed is False
        assert any(
            i.check == "mirrors_indexed" and "Not all mirrors indexed" in i.message
            for i in result.issues
        )

    def test_malformed_mirror_id_flagged_distinctly_from_not_indexed(
        self, tmp_benchmarks: Path
    ) -> None:
        """A mirror_id whose rev segment was never pre-transformed (slash
        left in place, as derive_mirror_name would have replaced with '_')
        must be flagged as malformed, not silently treated as an ordinary
        not-yet-indexed mirror."""
        task_dir = _create_task_dir(
            tmp_benchmarks,
            "customer_escalation",
            "test-task-mirrors",
            _toml_with_sourcegraph_mirrors("org/repo--rel/2.14.1"),
        )
        result = _validate(task_dir, sg_index={"sg-evals/repo--rel_2.14.1": True})
        assert result.mirrors_indexed is False
        assert any(
            i.check == "mirrors_indexed" and "not a legal sg-evals mirror" in i.message
            for i in result.issues
        )


# ---------------------------------------------------------------------------
# Tests for the shared mirror-indexed-check helpers
# (EnterpriseBench-pias: unify branch-1/branch-2 semantics behind two
# intention-revealing functions, without changing either branch's
# observable behavior)
# ---------------------------------------------------------------------------


class TestMirrorVerifiedIndexed:
    def test_absent(self) -> None:
        assert vtp._mirror_verified_indexed("x", {}) is False

    def test_present_indexed(self) -> None:
        assert vtp._mirror_verified_indexed("x", {"x": True}) is True

    def test_present_not_indexed(self) -> None:
        assert vtp._mirror_verified_indexed("x", {"x": False}) is False


class TestMirrorPresentInIndex:
    def test_absent(self) -> None:
        assert vtp._mirror_present_in_index("x", {}) is False

    def test_present_indexed(self) -> None:
        assert vtp._mirror_present_in_index("x", {"x": True}) is True

    def test_present_not_indexed(self) -> None:
        # The critical differentiator versus _mirror_verified_indexed:
        # membership alone is enough here, the stored _indexed value is
        # irrelevant. This is what keeps branch 2 (configs/sg_mirrors/*.json)
        # from silently flipping 77 real tasks from indexed to not-indexed.
        assert vtp._mirror_present_in_index("x", {"x": False}) is True


# ---------------------------------------------------------------------------
# Tests for load_sg_index
# ---------------------------------------------------------------------------


class TestLoadSgIndex:
    def test_loads_index(self, tmp_path: Path) -> None:
        """load_sg_index() is format-agnostic — it just builds {sg_name:
        indexed} from whatever string is in the field — but use the real
        org-dropped convention here (not the pre-k9po org-embedded shape)
        so this fixture doesn't read as a stale example of the fixed bug."""
        index_path = tmp_path / "sg_indexing_list.json"
        index_path.write_text(
            json.dumps(
                {
                    "repos": [
                        {"sg_name": "sg-evals/repo--v1", "_indexed": True},
                        {"sg_name": "sg-evals/other-repo--v2", "_indexed": False},
                    ]
                }
            )
        )
        with patch.object(vtp, "SG_INDEXING_PATH", index_path):
            result = vtp.load_sg_index()
        assert result["sg-evals/repo--v1"] is True
        assert result["sg-evals/other-repo--v2"] is False

    def test_missing_file(self, tmp_path: Path) -> None:
        with patch.object(vtp, "SG_INDEXING_PATH", tmp_path / "nonexistent.json"):
            result = vtp.load_sg_index()
        assert result == {}


# ---------------------------------------------------------------------------
# Tests for TaskValidation properties
# ---------------------------------------------------------------------------


class TestScriptInvokesPython:
    """The detector is deliberately over-inclusive. A false positive costs
    nothing (every image ships python3), while a miss lets a checkpoint score
    0.0 forever with no signal."""

    @pytest.mark.parametrize(
        "script",
        [
            'if python3 -c "import json" 2>/dev/null; then FOUND=1; fi',
            'python3 - "$LIB_DIR" <<\'PYEOF\'\nprint(1)\nPYEOF',
            "python -c 'print(1)'",
            "from eb_verify.plugins.topological_order import validate_refactor_plan",
            'python3 -m eb_verify.cli score',
        ],
    )
    def test_detects_python_usage(self, script: str) -> None:
        assert vtp._script_invokes_python(f"#!/usr/bin/env bash\n{script}\n")

    @pytest.mark.parametrize(
        "script",
        [
            "#!/usr/bin/env bash\ngrep -q foo bar.txt\n",
            "#!/usr/bin/env bash\n# rewrite this in python3 someday\nexit 0\n",
            "#!/usr/bin/env bash\n#   uses eb_verify in a future life\nexit 0\n",
        ],
    )
    def test_ignores_comments_and_plain_shell(self, script: str) -> None:
        assert not vtp._script_invokes_python(script)


class TestPythonInterpreterCheck:
    """A check script that shells out to python on an image with no python
    scores 0.0 no matter how good the agent's answer is. Preflight must catch
    that before the run, not leave it to the scorer."""

    def _java_task(
        self, tmp_benchmarks: Path, minimal_task_toml: str, check_body: str
    ) -> Path:
        toml = minimal_task_toml + '\n[metadata]\nlanguages = ["java"]\n'
        task_dir = _create_task_dir(
            tmp_benchmarks, "technical_debt", "java-task", toml
        )
        (task_dir / "checks" / "check_one.sh").write_text(check_body)
        return task_dir

    def test_python_using_check_passes_when_image_provides_python(
        self, tmp_benchmarks: Path, minimal_task_toml: str
    ) -> None:
        task_dir = self._java_task(
            tmp_benchmarks,
            minimal_task_toml,
            '#!/usr/bin/env bash\npython3 -c "import json"\n',
        )
        result = _validate(task_dir)
        assert result.python_interpreter_ok
        assert not [i for i in result.issues if i.check == "python_interpreter"]

    def test_errors_when_image_has_no_python(
        self, tmp_benchmarks: Path, minimal_task_toml: str, monkeypatch
    ) -> None:
        """Reproduces the pre-fix generator: temurin with no interpreter."""
        monkeypatch.setattr(
            dockerfile_generator,
            "_setup_lines",
            lambda base: ["RUN apt-get install -y git curl", "USER agent"],
        )
        task_dir = self._java_task(
            tmp_benchmarks,
            minimal_task_toml,
            '#!/usr/bin/env bash\npython3 -c "import json"\n',
        )
        result = _validate(task_dir)

        assert not result.python_interpreter_ok
        errors = [
            i
            for i in result.issues
            if i.check == "python_interpreter" and i.severity == "error"
        ]
        assert len(errors) == 1
        assert "eclipse-temurin:17-jdk-jammy" in errors[0].message
        assert "checks/check_one.sh" in errors[0].message
        assert not result.ready, "a task that cannot score its checkpoints is not ready"

    def test_eb_verify_import_counts_as_needing_python(
        self, tmp_benchmarks: Path, minimal_task_toml: str, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            dockerfile_generator,
            "_setup_lines",
            lambda base: ["RUN apt-get install -y git curl", "USER agent"],
        )
        task_dir = self._java_task(
            tmp_benchmarks,
            minimal_task_toml,
            "#!/usr/bin/env bash\ngrep -q x y\n"
            "from eb_verify.plugins.topological_order import validate_refactor_plan\n",
        )
        result = _validate(task_dir)
        assert not result.python_interpreter_ok

    def test_shell_only_task_is_unaffected_by_a_pythonless_image(
        self, tmp_benchmarks: Path, minimal_task_toml: str, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            dockerfile_generator,
            "_setup_lines",
            lambda base: ["RUN apt-get install -y git curl", "USER agent"],
        )
        task_dir = self._java_task(
            tmp_benchmarks,
            minimal_task_toml,
            "#!/usr/bin/env bash\ngrep -q foo /workspace/ANSWER.md\n",
        )
        result = _validate(task_dir)
        assert result.python_interpreter_ok
        assert not [i for i in result.issues if i.check == "python_interpreter"]

    def test_a_python_verifier_needs_an_interpreter_to_start(
        self, tmp_benchmarks: Path, minimal_task_toml: str, monkeypatch
    ) -> None:
        """schemas/task.schema.json puts no extension constraint on `verifier`.
        A .py verifier cannot even start without an interpreter, and globbing
        only *.sh would wave it through."""
        monkeypatch.setattr(
            dockerfile_generator,
            "_setup_lines",
            lambda base: ["RUN apt-get install -y git curl", "USER agent"],
        )
        toml = minimal_task_toml.replace(
            'verifier = "checks/check_one.sh"', 'verifier = "checks/check_one.py"'
        ) + '\n[metadata]\nlanguages = ["java"]\n'
        task_dir = _create_task_dir(
            tmp_benchmarks, "technical_debt", "py-verifier-task", toml
        )
        (task_dir / "checks" / "check_one.sh").unlink()
        (task_dir / "checks" / "check_two.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
        (task_dir / "checks" / "check_one.py").write_text("print('hello')\n")

        result = _validate(task_dir)
        assert not result.python_interpreter_ok
        errors = [i for i in result.issues if i.check == "python_interpreter"]
        assert len(errors) == 1
        assert "checks/check_one.py" in errors[0].message


class TestTaskValidationProperties:
    def test_ready_with_no_issues(self) -> None:
        v = vtp.TaskValidation(task_id="t", suite="s", task_dir="/tmp")
        assert v.ready

    def test_not_ready_with_error(self) -> None:
        v = vtp.TaskValidation(
            task_id="t",
            suite="s",
            task_dir="/tmp",
            issues=[vtp.TaskIssue("error", "test", "fail")],
        )
        assert not v.ready

    def test_ready_with_warning_only(self) -> None:
        v = vtp.TaskValidation(
            task_id="t",
            suite="s",
            task_dir="/tmp",
            issues=[vtp.TaskIssue("warning", "test", "warn")],
        )
        assert v.ready

    def test_error_and_warning_counts(self) -> None:
        v = vtp.TaskValidation(
            task_id="t",
            suite="s",
            task_dir="/tmp",
            issues=[
                vtp.TaskIssue("error", "a", "x"),
                vtp.TaskIssue("error", "b", "y"),
                vtp.TaskIssue("warning", "c", "z"),
            ],
        )
        assert v.error_count == 2
        assert v.warning_count == 1


# ---------------------------------------------------------------------------
# Integration: run against real benchmarks
# ---------------------------------------------------------------------------


class TestRealBenchmarks:
    """Smoke test against the actual EnterpriseBench tasks."""

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "benchmarks").exists(),
        reason="Not in EnterpriseBench repo",
    )
    def test_all_tasks_parseable(self) -> None:
        """Every task.toml should at least parse without error."""
        task_dirs = vtp.collect_task_dirs()
        assert len(task_dirs) > 0
        sg_index = vtp.load_sg_index()
        mirror_ids = vtp.load_mirror_task_ids()
        for td in task_dirs:
            result = vtp.validate_task(td, None, None, sg_index, mirror_ids)
            # Should not have toml_parse errors
            parse_errors = [i for i in result.issues if i.check == "toml_parse"]
            assert parse_errors == [], f"{td.name}: {parse_errors}"

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "benchmarks").exists(),
        reason="Not in EnterpriseBench repo",
    )
    def test_mirrors_indexed_branches_unchanged_by_refactor(self) -> None:
        """Regression lock for EnterpriseBench-pias: splitting the shared
        indexed-check into _mirror_verified_indexed/_mirror_present_in_index
        must not change either branch's real-corpus result. Branch 1
        (tool_access.sourcegraph_mirrors[]) currently has exactly two tasks,
        both not-indexed -- asserted by name. Branch 2 (configs/sg_mirrors/
        *.json) has 77, all indexed; asserted by count rather than by name
        (unlike branch 1) since hardcoding 77 task names would be pure
        noise, but still built as a set for the same per-task tracking
        shape so a future change flipping one task while adding another
        doesn't cancel out silently within this test run."""
        import tomllib

        schema = vtp.load_schema()
        sg_index = vtp.load_sg_index()
        mirror_ids = vtp.load_mirror_task_ids()

        branch1_not_indexed = set()
        branch2_indexed = set()
        for td in vtp.collect_task_dirs():
            # td.name alone isn't a unique key -- task dir names repeat
            # across suites (e.g. calibration-001 exists in 3 suites), so
            # dedup on the suite-qualified relative path instead.
            key = str(td.relative_to(vtp.BENCHMARKS_DIR))
            data = tomllib.loads((td / "task.toml").read_text())
            has_branch1 = bool(
                data.get("tool_access", {}).get("sourcegraph_mirrors")
            )
            result = vtp.validate_task(td, schema, None, sg_index, mirror_ids)
            if has_branch1:
                if not result.mirrors_indexed:
                    branch1_not_indexed.add(key)
            elif result.has_mirror_config:
                if result.mirrors_indexed:
                    branch2_indexed.add(key)

        assert branch1_not_indexed == {
            "dependency_management/ccx-dep-trace-106",
            "incident_response/ccx-incident-032",
        }
        assert len(branch2_indexed) == 77

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parent.parent / "benchmarks").exists(),
        reason="Not in EnterpriseBench repo",
    )
    def test_all_tasks_ready(self) -> None:
        """All real tasks should be ready (no blocking errors)."""
        task_dirs = vtp.collect_task_dirs()
        sg_index = vtp.load_sg_index()
        mirror_ids = vtp.load_mirror_task_ids()
        blocked = []
        for td in task_dirs:
            result = vtp.validate_task(td, None, None, sg_index, mirror_ids)
            if not result.ready:
                errors = [i for i in result.issues if i.severity == "error"]
                blocked.append((td.name, errors))
        assert blocked == [], f"Blocked tasks: {blocked}"
