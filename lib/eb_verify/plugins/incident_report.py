"""
incident_report validator — structured JSON with required fields + semantic checks.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from eb_verify.plugins import ValidationResult, safe_read


REQUIRED_FIELDS = ["timeline", "root_cause", "remediation", "affected_services"]

# Sections that should have non-empty content
REQUIRED_SECTIONS = {"timeline", "root_cause", "remediation"}


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Try to parse a timestamp string in various formats."""
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%H:%M:%S",
        "%H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def check_sections_completeness(data: dict[str, Any]) -> list[str]:
    """Check that required sections have non-empty content.

    Returns list of issues (empty = all good).
    """
    issues: list[str] = []
    for section in REQUIRED_SECTIONS:
        value = data.get(section)
        if value is None:
            continue  # missing field is caught elsewhere
        if isinstance(value, str) and not value.strip():
            issues.append(f"{section} is empty")
        elif isinstance(value, list) and len(value) == 0:
            issues.append(f"{section} is an empty list")
    return issues


def check_timeline_ordering(timeline: list[Any]) -> list[str]:
    """Verify timeline events are in chronological order.

    Returns list of issues (empty = all good or not enough timestamps to check).
    """
    if not isinstance(timeline, list) or len(timeline) < 2:
        return []

    issues: list[str] = []
    parsed_times: list[tuple[int, datetime]] = []

    for i, event in enumerate(timeline):
        if not isinstance(event, dict):
            continue
        # Look for time/timestamp field
        ts_str = event.get("time") or event.get("timestamp") or event.get("ts")
        if ts_str is None:
            continue
        ts = _parse_timestamp(str(ts_str))
        if ts is not None:
            parsed_times.append((i, ts))

    # Check chronological ordering
    for j in range(1, len(parsed_times)):
        idx_prev, t_prev = parsed_times[j - 1]
        idx_curr, t_curr = parsed_times[j]
        if t_curr < t_prev:
            issues.append(
                f"timeline event {idx_curr} ({t_curr}) is before event {idx_prev} ({t_prev})"
            )

    return issues


def check_cross_references(
    data: dict[str, Any],
    known_services: Optional[list[str]] = None,
    known_files: Optional[list[str]] = None,
) -> list[str]:
    """Validate that services/files mentioned in the report are plausible.

    When known_services or known_files are provided, checks references against them.
    Returns list of issues (empty = all good or no references to check).
    """
    issues: list[str] = []
    mentioned_services = data.get("affected_services", [])

    if known_services is not None and isinstance(mentioned_services, list):
        unknown = [s for s in mentioned_services if s not in known_services]
        if unknown:
            issues.append(
                f"unknown services referenced: {', '.join(unknown)}"
            )

    # Check if root_cause mentions any file paths and validate them
    if known_files is not None:
        root_cause = data.get("root_cause", "")
        if isinstance(root_cause, str):
            # Extract file-like references from root_cause
            file_refs = re.findall(r"[\w./\-]+\.\w{1,5}", root_cause)
            for ref in file_refs:
                basename = ref.rsplit("/", 1)[-1] if "/" in ref else ref
                if not any(
                    ref in kf or basename in kf or kf.endswith(basename)
                    for kf in known_files
                ):
                    issues.append(f"file reference '{ref}' in root_cause not in known files")

    return issues


class IncidentReportValidator:
    artifact_type = "incident_report"

    def validate(
        self,
        workspace: Path,
        known_services: Optional[list[str]] = None,
        known_files: Optional[list[str]] = None,
    ) -> ValidationResult:
        """
        Look for incident report artifacts and validate structure + semantics.

        Checks:
        1. Required fields present with correct types
        2. Required sections have non-empty content
        3. Timeline events are in chronological order
        4. Cross-references (services, files) are plausible when known lists provided
        """
        candidates = list(workspace.glob("**/incident_report.json")) + \
                     list(workspace.glob("**/incident-report.json")) + \
                     list(workspace.glob("**/output/incident_report.json")) + \
                     list(workspace.glob("**/artifacts/incident_report.json"))

        if not candidates:
            return ValidationResult(
                valid=False,
                detail="No incident report file found (expected incident_report.json)",
            )

        # Validate the first found
        report_path = candidates[0]
        try:
            data = json.loads(safe_read(report_path, workspace))
        except (json.JSONDecodeError, ValueError) as e:
            return ValidationResult(valid=False, detail=f"Invalid JSON: {e}")

        if not isinstance(data, dict):
            return ValidationResult(valid=False, detail="Report must be a JSON object")

        missing = [f for f in REQUIRED_FIELDS if f not in data]
        if missing:
            return ValidationResult(
                valid=False,
                detail=f"Missing required fields: {', '.join(missing)}",
            )

        # Validate field types
        issues: list[str] = []
        if "timeline" in data and not isinstance(data["timeline"], list):
            issues.append("timeline should be an array of events")
        if "affected_services" in data and not isinstance(data["affected_services"], list):
            issues.append("affected_services should be an array")
        if "root_cause" in data and not isinstance(data["root_cause"], str):
            issues.append("root_cause should be a string")
        if "remediation" in data:
            if not isinstance(data["remediation"], (str, list)):
                issues.append("remediation should be a string or array of steps")

        if issues:
            return ValidationResult(valid=False, detail="; ".join(issues))

        # --- Semantic checks ---
        warnings: list[str] = []

        # Section completeness
        completeness_issues = check_sections_completeness(data)
        warnings.extend(completeness_issues)

        # Timeline ordering
        if isinstance(data.get("timeline"), list):
            ordering_issues = check_timeline_ordering(data["timeline"])
            warnings.extend(ordering_issues)

        # Cross-reference validation
        xref_issues = check_cross_references(data, known_services, known_files)
        warnings.extend(xref_issues)

        detail = (
            f"Valid incident report at {report_path.name} "
            f"with {len(data.get('timeline', []))} timeline events"
        )
        if warnings:
            detail += "; WARNINGS: " + "; ".join(warnings)

        return ValidationResult(valid=True, detail=detail)
