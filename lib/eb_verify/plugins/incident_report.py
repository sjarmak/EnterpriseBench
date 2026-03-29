"""
incident_report validator — structured JSON with required fields.
"""

from __future__ import annotations

import json
from pathlib import Path

from eb_verify.plugins import ValidationResult, safe_read


REQUIRED_FIELDS = ["timeline", "root_cause", "remediation", "affected_services"]


class IncidentReportValidator:
    artifact_type = "incident_report"

    def validate(self, workspace: Path) -> ValidationResult:
        """
        Look for incident report artifacts and validate structure.
        Expected: JSON file with required fields.
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
        issues = []
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

        return ValidationResult(
            valid=True,
            detail=f"Valid incident report at {report_path.name} with {len(data.get('timeline', []))} timeline events",
        )
