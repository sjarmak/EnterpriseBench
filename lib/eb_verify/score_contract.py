"""The versioned ``task_score`` contract.

``task_score`` is the one number the whole benchmark is about, and its meaning
has changed once already without a version to mark the change. This module is
the normative statement of what the number means, plus the check that refuses
to read an artifact whose meaning is unknown.

The contract, version 2
-----------------------

::

    task_score = sum(score_i * weight_i) / sum(weight_i)

over the checkpoints that ran, and therefore ``task_score`` is in ``[0, 1]``
for any ``score_i`` in ``[0, 1]`` and any positive weights. The division is
what makes the range an invariant *by construction*. Task authoring already
requires weights to sum to 1.0 — enforced by
:mod:`eb_verify.schema_validator`, ``scripts/validate_tasks_preflight.py``,
and ``scripts/audit_consistency.py``, which CI runs as a standalone gate — so
for every currently-valid task the division is a numerical no-op. It is there
so that a mis-authored task cannot silently emit a number above 1.0 that a
consumer would then average into a mean.

Version 1 is the pre-contract regime and exists only as a name for what
historical artifacts contain: ``task_score = sum(score_i * weight_i)`` with no
division, and with every weight defaulting to 1.0 because the weights were not
plumbed to the scorer at all. That makes v1 ``task_score`` an unweighted 0-N
sum, which is why the v1-era consumer divided it by the checkpoint *count*.

Why the version is mandatory and sniffing is banned
---------------------------------------------------

The two regimes are not distinguishable by inspecting the artifact. A v1
four-checkpoint run whose checkpoints each scored 0.2 persists
``task_score = 0.8`` — identical to a v2 run that scored 0.8. Any magnitude
heuristic ("<= 1.0 means v2") silently misclassifies it, and misclassification
here does not fail, it produces a plausible wrong number. So the version is
read, never inferred, and an artifact that does not declare one is refused
rather than guessed at.

This mirrors ``cost_tracker.require_schema`` for the same reason: consumers
read score fields through ``.get(key, default)``, so an unversioned read
renders a believable number instead of failing, which is exactly what the
scoring trust boundary forbids.

Where the version is stamped
----------------------------

Producers write it into the scores object they emit:

* ``scripts/sandbox/test_runner.sh`` — the production Docker scorer. It is
  bash and cannot import this module, so it hardcodes the integer with a
  pointer back here; ``tests/test_score_contract.py`` asserts the two agree.
* ``scripts/orchestration/run_task.py`` — the LLM-judge rescore path, which is
  the *last* writer of ``task_score`` on a ``llm_curator`` task.
* ``scripts/orchestration/chain_runner.py`` — the chain scorer.

:func:`weighted_mean` is the one implementation of the v2 formula. Every Python
producer above calls it, as does :func:`eb_verify.scoring.compute_score`, so the
arithmetic exists once and a bump to v3 has one site to edit. The shell scorer
is the sole mirror, and it is a mirror only because it runs before this package
is importable.

In ``results.json`` the stamp lands inside the ``scores`` object, i.e.
``results.json["scores"]["score_contract_version"]``, because the runner
writes the scorer's JSON there verbatim.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

__all__ = [
    "SCORE_CONTRACT_VERSION",
    "LEGACY_SCORE_CONTRACT_VERSION",
    "ScoreContractError",
    "SCORE_CONTRACT_KEY",
    "read_task_score",
    "weighted_mean",
    "format_unreadable_sample",
]

#: The current contract. Bump only alongside a change to what ``task_score``
#: means, and update the shell mirror in ``scripts/sandbox/test_runner.sh``.
SCORE_CONTRACT_VERSION = 2

#: The pre-contract regime. Never stamped by anything — it is the version an
#: artifact is *declared* to be under, explicitly, by a caller analysing a
#: historical corpus.
LEGACY_SCORE_CONTRACT_VERSION = 1

SCORE_CONTRACT_KEY = "score_contract_version"


class ScoreContractError(ValueError):
    """An artifact's ``task_score`` cannot be read at a known contract."""


