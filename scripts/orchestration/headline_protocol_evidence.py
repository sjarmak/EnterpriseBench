"""Validate immutable evidence cited by headline protocol amendments."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from eb_study import file_hash
from headline_protocol import (
    HeadlineProtocol,
    V5_PROTOCOL,
    V6_PROTOCOL,
    V7_PROTOCOL,
)


def validate_protocol_amendment_evidence(
    repo_root: Path,
    analysis_plan: Mapping[str, Any],
    *,
    protocol: HeadlineProtocol,
) -> None:
    """Fail closed when a protocol amendment's cited evidence has drifted."""

    if protocol not in (V5_PROTOCOL, V6_PROTOCOL, V7_PROTOCOL):
        return
    amendment = analysis_plan.get("protocol_amendment")
    if not isinstance(amendment, dict):
        raise ValueError(f"{protocol.study_id} protocol amendment is missing")
    if protocol == V5_PROTOCOL:
        evidence = (
            (
                amendment.get("zero_agent_exposure_evidence"),
                amendment.get("zero_agent_exposure_evidence_sha256"),
            ),
        )
        error = "v5 zero-agent exposure evidence"
    else:
        evidence = (
            (
                amendment.get("predecessor_terminal_evidence"),
                amendment.get("predecessor_terminal_evidence_sha256"),
            ),
            (
                amendment.get("predecessor_receipts"),
                amendment.get("predecessor_receipts_sha256"),
            ),
        )
        error = f"{protocol.study_id.removeprefix('rryas-headline-')} predecessor evidence"

    root = repo_root.resolve()
    for evidence_value, expected_hash in evidence:
        if not isinstance(evidence_value, str) or not isinstance(expected_hash, str):
            raise ValueError(f"{error} is not hash-bound")
        evidence_path = (root / evidence_value).resolve()
        if evidence_path == root or root not in evidence_path.parents:
            raise ValueError(f"{error} escapes the repository")
        if not evidence_path.is_file() or file_hash(evidence_path) != expected_hash:
            raise ValueError(f"{error} hash does not match")
