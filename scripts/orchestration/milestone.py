"""
Between-session milestone verification.

Runs milestone verifiers after each session to produce intermediate scores.
Milestones are defined per-session in the chain task definition.

Scoring goes through ``eb_verify.scorer_guard`` — the same trust boundary the
Python checkpoint runner and ``test_runner.sh`` use — so all three runners share
one definition of "the verifier reached a verdict". A verifier that did not
reach one yields an :class:`InfraError`, never a number.
"""

import subprocess
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))
from eb_verify.scorer_guard import InfraError, guard_checkpoint_verdict, no_verdict

logger = logging.getLogger(__name__)

_STAGE = "milestone"


@dataclass
class MilestoneResult:
    """Result of running a single milestone verifier.

    ``score`` is ``None`` exactly when ``infra_error`` is set: the verifier never
    reached a verdict, so there is no score to record. Callers must not
    substitute a number for it — a placeholder 0.0 is a false zero that blames
    the agent for a broken harness, and a placeholder 1.0 is free credit.
    """

    session_number: int
    milestone_name: str
    passed: bool
    score: Optional[float]  # 0.0 to 1.0; None iff infra_error is set
    message: str = ""
    infra_error: Optional[InfraError] = None

    def __post_init__(self) -> None:
        # Enforced, not merely documented: the aggregators below multiply and sum
        # `score` unguarded, so a result that carried neither a score nor an error
        # would crash the chain, and one that carried both would let a placeholder
        # be averaged in as if it were real. Neither may be constructible.
        if (self.score is None) != (self.infra_error is not None):
            raise ValueError(
                f"milestone {self.milestone_name!r}: score and infra_error are "
                "mutually exclusive and jointly exhaustive — a verifier either "
                f"reached a verdict or it did not (score={self.score!r}, "
                f"infra_error={self.infra_error!r})"
            )


@dataclass
class SessionScore:
    """Aggregate score for a single session's milestones."""

    session_number: int
    milestones: list[MilestoneResult] = field(default_factory=list)

    @property
    def infra_errors(self) -> list[InfraError]:
        return [m.infra_error for m in self.milestones if m.infra_error is not None]

    @property
    def total_score(self) -> Optional[float]:
        """The mean milestone score, or None if any milestone never scored.

        Returning None rather than averaging over the milestones that *did* score
        is deliberate: a partial mean silently reweights the surviving milestones
        and reads downstream as a legitimate result.
        """
        if not self.milestones or self.infra_errors:
            return None
        return sum(m.score for m in self.milestones) / len(self.milestones)

    @property
    def all_passed(self) -> bool:
        return bool(self.milestones) and all(
            m.passed and m.infra_error is None for m in self.milestones
        )


def run_milestone_verifier(
    verifier_path: str,
    workspace_path: str,
    session_number: int,
    milestone_name: str,
    timeout_seconds: int = 120,
) -> MilestoneResult:
    """Run a single milestone verifier script.

    The verifier receives the workspace path as its first argument and MUST print
    a JSON object carrying a numeric ``score`` in [0.0, 1.0]; ``message`` is
    optional. It signals pass/fail with its exit code, which is read as pass/fail
    ONLY — never as a score. There is deliberately no exit-code score fallback:
    reading ``exit 0`` as a 1.0 hands full credit to a verifier that crashed
    before scoring anything, and ``exit 1`` as a 0.0 blames the agent for a broken
    harness (beads glka.2, kyo34, chc2z).
    """
    logger.info(
        "Running milestone '%s' for session %d: %s",
        milestone_name,
        session_number,
        verifier_path,
    )

    def failed(error: InfraError) -> MilestoneResult:
        logger.error(
            "Milestone '%s' did not reach a verdict (%s): %s",
            milestone_name,
            error.context.get("cause", error.reason),
            error.detail,
        )
        return MilestoneResult(
            session_number=session_number,
            milestone_name=milestone_name,
            passed=False,
            score=None,
            message=error.detail,
            infra_error=error,
        )

    def did_not_run(cause: str, detail: str, **evidence: object) -> MilestoneResult:
        return failed(
            no_verdict(
                cause,
                detail,
                checkpoint=milestone_name,
                stage=_STAGE,
                evidence=evidence,
            )
        )

    verifier = Path(verifier_path)
    if not verifier.exists():
        return did_not_run(
            "missing_verifier",
            f"verifier script not found: {verifier_path}",
            verifier=str(verifier_path),
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
        return did_not_run(
            "verifier_timeout",
            f"verifier timed out after {timeout_seconds}s",
            timeout_seconds=timeout_seconds,
        )
    except OSError as exc:
        # A non-executable or non-ELF verifier raises here. Uncaught, it took the
        # whole chain down mid-run — a harness bug reported as a crash, not a score.
        return did_not_run(
            "exec_error",
            f"verifier could not be executed: {exc}",
            verifier=str(verifier_path),
        )

    verdict = guard_checkpoint_verdict(
        result.stdout,
        result.returncode,
        stderr=result.stderr,
        checkpoint=milestone_name,
        stage=_STAGE,
    )
    if isinstance(verdict, InfraError):
        return failed(verdict)

    return MilestoneResult(
        session_number=session_number,
        milestone_name=milestone_name,
        # The verifier reached a verdict, so its exit code is a real pass/fail
        # signal: the real verifiers emit partial credit (e.g. 0.6) with exit 1.
        passed=result.returncode == 0,
        score=verdict["score"],
        message=str(verdict.get("message", "")),
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
        if result.infra_error is None:
            logger.info(
                "  Milestone '%s': %s (score=%.2f)",
                result.milestone_name,
                "PASS" if result.passed else "FAIL",
                result.score,
            )
        else:
            logger.warning(
                "  Milestone '%s': INVALID (no verdict: %s)",
                result.milestone_name,
                result.infra_error.context.get("cause", result.infra_error.reason),
            )

    return session_score
