"""Tests for eb_verify.cli."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from eb_verify.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_bash_script(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def make_minimal_task_toml(tmp_path: Path, verifier_content: str | None = None) -> Path:
    """Write a minimal valid task TOML and optionally a verifier script."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()

    if verifier_content is not None:
        write_bash_script(task_dir / "checks" / "check.sh", verifier_content)

    toml_content = f"""
[task]
id = "cli-test-001"
suite = "dependency_management"
difficulty = "medium"
session_type = "single"
description = "CLI test task"
prompt = "Do something."

[[repos]]
url = "github.com/example/repo"
rev = "v1.0.0"
path = "repo"
role = "primary"

[[checkpoints]]
name = "only_step"
weight = 1.0
verifier = "checks/check.sh"

[artifacts]
required = []
"""
    task_file = task_dir / "task.toml"
    task_file.write_text(toml_content)
    return task_file


# ---------------------------------------------------------------------------
# validate subcommand
# ---------------------------------------------------------------------------

class TestCliValidate:
    def test_validate_valid_task(self, example_task_path, capsys):
        rc = main(["validate", str(example_task_path)])
        assert rc == 0
        out = capsys.readouterr()
        assert "VALID" in out.out

    def test_validate_valid_task_json(self, example_task_path, capsys):
        rc = main(["validate", "--json", str(example_task_path)])
        assert rc == 0
        out = capsys.readouterr()
        data = json.loads(out.out)
        assert data[0]["valid"] is True

    def test_validate_invalid_task(self, invalid_task_path, capsys):
        rc = main(["validate", str(invalid_task_path)])
        assert rc == 1

    def test_validate_invalid_task_json(self, invalid_task_path, capsys):
        rc = main(["validate", "--json", str(invalid_task_path)])
        assert rc == 1
        out = capsys.readouterr()
        data = json.loads(out.err)
        assert data[0]["valid"] is False
        assert len(data[0]["errors"]) > 0

    def test_validate_multiple_files(self, example_task_path, valid_task_path, capsys):
        rc = main(["validate", str(example_task_path), str(valid_task_path)])
        assert rc == 0

    def test_validate_nonexistent_file(self, tmp_path, capsys):
        rc = main(["validate", str(tmp_path / "nope.toml")])
        assert rc == 1

    def test_validate_chain_task(self, chain_task_path, capsys):
        rc = main(["validate", str(chain_task_path)])
        assert rc == 0


# ---------------------------------------------------------------------------
# validate-artifact subcommand
# ---------------------------------------------------------------------------

class TestCliValidateArtifact:
    def test_validate_artifact_known_type(self, tmp_path, capsys):
        # No answer file present → validator returns invalid, but CLI itself runs
        rc = main(["validate-artifact", "answer", str(tmp_path)])
        assert rc == 1  # invalid because no answer file

    def test_validate_artifact_valid_answer(self, tmp_path, capsys):
        (tmp_path / "answer.json").write_text('{"result": "ok"}')
        rc = main(["validate-artifact", "answer", str(tmp_path)])
        assert rc == 0

    def test_validate_artifact_unknown_type(self, tmp_path, capsys):
        rc = main(["validate-artifact", "totally_unknown_xyz", str(tmp_path)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "no validator" in err.lower()


# ---------------------------------------------------------------------------
# run subcommand
# ---------------------------------------------------------------------------

class TestCliRun:
    def test_run_passing_task(self, tmp_path, capsys):
        task_file = make_minimal_task_toml(
            tmp_path,
            verifier_content='#!/bin/bash\necho \'{"score": 1.0, "detail": "pass"}\'\n',
        )
        workspace = tmp_path / "ws"
        workspace.mkdir()
        output = tmp_path / "reward.txt"

        rc = main([
            "run", str(task_file),
            "--workspace", str(workspace),
            "--output", str(output),
        ])
        assert rc == 0
        assert output.exists()

    def test_run_failing_task(self, tmp_path, capsys):
        task_file = make_minimal_task_toml(
            tmp_path,
            verifier_content='#!/bin/bash\necho \'{"score": 0.0, "detail": "fail"}\'\n',
        )
        workspace = tmp_path / "ws"
        workspace.mkdir()
        output = tmp_path / "reward.txt"

        rc = main([
            "run", str(task_file),
            "--workspace", str(workspace),
            "--output", str(output),
        ])
        assert rc == 1

    def test_run_nonexistent_task_file(self, tmp_path, capsys):
        rc = main(["run", str(tmp_path / "nope.toml")])
        assert rc == 1
        err = capsys.readouterr().err
        assert "not found" in err.lower()


# ---------------------------------------------------------------------------
# check subcommand
# ---------------------------------------------------------------------------

class TestCliCheck:
    def test_check_passing_checkpoint(self, tmp_path, capsys):
        task_file = make_minimal_task_toml(
            tmp_path,
            verifier_content='#!/bin/bash\necho \'{"score": 1.0, "detail": "ok"}\'\n',
        )
        workspace = tmp_path / "ws"
        workspace.mkdir()

        rc = main([
            "check", "only_step", str(task_file),
            "--workspace", str(workspace),
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "PASS" in out

    def test_check_failing_checkpoint(self, tmp_path, capsys):
        task_file = make_minimal_task_toml(
            tmp_path,
            verifier_content='#!/bin/bash\necho \'{"score": 0.0, "detail": "nope"}\'\n',
        )
        workspace = tmp_path / "ws"
        workspace.mkdir()

        rc = main([
            "check", "only_step", str(task_file),
            "--workspace", str(workspace),
        ])
        assert rc == 1

    def test_check_unknown_checkpoint(self, tmp_path, capsys):
        task_file = make_minimal_task_toml(tmp_path)
        rc = main(["check", "nonexistent_cp", str(task_file)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "not found" in err.lower() or "Checkpoint" in err
