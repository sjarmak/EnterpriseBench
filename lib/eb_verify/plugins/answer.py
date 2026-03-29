"""
answer validator — oracle matching (keywords, files, symbols).
"""

from __future__ import annotations

import json
from pathlib import Path

from eb_verify.plugins import ValidationResult, safe_read


class AnswerValidator:
    artifact_type = "answer"

    def validate(self, workspace: Path) -> ValidationResult:
        """
        Look for answer.json or answer.txt and do basic structure check.
        Full oracle matching requires oracle data from the task definition,
        which would be passed at scoring time — this just validates the artifact exists
        and has the right structure.
        """
        json_candidates = list(workspace.glob("**/answer.json"))
        txt_candidates = list(workspace.glob("**/answer.txt"))

        if json_candidates:
            try:
                data = json.loads(safe_read(json_candidates[0], workspace))
                if isinstance(data, dict):
                    return ValidationResult(valid=True, detail="answer.json found and valid")
                return ValidationResult(valid=False, detail="answer.json should be a JSON object")
            except (json.JSONDecodeError, ValueError) as e:
                return ValidationResult(valid=False, detail=f"answer.json invalid: {e}")

        if txt_candidates:
            try:
                content = safe_read(txt_candidates[0], workspace).strip()
            except ValueError as e:
                return ValidationResult(valid=False, detail=str(e))
            if content:
                return ValidationResult(valid=True, detail="answer.txt found with content")
            return ValidationResult(valid=False, detail="answer.txt is empty")

        return ValidationResult(valid=False, detail="No answer file found")
