"""Scorer trust boundary — one invariant, enforced in one place.

A benchmark score is valid ONLY if the pristine verifier ran on real agent
output. Any infrastructure, verifier, or judge failure must surface as a
``verifier_infra_error`` and route the run to the re-run channel — it must never
be recorded as a legitimate ``0.0`` (false-zero / under-credit) or as an
un-capped grep score (judge-outage inflation / over-credit).

Before this module the invariant was re-implemented by hand at every scoring
entry point (``_run_scoring``, ``_apply_llm_judge``, ``code_patch.validate``,
the docker-cp copy path) and each got it subtly wrong in a different way
(beads: s58f, hktt/pt0n, wbsq, apfp). This module owns the single definition of
"infra failure vs real score" so every entry point enforces it identically.

The routing contract in ``run_task.py`` reads ``scores['verifier_infra_error']``
(the dict produced by :meth:`InfraError.as_verifier_error`) and sets
``phase='verifier_infra_error'`` so the run is never marked complete/success.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Union

# Sentinel a verifier emits in its ``detail`` to declare, on purpose, that the
# verifier harness itself failed (not that the agent failed the task). Kept
# explicit so the guard never has to guess from an arbitrary Python traceback —
# a task about an ImportError would otherwise be misclassified as infra.
INFRA_SENTINEL = "VERIFIER_INFRA_ERROR"

# Harness-import failure signature from the docker-cp package-drop regression
# (bead hktt/pt0n): a check script could not import the eb_verify harness and
# test_runner recorded it as a silent 0.0. This string names OUR harness module,
# never a task's subject code, so scanning for it cannot false-positive a task
# whose *own* code raises ModuleNotFoundError.
_HARNESS_IMPORT_FAILURE = "No module named 'eb_verify"

# Explicit, harness-specific detail signatures that mean "the verifier did not
# really run". Deliberately NOT a generic traceback/ImportError match — those
# occur legitimately in error-provenance task subjects.
_INFRA_DETAIL_SIGNATURES = (INFRA_SENTINEL, _HARNESS_IMPORT_FAILURE)


@dataclass(frozen=True)
class InfraError:
    """A scoring-infrastructure failure. Never a legitimate score."""

    reason: str  # machine key, e.g. "empty_verifier_output"
    stage: str  # scoring stage, e.g. "deterministic_scoring" | "llm_judge"
    detail: str  # human-readable explanation
    context: dict = field(default_factory=dict)

    def as_verifier_error(self) -> dict:
        """The dict shape ``run_task`` stores under ``verifier_infra_error``."""
        payload = {"reason": self.reason, "stage": self.stage, "detail": self.detail}
        payload.update(self.context)
        return payload


class DiffProbeError(Exception):
    """A git/subprocess probe failed to *run* (missing git, EACCES, corrupt
    .git, I/O error, timeout) — distinct from "git ran and found no diff".

    Raised by ``code_patch`` probes so a sandbox/infra failure is never
    collapsed into the same "no changes" 0-score as a genuinely clean repo.
    """


GuardResult = Union[dict, InfraError]


def _detail_infra_signature(detail: str) -> str | None:
    """Return the infra signature found in a checkpoint ``detail``, else None."""
    for sig in _INFRA_DETAIL_SIGNATURES:
        if sig in detail:
            return sig
    return None


def guard_verifier_output(
    stdout: str,
    returncode: int,
    *,
    stage: str = "deterministic_scoring",
) -> GuardResult:
    """Parse ``test.sh`` output into a scores dict, or an :class:`InfraError`.

    An :class:`InfraError` (never a numeric score) is returned when:

    * stdout is empty — the verifier produced nothing (crashed / mis-copied);
    * stdout is not valid JSON, or not a JSON object;
    * the parsed result carries a top-level ``error`` key — test.sh emits this
      for "cannot access repo" / "no .verifiers/ directory" (previously read by
      no caller, so it became a false 0.0);
    * a checkpoint ``detail`` carries an explicit infra signature
      (:data:`INFRA_SENTINEL` or the docker-cp harness-import failure).

    Otherwise the parsed scores dict is returned unchanged.
    """
    text = stdout.strip()
    if not text:
        return InfraError(
            reason="empty_verifier_output",
            stage=stage,
            detail=f"test.sh produced no output (exit {returncode})",
            context={"returncode": returncode},
        )

    try:
        scores = json.loads(text)
    except json.JSONDecodeError as exc:
        return InfraError(
            reason="malformed_verifier_output",
            stage=stage,
            detail=f"test.sh output was not valid JSON: {exc}",
            context={"returncode": returncode, "raw_output": text[:2000]},
        )

    if not isinstance(scores, dict):
        return InfraError(
            reason="malformed_verifier_output",
            stage=stage,
            detail=f"test.sh output was not a JSON object (got {type(scores).__name__})",
            context={"returncode": returncode, "raw_output": text[:2000]},
        )

    reported_error = scores.get("error")
    if reported_error:
        return InfraError(
            reason="verifier_reported_error",
            stage=stage,
            detail=f"test.sh reported an error: {reported_error}",
            context={"returncode": returncode},
        )

    for cp in scores.get("checkpoints", []):
        if not isinstance(cp, dict):
            continue
        sig = _detail_infra_signature(str(cp.get("detail", "")))
        if sig is not None:
            return InfraError(
                reason="verifier_crash",
                stage=stage,
                detail=(
                    f"checkpoint {cp.get('name', '?')!r} reported a verifier "
                    f"infra failure (signature: {sig!r})"
                ),
                context={"checkpoint": cp.get("name", ""), "signature": sig},
            )

    return scores
