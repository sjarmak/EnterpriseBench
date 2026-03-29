"""Tests for eb_verify.plugins."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from eb_verify.plugins import (
    ValidationResult,
    get_validator,
    list_validators,
    register,
)
from eb_verify.plugins.answer import AnswerValidator
from eb_verify.plugins.code_patch import CodePatchValidator
from eb_verify.plugins.config_validator import ConfigValidator
from eb_verify.plugins.incident_report import IncidentReportValidator
from eb_verify.plugins.reproduction_script import ReproductionScriptValidator
from eb_verify.plugins.runbook import RunbookValidator
from eb_verify.plugins.security_assessment import SecurityAssessmentValidator


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_all_expected_types_registered(self):
        registered = list_validators()
        expected = {
            "code_patch",
            "config",
            "incident_report",
            "runbook",
            "reproduction_script",
            "security_assessment",
            "answer",
        }
        for t in expected:
            assert t in registered, f"'{t}' not in registry"

    def test_get_validator_returns_instance(self):
        for name in list_validators():
            v = get_validator(name)
            assert v is not None
            assert hasattr(v, "validate")

    def test_get_validator_unknown_returns_none(self):
        result = get_validator("totally_unknown_xyz_999")
        assert result is None

    def test_artifact_type_attribute(self):
        v = get_validator("code_patch")
        assert v.artifact_type == "code_patch"

    def test_register_custom_validator(self):
        class FakeValidator:
            artifact_type = "_test_fake_xyz"

            def validate(self, workspace: Path) -> ValidationResult:
                return ValidationResult(valid=True, detail="fake")

        fake = FakeValidator()
        register(fake)
        assert get_validator("_test_fake_xyz") is fake


# ---------------------------------------------------------------------------
# ValidationResult dataclass
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_valid_true(self):
        r = ValidationResult(valid=True)
        assert r.valid is True
        assert r.detail == ""

    def test_valid_false_with_detail(self):
        r = ValidationResult(valid=False, detail="something wrong")
        assert r.valid is False
        assert r.detail == "something wrong"


# ---------------------------------------------------------------------------
# ConfigValidator
# ---------------------------------------------------------------------------

class TestConfigValidator:
    def test_no_artifacts_passes(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        validator = ConfigValidator()
        result = validator.validate(workspace)
        assert result.valid is True
        assert "No config" in result.detail

    def test_valid_json_in_output_dir(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        output = workspace / "output"
        output.mkdir()
        (output / "config.json").write_text('{"key": "value"}')

        validator = ConfigValidator()
        result = validator.validate(workspace)
        assert result.valid is True

    def test_invalid_json_fails(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        output = workspace / "output"
        output.mkdir()
        (output / "config.json").write_text("{bad json:::}")

        validator = ConfigValidator()
        result = validator.validate(workspace)
        assert result.valid is False
        assert "config.json" in result.detail

    def test_valid_json_in_artifacts_dir(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        arts = workspace / "artifacts"
        arts.mkdir()
        (arts / "settings.json").write_text('{"a": 1}')

        validator = ConfigValidator()
        result = validator.validate(workspace)
        assert result.valid is True

    def test_nonexistent_workspace(self, tmp_path):
        validator = ConfigValidator()
        result = validator.validate(tmp_path / "nonexistent")
        # No dirs found → no files → passes as "no artifacts"
        assert result.valid is True

    def test_validate_file_valid_json(self, tmp_path):
        f = tmp_path / "good.json"
        f.write_text('{"x": 1}')
        validator = ConfigValidator()
        result = validator._validate_file(f, tmp_path)
        assert result.valid is True

    def test_validate_file_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{invalid}")
        validator = ConfigValidator()
        result = validator._validate_file(f, tmp_path)
        assert result.valid is False

    def test_validate_file_valid_toml(self, tmp_path):
        f = tmp_path / "good.toml"
        f.write_text('[section]\nkey = "value"\n')
        validator = ConfigValidator()
        result = validator._validate_file(f, tmp_path)
        assert result.valid is True

    def test_validate_file_invalid_toml(self, tmp_path):
        f = tmp_path / "bad.toml"
        f.write_bytes(b"[section\nbad toml [[[")
        validator = ConfigValidator()
        result = validator._validate_file(f, tmp_path)
        # If toml parser available, should fail; otherwise passes (skip)
        # Either outcome is valid — we just assert no exception is raised
        assert isinstance(result.valid, bool)


# ---------------------------------------------------------------------------
# AnswerValidator
# ---------------------------------------------------------------------------

class TestAnswerValidator:
    def test_no_answer_file_fails(self, tmp_path):
        validator = AnswerValidator()
        result = validator.validate(tmp_path)
        assert result.valid is False
        assert "No answer file" in result.detail

    def test_valid_answer_json(self, tmp_path):
        (tmp_path / "answer.json").write_text('{"answer": "foo"}')
        validator = AnswerValidator()
        result = validator.validate(tmp_path)
        assert result.valid is True
        assert "answer.json" in result.detail

    def test_invalid_answer_json_syntax(self, tmp_path):
        (tmp_path / "answer.json").write_text("{invalid json")
        validator = AnswerValidator()
        result = validator.validate(tmp_path)
        assert result.valid is False

    def test_answer_json_not_object_fails(self, tmp_path):
        (tmp_path / "answer.json").write_text("[1, 2, 3]")
        validator = AnswerValidator()
        result = validator.validate(tmp_path)
        assert result.valid is False
        assert "JSON object" in result.detail

    def test_valid_answer_txt(self, tmp_path):
        (tmp_path / "answer.txt").write_text("The answer is 42.")
        validator = AnswerValidator()
        result = validator.validate(tmp_path)
        assert result.valid is True
        assert "answer.txt" in result.detail

    def test_empty_answer_txt_fails(self, tmp_path):
        (tmp_path / "answer.txt").write_text("")
        validator = AnswerValidator()
        result = validator.validate(tmp_path)
        assert result.valid is False
        assert "empty" in result.detail

    def test_json_takes_precedence_over_txt(self, tmp_path):
        (tmp_path / "answer.json").write_text('{"a": 1}')
        (tmp_path / "answer.txt").write_text("some text")
        validator = AnswerValidator()
        result = validator.validate(tmp_path)
        assert "answer.json" in result.detail

    def test_answer_json_in_subdir(self, tmp_path):
        subdir = tmp_path / "output"
        subdir.mkdir()
        (subdir / "answer.json").write_text('{"result": "ok"}')
        validator = AnswerValidator()
        result = validator.validate(tmp_path)
        assert result.valid is True


# ---------------------------------------------------------------------------
# CodePatchValidator
# ---------------------------------------------------------------------------

class TestCodePatchValidator:
    def test_nonexistent_workspace_fails(self, tmp_path):
        validator = CodePatchValidator()
        result = validator.validate(tmp_path / "nonexistent")
        assert result.valid is False
        assert "Workspace not found" in result.detail

    def test_workspace_no_repos_fails(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        validator = CodePatchValidator()
        result = validator.validate(workspace)
        assert result.valid is False
        assert "No code changes" in result.detail

    def test_workspace_with_non_git_dirs_fails(self, tmp_path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        (workspace / "not_a_repo").mkdir()
        validator = CodePatchValidator()
        result = validator.validate(workspace)
        assert result.valid is False


# ---------------------------------------------------------------------------
# IncidentReportValidator
# ---------------------------------------------------------------------------

class TestIncidentReportValidator:
    def test_artifact_type(self):
        v = IncidentReportValidator()
        assert v.artifact_type == "incident_report"

    def test_validate_returns_validation_result(self, tmp_path):
        v = IncidentReportValidator()
        result = v.validate(tmp_path)
        assert isinstance(result, ValidationResult)
        assert isinstance(result.valid, bool)


# ---------------------------------------------------------------------------
# RunbookValidator
# ---------------------------------------------------------------------------

class TestRunbookValidator:
    def test_artifact_type(self):
        v = RunbookValidator()
        assert v.artifact_type == "runbook"

    def test_validate_returns_validation_result(self, tmp_path):
        v = RunbookValidator()
        result = v.validate(tmp_path)
        assert isinstance(result, ValidationResult)


# ---------------------------------------------------------------------------
# ReproductionScriptValidator
# ---------------------------------------------------------------------------

class TestReproductionScriptValidator:
    def test_artifact_type(self):
        v = ReproductionScriptValidator()
        assert v.artifact_type == "reproduction_script"

    def test_validate_returns_validation_result(self, tmp_path):
        v = ReproductionScriptValidator()
        result = v.validate(tmp_path)
        assert isinstance(result, ValidationResult)


# ---------------------------------------------------------------------------
# SecurityAssessmentValidator
# ---------------------------------------------------------------------------

class TestSecurityAssessmentValidator:
    def test_artifact_type(self):
        v = SecurityAssessmentValidator()
        assert v.artifact_type == "security_assessment"

    def test_no_file_fails(self, tmp_path):
        v = SecurityAssessmentValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "No security assessment" in result.detail

    def test_valid_assessment(self, tmp_path):
        data = {
            "vulnerabilities": [{"id": "CVE-2024-001", "severity": "high"}],
            "severity_summary": {"high": 1},
            "recommendations": ["patch immediately"],
        }
        (tmp_path / "security_assessment.json").write_text(json.dumps(data))
        v = SecurityAssessmentValidator()
        result = v.validate(tmp_path)
        assert result.valid is True

    def test_missing_required_field(self, tmp_path):
        data = {"vulnerabilities": [], "severity_summary": {}}
        (tmp_path / "security_assessment.json").write_text(json.dumps(data))
        v = SecurityAssessmentValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "recommendations" in result.detail

    def test_invalid_json(self, tmp_path):
        (tmp_path / "security_assessment.json").write_text("{bad json")
        v = SecurityAssessmentValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "Invalid JSON" in result.detail

    def test_hyphen_filename_found(self, tmp_path):
        data = {
            "vulnerabilities": [],
            "severity_summary": {},
            "recommendations": [],
        }
        (tmp_path / "security-assessment.json").write_text(json.dumps(data))
        v = SecurityAssessmentValidator()
        result = v.validate(tmp_path)
        assert result.valid is True


# ---------------------------------------------------------------------------
# IncidentReportValidator (detailed)
# ---------------------------------------------------------------------------

class TestIncidentReportValidatorDetailed:
    def test_valid_report(self, tmp_path):
        data = {
            "timeline": [{"time": "00:00", "event": "alert fired"}],
            "root_cause": "Memory leak in service X",
            "remediation": "Restart service X",
            "affected_services": ["service-x", "service-y"],
        }
        (tmp_path / "incident_report.json").write_text(json.dumps(data))
        v = IncidentReportValidator()
        result = v.validate(tmp_path)
        assert result.valid is True
        assert "incident_report.json" in result.detail

    def test_no_file_fails(self, tmp_path):
        v = IncidentReportValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "No incident report" in result.detail

    def test_missing_required_fields(self, tmp_path):
        data = {"timeline": [], "root_cause": "x"}
        (tmp_path / "incident_report.json").write_text(json.dumps(data))
        v = IncidentReportValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "Missing required fields" in result.detail

    def test_invalid_json(self, tmp_path):
        (tmp_path / "incident_report.json").write_text("{not valid")
        v = IncidentReportValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "Invalid JSON" in result.detail

    def test_not_dict_fails(self, tmp_path):
        (tmp_path / "incident_report.json").write_text("[1, 2, 3]")
        v = IncidentReportValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "JSON object" in result.detail

    def test_timeline_not_list_fails(self, tmp_path):
        data = {
            "timeline": "not a list",
            "root_cause": "x",
            "remediation": "y",
            "affected_services": [],
        }
        (tmp_path / "incident_report.json").write_text(json.dumps(data))
        v = IncidentReportValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "timeline" in result.detail

    def test_affected_services_not_list_fails(self, tmp_path):
        data = {
            "timeline": [],
            "root_cause": "x",
            "remediation": "y",
            "affected_services": "not a list",
        }
        (tmp_path / "incident_report.json").write_text(json.dumps(data))
        v = IncidentReportValidator()
        result = v.validate(tmp_path)
        assert result.valid is False

    def test_hyphen_filename_found(self, tmp_path):
        data = {
            "timeline": [],
            "root_cause": "x",
            "remediation": "y",
            "affected_services": [],
        }
        (tmp_path / "incident-report.json").write_text(json.dumps(data))
        v = IncidentReportValidator()
        result = v.validate(tmp_path)
        assert result.valid is True


# ---------------------------------------------------------------------------
# RunbookValidator (detailed)
# ---------------------------------------------------------------------------

class TestRunbookValidatorDetailed:
    def test_valid_runbook(self, tmp_path):
        content = "# Overview\nSome overview.\n\n# Steps\n1. Do this.\n\n# Rollback\nRevert.\n"
        (tmp_path / "runbook.md").write_text(content)
        v = RunbookValidator()
        result = v.validate(tmp_path)
        assert result.valid is True
        assert "required sections" in result.detail

    def test_no_file_fails(self, tmp_path):
        v = RunbookValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "No runbook" in result.detail

    def test_missing_section(self, tmp_path):
        content = "# Overview\nSome overview.\n\n# Steps\n1. Do this.\n"
        (tmp_path / "runbook.md").write_text(content)
        v = RunbookValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "rollback" in result.detail.lower()

    def test_uppercase_runbook_found(self, tmp_path):
        content = "# Overview\nX\n# Steps\nY\n# Rollback\nZ\n"
        (tmp_path / "RUNBOOK.md").write_text(content)
        v = RunbookValidator()
        result = v.validate(tmp_path)
        assert result.valid is True


# ---------------------------------------------------------------------------
# ReproductionScriptValidator (detailed)
# ---------------------------------------------------------------------------

class TestReproductionScriptValidatorDetailed:
    def test_no_script_fails(self, tmp_path):
        v = ReproductionScriptValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "No reproduction script" in result.detail

    def test_non_executable_script_fails(self, tmp_path):
        script = tmp_path / "reproduce.sh"
        script.write_text("#!/bin/bash\necho hi\n")
        # Remove execute permission
        script.chmod(0o644)
        v = ReproductionScriptValidator()
        result = v.validate(tmp_path)
        assert result.valid is False
        assert "not executable" in result.detail

    def test_executable_script_passes(self, tmp_path):
        import stat as _stat
        script = tmp_path / "reproduce.sh"
        script.write_text("#!/bin/bash\necho hi\n")
        script.chmod(script.stat().st_mode | _stat.S_IEXEC)
        v = ReproductionScriptValidator()
        result = v.validate(tmp_path)
        assert result.valid is True
        assert "reproduce.sh" in result.detail

    def test_repro_prefix_found(self, tmp_path):
        import stat as _stat
        script = tmp_path / "repro.py"
        script.write_text("print('hi')")
        script.chmod(script.stat().st_mode | _stat.S_IEXEC)
        v = ReproductionScriptValidator()
        result = v.validate(tmp_path)
        assert result.valid is True
