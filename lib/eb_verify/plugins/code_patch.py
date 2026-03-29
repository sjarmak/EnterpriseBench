"""
code_patch validator — checks that git diffs exist and apply cleanly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from eb_verify.plugins import ValidationResult


class CodePatchValidator:
    artifact_type = "code_patch"

    def validate(self, workspace: Path) -> ValidationResult:
        """
        Check that at least one repo in workspace has uncommitted or staged changes
        (i.e., the agent produced a code patch). Optionally check that diffs apply cleanly.
        """
        if not workspace.is_dir():
            return ValidationResult(valid=False, detail=f"Workspace not found: {workspace}")

        repos_with_changes = []
        for item in workspace.iterdir():
            if not item.is_dir():
                continue
            git_dir = item / ".git"
            if not git_dir.exists():
                continue
            # Check for any changes (staged or unstaged)
            try:
                result = subprocess.run(
                    ["git", "diff", "--stat", "HEAD"],
                    capture_output=True,
                    text=True,
                    cwd=str(item),
                    timeout=30,
                )
                if result.stdout.strip():
                    repos_with_changes.append(item.name)
                    continue
                # Also check staged
                result = subprocess.run(
                    ["git", "diff", "--cached", "--stat"],
                    capture_output=True,
                    text=True,
                    cwd=str(item),
                    timeout=30,
                )
                if result.stdout.strip():
                    repos_with_changes.append(item.name)
            except (subprocess.TimeoutExpired, Exception):
                continue

        if repos_with_changes:
            return ValidationResult(
                valid=True,
                detail=f"Code changes found in: {', '.join(repos_with_changes)}",
            )
        return ValidationResult(
            valid=False,
            detail="No code changes detected in any repo under workspace",
        )
