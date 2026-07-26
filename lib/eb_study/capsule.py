"""The study capsule — a spec and its receipts, validated together.

Everything downstream of execution reads this, and only this. Promotion, score
analysis, cost accounting, and charts stop discovering what a study contains by
walking ``results/`` and stop deciding what a trial *is* from the shape of the
path it landed in.

Two views come out, and they are deliberately not one number:

``paired_valid``    the prespecified comparable trials, complete in every
                    declared arm. Reward claims are built on this and nothing
                    else.
``all_attempts``    every receipt, valid or not. This is what was actually
                    paid, including the infrastructure failures that produced
                    no measurement.

Neither view can quietly become the other, because an arm that produced no
valid trial raises instead of leaving the table.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import CapsuleIntegrityError, CompletenessError, SpecError
from .receipt import STATUS_VALID, TrialReceipt, read_receipts
from .spec import StudySpec


@dataclass(frozen=True)
class PairedValid:
    """The matched comparison population, and every count made of it.

    ``trials`` holds admitted valid receipts for complete tasks only.
    ``excluded`` names each task that did not survive and the slots it was
    missing — an excluded task is reported, never silently absent.
    """

    trials: tuple[TrialReceipt, ...]
    task_ids: tuple[str, ...]
    arms: tuple[str, ...]
    excluded: Mapping[str, tuple[str, ...]]

    @property
    def cost_usd(self) -> float:
        return round(sum(t.usage.cost_usd for t in self.trials if t.usage), 6)

    def mean_score(self, task_id: str, arm: str) -> float:
        """Mean score across the declared repetitions of one task/arm cell.

        The mean, not the best: picking a repetition by its score is the
        selection bias this package was written to remove. Every admitted
        repetition counts equally.
        """

        scores = [
            t.score
            for t in self.trials
            if t.trial.task_id == task_id and t.trial.arm == arm and t.score is not None
        ]
        if not scores:
            raise CompletenessError(
                f"no admitted trial for task {task_id!r} in arm {arm!r}"
            )
        return statistics.mean(scores)


@dataclass(frozen=True)
class AllAttempts:
    """Every receipt the study emitted, for economics that must not be netted."""

    receipts: tuple[TrialReceipt, ...]

    @property
    def cost_usd(self) -> float:
        return round(sum(r.usage.cost_usd for r in self.receipts if r.usage), 6)

    @property
    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.receipts:
            counts[r.status] = counts.get(r.status, 0) + 1
        return dict(sorted(counts.items()))


@dataclass(frozen=True)
class StudyCapsule:
    """A validated spec plus every receipt that belongs to it."""

    spec: StudySpec
    receipts: tuple[TrialReceipt, ...]

    # -- construction --------------------------------------------------

    @classmethod
    def load(cls, spec_path: Path, receipts_path: Path) -> "StudyCapsule":
        spec = StudySpec.load(spec_path)
        receipts = read_receipts(receipts_path)
        return cls.build(spec, receipts)

    @classmethod
    def build(cls, spec: StudySpec, receipts: list[TrialReceipt]) -> "StudyCapsule":
        """Validate receipts against the spec, fail-closed."""

        if not receipts:
            raise CapsuleIntegrityError(f"study {spec.study_id!r} has no receipts")

        seen: set[str] = set()
        for r in receipts:
            _check_belongs(spec, r)
            if r.trial.key in seen:
                raise CapsuleIntegrityError(f"duplicate receipt for trial {r.trial.key}")
            seen.add(r.trial.key)

        return cls(spec=spec, receipts=tuple(receipts))

    # -- views ---------------------------------------------------------

    def all_attempts(self) -> AllAttempts:
        return AllAttempts(receipts=self.receipts)

    def paired_valid(self) -> PairedValid:
        """Admit trials by the frozen attempt policy, then require completeness."""

        admitted = self._admit()

        by_arm: dict[str, int] = {arm: 0 for arm in self.spec.arm_names}
        for slot in admitted:
            by_arm[slot[1]] += 1
        empty_arms = sorted(arm for arm, n in by_arm.items() if n == 0)
        if empty_arms:
            raise CompletenessError(
                f"study {self.spec.study_id!r} declares arm(s) {empty_arms} with no valid "
                "trial. A comparison missing a declared arm is incomplete, not smaller."
            )

        complete: list[str] = []
        excluded: dict[str, tuple[str, ...]] = {}
        for task_id in self.spec.task_ids:
            missing = tuple(
                f"{arm}/rep{rep}"
                for arm in self.spec.arm_names
                for rep in range(1, self.spec.repetitions + 1)
                if (task_id, arm, rep) not in admitted
            )
            if missing:
                excluded[task_id] = missing
            else:
                complete.append(task_id)

        if not complete:
            raise CompletenessError(
                f"study {self.spec.study_id!r} has no task complete in every declared arm; "
                f"{len(excluded)} task(s) are incomplete"
            )

        kept = set(complete)
        trials = tuple(
            receipt for slot, receipt in sorted(admitted.items()) if slot[0] in kept
        )
        return PairedValid(
            trials=trials,
            task_ids=tuple(complete),
            arms=self.spec.arm_names,
            excluded=excluded,
        )

    # -- attempt policy ------------------------------------------------

    def _admit(self) -> dict[tuple[str, str, int], TrialReceipt]:
        """Collapse valid receipts to one per prespecified slot.

        Neither branch reads ``score``. Under ``all_valid_repetitions`` a slot
        with two valid attempts is an integrity failure — a trial that already
        produced a measurement was re-run, and keeping either one is a choice
        made after the fact. Under ``first_valid_attempt`` the earliest attempt
        wins by its declared number, and the later ones are reruns.
        """

        slots: dict[tuple[str, str, int], list[TrialReceipt]] = {}
        for r in self.receipts:
            if r.status == STATUS_VALID:
                slots.setdefault(r.trial.slot, []).append(r)

        admitted: dict[tuple[str, str, int], TrialReceipt] = {}
        for slot, candidates in slots.items():
            ordered = sorted(candidates, key=lambda r: r.trial.attempt)
            if len(ordered) > 1 and self.spec.attempt_policy == "all_valid_repetitions":
                attempts = [r.trial.attempt for r in ordered]
                raise CapsuleIntegrityError(
                    f"slot {slot} has {len(ordered)} valid attempts {attempts} under "
                    "attempt_policy 'all_valid_repetitions'. Choose between them and the "
                    "choice is made after the outcome; declare 'first_valid_attempt' "
                    "instead if reruns are expected."
                )
            admitted[slot] = ordered[0]
        return admitted


def _check_belongs(spec: StudySpec, receipt: TrialReceipt) -> None:
    """Reject a receipt that does not describe a trial of this exact study."""

    trial = receipt.trial
    if trial.study_id != spec.study_id:
        raise CapsuleIntegrityError(
            f"receipt {trial.key} belongs to study {trial.study_id!r}, "
            f"not {spec.study_id!r}"
        )
    if receipt.spec_hash != spec.spec_hash:
        raise CapsuleIntegrityError(
            f"receipt {trial.key} was produced under spec hash {receipt.spec_hash}, "
            f"but this spec hashes to {spec.spec_hash}"
        )
    if receipt.task_manifest_hash != spec.task_manifest_hash:
        raise CapsuleIntegrityError(
            f"receipt {trial.key} names task manifest {receipt.task_manifest_hash}, "
            f"but the spec froze {spec.task_manifest_hash}"
        )
    try:
        spec.trial_id(trial.task_id, trial.arm, trial.repetition, trial.attempt)
    except SpecError as exc:
        raise CapsuleIntegrityError(f"receipt {trial.key}: {exc}") from exc

    if receipt.status != STATUS_VALID:
        return
    if receipt.score_contract != spec.score_contract:
        raise CapsuleIntegrityError(
            f"receipt {trial.key} was scored under contract {receipt.score_contract!r}, "
            f"but the spec froze {spec.score_contract!r}"
        )
    if receipt.harness_hash != spec.harness:
        raise CapsuleIntegrityError(
            f"receipt {trial.key} used harness {receipt.harness_hash!r}, "
            f"but the spec froze {spec.harness!r}"
        )
    if receipt.usage is None or receipt.usage.source != spec.token_source:
        source = receipt.usage.source if receipt.usage else None
        raise CapsuleIntegrityError(
            f"receipt {trial.key} bills usage from {source!r}, "
            f"but the spec requires {spec.token_source!r}"
        )
