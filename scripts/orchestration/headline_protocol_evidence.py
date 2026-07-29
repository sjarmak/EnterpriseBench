"""Validate immutable evidence cited by headline protocol amendments."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from eb_study import file_hash
from headline_protocol import HeadlineProtocol, V5_PROTOCOL


def validate_protocol_amendment_evidence(
    repo_root: Path,
    analysis_plan: Mapping[str, Any],
    *,
    protocol: HeadlineProtocol,
) -> None:
    """Fail closed when a protocol amendment's cited evidence has drifted."""

    if protocol != V5_PROTOCOL:
        return
    amendment = analysis_plan.get("protocol_amendment")
    if not isinstance(amendment, dict):
        raise ValueError("v5 protocol amendment is missing")
    evidence_value = amendment.get("zero_agent_exposure_evidence")
    expected_hash = amendment.get("zero_agent_exposure_evidence_sha256")
    if not isinstance(evidence_value, str) or not isinstance(expected_hash, str):
        raise ValueError("v5 zero-agent exposure evidence is not hash-bound")

    root = repo_root.resolve()
    evidence_path = (root / evidence_value).resolve()
    if evidence_path == root or root not in evidence_path.parents:
        raise ValueError("v5 zero-agent exposure evidence escapes the repository")
    if not evidence_path.is_file() or file_hash(evidence_path) != expected_hash:
        raise ValueError("v5 zero-agent exposure evidence hash does not match")
