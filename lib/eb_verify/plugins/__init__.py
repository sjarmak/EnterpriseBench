"""
Artifact validator plugin registry.

Each plugin implements validate(workspace: Path) -> ValidationResult.
Plugins are registered by artifact type name.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Protocol


@dataclass
class ValidationResult:
    valid: bool
    detail: str = ""


class ArtifactValidator(Protocol):
    """Protocol for artifact validators."""

    artifact_type: str

    def validate(self, workspace: Path) -> ValidationResult: ...


# Plugin registry — populated by imports below
_registry: Dict[str, ArtifactValidator] = {}


def register(validator: ArtifactValidator) -> None:
    _registry[validator.artifact_type] = validator


def get_validator(artifact_type: str) -> Optional[ArtifactValidator]:
    return _registry.get(artifact_type)


def list_validators() -> list[str]:
    return list(_registry.keys())


class FileTooLargeError(ValueError):
    """Raised by safe_read when a file exceeds the caller's max_bytes cap."""


def safe_read(path: Path, workspace: Path, max_bytes: Optional[int] = None) -> str:
    """Read a file, asserting the resolved path stays within workspace (symlink-safe).

    When max_bytes is set, files larger than the cap raise FileTooLargeError
    without being read. Containment is checked FIRST: an escaping path always
    reports the escape and is never stat'd for a size verdict.
    """
    resolved = path.resolve()
    workspace_resolved = workspace.resolve()
    if not str(resolved).startswith(str(workspace_resolved) + "/") and resolved != workspace_resolved:
        raise ValueError(
            f"Path escapes workspace: {path} -> {resolved}"
        )
    if max_bytes is not None:
        size = resolved.stat().st_size
        if size > max_bytes:
            raise FileTooLargeError(
                f"File too large to read: {path} is {size} bytes (max {max_bytes})"
            )
    return resolved.read_text()


# Import all plugins to trigger registration
from eb_verify.plugins.code_patch import CodePatchValidator
from eb_verify.plugins.config_validator import ConfigValidator
from eb_verify.plugins.incident_report import IncidentReportValidator
from eb_verify.plugins.runbook import RunbookValidator
from eb_verify.plugins.reproduction_script import ReproductionScriptValidator
from eb_verify.plugins.security_assessment import SecurityAssessmentValidator
from eb_verify.plugins.answer import AnswerValidator
from eb_verify.plugins.call_graph import CallGraphValidator
from eb_verify.plugins.topological_order import TopologicalOrderValidator
from eb_verify.plugins.fact_triples import FactTriplesValidator

register(CodePatchValidator())
register(ConfigValidator())
register(IncidentReportValidator())
register(RunbookValidator())
register(ReproductionScriptValidator())
register(SecurityAssessmentValidator())
register(AnswerValidator())
register(CallGraphValidator())
register(TopologicalOrderValidator())
register(FactTriplesValidator())