def weighted_mean(weighted_scores: Iterable[tuple[float, float]]) -> float:
    """Return the v2 ``task_score`` for ``(score, weight)`` pairs.

    The division is what makes the ``[0, 1]`` range an invariant, so it is the
    load-bearing half of the contract this module states — which is why the
    arithmetic lives here rather than at each producer. Every Python producer
    calls this; ``scripts/sandbox/test_runner.sh`` mirrors it in awk because it
    runs before this package is importable, and ``tests/test_score_contract.py``
    pins the two together.

    Zero total weight yields 0.0 rather than raising, preserving what all three
    Python producers already did. It is unreachable while task validation
    enforces weights summing to 1.0; it is here so a gate failure yields an
    honest 0.0 instead of a ZeroDivisionError. Non-positive totals take the same
    branch: a negative total weight would flip the sign of the mean, and an
    inverted score is a worse answer than a zero one.
    """

    pairs = list(weighted_scores)
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0:
        return 0.0
    return sum(score * weight for score, weight in pairs) / total_weight


def format_unreadable_sample(paths: Iterable[str], limit: int = 3) -> str:
    """Render *paths* as an indented sample, eliding the tail past *limit*.

    Both corpus scanners collect every unreadable artifact and report once, so
    both need the same sample-with-elision block. Only the surrounding prose
    differs between them — each states its own remedy — so this shares the
    index arithmetic and nothing else.
    """

    paths = list(paths)
    shown = paths[:limit]
    elided = len(paths) - len(shown)
    block = "\n".join(f"  {p}" for p in shown)
    return block + (f"\n  ... and {elided} more" if elided else "")


def read_task_score(
    scores: Mapping[str, Any],
    consumer: str,
    *,
    allow_legacy: bool = False,
) -> float:
    """Return *scores*' task_score on the v2 scale, or raise.

    Resolving the version and applying it are one step on purpose: the version
    is not information a caller has any other use for, and splitting them
    leaves a normalizer that has to re-handle versions its own gate already
    rejected.

    A missing stamp means the artifact predates the contract. With
    *allow_legacy* the caller is asserting it knows that and wants v1
    semantics; without it, the artifact is refused. A stamp that is present but
    is not a version this code knows is always refused — that direction is a
    future artifact read by old code, which no flag can make safe.
    """

    declared = scores.get(SCORE_CONTRACT_KEY)

    # An explicit null, a string, or a list all reach here as a present key, so
    # .get's default never fires for them. Letting float() raise would surface a
    # bare TypeError from inside the one module whose job is to fail closed with
    # a typed, actionable error — so the cast is owned here.
    raw = scores.get("task_score", 0.0)
    try:
        task_score = float(raw)
    except (TypeError, ValueError) as exc:
        raise ScoreContractError(
            f"{consumer}: task_score is {raw!r}, which is not a number. "
            f"A result that cannot state what it scored has no score to read."
        ) from exc

    if declared == SCORE_CONTRACT_VERSION:
        return task_score

    if declared is None:
        if allow_legacy:
            # v1 task_score is an unweighted 0-N sum, so it divides by the
            # checkpoint count — the same arithmetic the v1-era consumer did,
            # kept here so the legacy corpus stays readable and the
            # corrected-vs-legacy difference is a property of one function
            # rather than of two code paths.
            count = scores.get("checkpoints_total", 0)
            return task_score / count if count else 0.0
        raise ScoreContractError(
            f"{consumer}: result declares no {SCORE_CONTRACT_KEY}, so its "
            f"task_score predates the score contract and means "
            f"sum(score*weight) with unplumbed weights — not the v"
            f"{SCORE_CONTRACT_VERSION} weighted mean. The two are not "
            f"distinguishable by inspection, so this is not guessed at. "
            f"Re-run the task to produce a v{SCORE_CONTRACT_VERSION} result, "
            f"or pass --legacy-score-contract to read the historical corpus "
            f"under v{LEGACY_SCORE_CONTRACT_VERSION} semantics."
        )

    raise ScoreContractError(
        f"{consumer}: result declares {SCORE_CONTRACT_KEY}={declared!r}, "
        f"which this build does not know how to read (it understands "
        f"v{SCORE_CONTRACT_VERSION}). Reading it anyway would apply the wrong "
        f"formula to a real number."
    )
