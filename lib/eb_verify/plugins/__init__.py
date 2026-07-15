"""
Artifact validator plugin registry.

Each plugin implements validate(workspace: Path) -> ValidationResult.
Plugins are registered by artifact type name.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Protocol

# Re-exported: the validators in this package all read artifacts through
# safe_read, and importing it from here costs them nothing (this registry
# imports every validator eagerly anyway). It is DEFINED in artifact_io so that
# groundedness can use it without importing the registry, which would cycle.
from eb_verify.artifact_io import (  # noqa: F401
    MAX_ARTIFACT_BYTES,
    FileTooLargeError,
    safe_read,
)


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

register(CodePatchValidator())
register(ConfigValidator())
register(IncidentReportValidator())
register(RunbookValidator())
register(ReproductionScriptValidator())
register(SecurityAssessmentValidator())
register(AnswerValidator())
register(CallGraphValidator())
register(TopologicalOrderValidator())

# fact_triples needs numpy/scikit-learn/jsonschema, which minimal task
# sandboxes do not ship. Register it only when its deps are importable so
# dependency-free scorers (e.g. plugins.file_extraction run via `python -m`
# inside the sandbox) can import this package without the heavy stack.
# get_validator("fact_triples") returns None in that case and the runner
# reports the unknown artifact type explicitly.
#
# The scoring deps must be probed explicitly: fact_triples defers them to its scoring
# call sites, so importing it cleanly proves only that jsonschema is present. Relying
# on the ImportError alone once registered a validator that then raised from inside
# validate() — which runner.py calls unguarded, killing the run instead of recording a
# clean unscoreable result. Raising here routes a missing dep through the same warning
# as a missing jsonschema, so there is one "unavailable" path rather than two.
try:
    from eb_verify.fact_coverage import scoring_deps_available

    if not scoring_deps_available():
        raise ImportError("numpy, scipy and scikit-learn are required to score facts")
    from eb_verify.plugins.fact_triples import FactTriplesValidator
except ImportError as _fact_triples_exc:  # numpy/sklearn/jsonschema absent
    import warnings

    warnings.warn(
        f"fact_triples validator unavailable (missing dependency: "
        f"{_fact_triples_exc}); it will not be registered",
        RuntimeWarning,
        stacklevel=2,
    )
else:
    register(FactTriplesValidator())
