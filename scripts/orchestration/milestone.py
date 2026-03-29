"""
Between-session milestone verification.

Runs milestone verifiers after each session to produce intermediate scores.
Milestones are defined per-session in the chain task definition.
"""

import subprocess
import logging
import json
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MilestoneResult:
    """Result of running a single milestone verifier."""
    session_number: int
    milestone_name: str
    passed: bool
    score: float  # 0.0 to 1.0
    message: str = ""


@dataclass
class SessionScore:
    """Aggregate score for a single session's milestones."""
    session_number: int
    milestones: list[MilestoneResult] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        if not self.milestones:
            return 0.0
        return sum(m.score for m in self.milestones) / len(self.milestones)

    @property
    def all_passed(self) -> bool:
        return all(m.passed for m in self.milestones)


def run_milestone_verifier(
    verifier_path: str,
    workspace_path: str,
    session_number: int,
    milestone_name: str,
    timeout_seconds: int = 120,
) -> MilestoneResult:
    """Run a single milestone verifier script.

    The verifier script receives the workspace path as its first argument.
    It should exit 0 for pass, non-zero for fail.
    stdout can contain a JSON object with {"score": float, "message": str}.
    """
    logger.info("Running milestone '%s' for session %d: %s",
                milestone_name, session_number, verifier_path)

    verifier = Path(verifier_path)
    if not verifier.exists():
        logger.warning("Verifier not found: %s", verifier_path)
        return MilestoneResult(
            session_number=session_number,
            milestone_name=milestone_name,
            passed=False,
            score=0.0,
            message="Verifier script not found",
        )

    try:
        result = subprocess.run(
            [str(verifier.resolve()), workspace_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=workspace_path,
        )
    except subprocess.TimeoutExpired:
        return MilestoneResult(
            session_number=session_number,
            milestone_name=milestone_name,
            passed=False,
            score=0.0,
            message=f"Verifier timed out after {timeout_seconds}s",
        )

    passed = result.returncode == 0
    score = 1.0 if passed else 0.0
    message = ""

    # Try to parse structured output from stdout
    try:
        output = json.loads(result.stdout)
        score = float(output.get("score", score))
        message = output.get("message", "")
    except (json.JSONDecodeError, ValueError):
        message = result.stdout.strip() if result.stdout else result.stderr.strip()

    return MilestoneResult(
        session_number=session_number,
        milestone_name=milestone_name,
        passed=passed,
        score=score,
        message=message,
    )


def run_session_milestones(
    milestones: list[dict],
    workspace_path: str,
    session_number: int,
    task_dir: str,
) -> SessionScore:
    """Run all milestones for a completed session.

    Args:
        milestones: List of {"name": str, "verifier": str} dicts from task definition.
        workspace_path: Path to the workspace root.
        session_number: Which session just completed.
        task_dir: Path to the task definition directory (verifier paths are relative to this).
    """
    session_score = SessionScore(session_number=session_number)

    for milestone in milestones:
        resolved = Path(task_dir, milestone["verifier"]).resolve()
        task_dir_resolved = Path(task_dir).resolve()
        if not str(resolved).startswith(str(task_dir_resolved) + "/"):
            raise ValueError(f"Verifier path escapes task directory: {resolved}")
        verifier_path = str(resolved)
        result = run_milestone_verifier(
            verifier_path=verifier_path,
            workspace_path=workspace_path,
            session_number=session_number,
            milestone_name=milestone["name"],
        )
        session_score.milestones.append(result)
        logger.info("  Milestone '%s': %s (score=%.2f)",
                     result.milestone_name,
                     "PASS" if result.passed else "FAIL",
                     result.score)

    return session_score
