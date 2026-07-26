"""The StudySpec — everything a study freezes before it observes an outcome.

A study's scientific identity has been rediscovered from filesystem paths:
directory names carried the arm, a ``rep<N>`` segment carried the repetition,
and whichever attempt scored highest carried the cell. Path shape is not a
contract. It changes when someone reorganizes a directory, and it cannot
express the fields that decide whether two runs are comparable at all — model,
harness revision, score contract, attempt policy.

The spec states those fields once, before execution, and hashes itself. Every
receipt then carries that hash, so a receipt produced under a different model,
a different score contract, or a different task manifest cannot silently join
the study it was not part of.

The spec is deliberately not a config file with defaults. Every frozen field is
required, because a default is a value nobody chose, and "nobody chose it" is
the one property a prespecification may not have.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import SpecError
from .hashing import canonical_json, content_hash

SPEC_SCHEMA_VERSION = 1

#: How the capsule collapses a task/arm cell to the trials it reports.
#:
#: ``all_valid_repetitions`` keeps every prespecified repetition that produced a
#: valid receipt. ``first_valid_attempt`` keeps the earliest valid attempt of
#: each repetition and classifies the rest as reruns.
#:
#: Neither consults the score. That is the point of naming them: an attempt rule
#: written down after the scores are visible is a selection procedure, not a
#: policy.
ATTEMPT_POLICIES = ("all_valid_repetitions", "first_valid_attempt")

#: The only token source a paired comparison may be billed from. The trace
#: re-derivation records one model per run and no sub-agent usage, so it cannot
#: price a multi-model run however carefully it is summed.
TOKEN_SOURCES = ("sdk_model_usage",)

_REQUIRED_FIELDS = (
    "study_id",
    "schema_version",
    "task_manifest_hash",
    "task_ids",
    "arms",
    "baseline_arm",
    "repetitions",
    "attempt_policy",
    "max_attempts",
    "model",
    "harness",
    "revision",
    "token_source",
    "score_contract",
    "promotion_policy",
)


@dataclass(frozen=True)
class Arm:
    """One declared arm and the capability set that defines it.

    ``capability_fingerprint`` is what makes "baseline" mean the same thing in
    two studies, or provably not. The name alone does not: an arm called
    ``mcp_only`` whose MCP server changed underneath it is a different arm.
    """

    name: str
    capability_fingerprint: str

    @classmethod
    def from_json(cls, payload: Any) -> "Arm":
        if not isinstance(payload, dict):
            raise SpecError(f"arm entry must be an object, got {type(payload).__name__}")
        name = payload.get("name")
        fingerprint = payload.get("capability_fingerprint")
        if not isinstance(name, str) or not name:
            raise SpecError("arm.name must be a non-empty string")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise SpecError(f"arm {name!r}: capability_fingerprint must be a non-empty string")
        return cls(name=name, capability_fingerprint=fingerprint)

    def to_json(self) -> dict[str, str]:
        return {"name": self.name, "capability_fingerprint": self.capability_fingerprint}


@dataclass(frozen=True)
class TrialID:
    """The stable identity of one execution.

    Every downstream join — score to cost, receipt to trace, report to
    promotion — keys on this and nothing else.
    """

    study_id: str
    task_id: str
    arm: str
    repetition: int
    attempt: int

    @property
    def key(self) -> str:
        return f"{self.study_id}/{self.task_id}/{self.arm}/rep{self.repetition}/att{self.attempt}"

    @property
    def slot(self) -> tuple[str, str, int]:
        """The prespecified (task, arm, repetition) this trial fills."""

        return (self.task_id, self.arm, self.repetition)

    def to_json(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "task_id": self.task_id,
            "arm": self.arm,
            "repetition": self.repetition,
            "attempt": self.attempt,
        }


@dataclass(frozen=True)
class StudySpec:
    """The frozen prespecification of one study."""

    study_id: str
    schema_version: int
    task_manifest_hash: str
    task_ids: tuple[str, ...]
    arms: tuple[Arm, ...]
    baseline_arm: str
    repetitions: int
    attempt_policy: str
    max_attempts: int
    model: str
    harness: str
    revision: str
    token_source: str
    score_contract: str
    promotion_policy: str

    # -- construction --------------------------------------------------

    @classmethod
    def from_json(cls, payload: Any) -> "StudySpec":
        """Build a spec from parsed JSON, rejecting anything under-specified."""

        if not isinstance(payload, dict):
            raise SpecError(f"spec must be a JSON object, got {type(payload).__name__}")

        missing = [f for f in _REQUIRED_FIELDS if f not in payload]
        if missing:
            raise SpecError(f"spec is missing required field(s): {', '.join(missing)}")

        version = payload["schema_version"]
        if version != SPEC_SCHEMA_VERSION:
            raise SpecError(
                f"spec schema_version {version!r} is not supported "
                f"(this build reads {SPEC_SCHEMA_VERSION})"
            )

        arms = tuple(Arm.from_json(a) for a in _require_list(payload, "arms"))
        arm_names = [a.name for a in arms]
        if len(set(arm_names)) != len(arm_names):
            raise SpecError(f"spec declares duplicate arm names: {arm_names}")

        baseline = payload["baseline_arm"]
        if baseline not in arm_names:
            raise SpecError(f"baseline_arm {baseline!r} is not one of the declared arms {arm_names}")

        task_ids = tuple(_require_list(payload, "task_ids"))
        if not task_ids:
            raise SpecError("spec declares no task_ids")
        if len(set(task_ids)) != len(task_ids):
            raise SpecError("spec declares duplicate task_ids")
        for tid in task_ids:
            if not isinstance(tid, str) or not tid:
                raise SpecError(f"task_ids entry must be a non-empty string, got {tid!r}")

        policy = payload["attempt_policy"]
        if policy not in ATTEMPT_POLICIES:
            raise SpecError(
                f"attempt_policy {policy!r} is not one of {ATTEMPT_POLICIES}. "
                "An attempt rule that consults the score is a selection procedure."
            )

        token_source = payload["token_source"]
        if token_source not in TOKEN_SOURCES:
            raise SpecError(f"token_source {token_source!r} is not one of {TOKEN_SOURCES}")

        return cls(
            study_id=_require_str(payload, "study_id"),
            schema_version=SPEC_SCHEMA_VERSION,
            task_manifest_hash=_require_str(payload, "task_manifest_hash"),
            task_ids=task_ids,
            arms=arms,
            baseline_arm=baseline,
            repetitions=_require_positive_int(payload, "repetitions"),
            attempt_policy=policy,
            max_attempts=_require_positive_int(payload, "max_attempts"),
            model=_require_str(payload, "model"),
            harness=_require_str(payload, "harness"),
            revision=_require_str(payload, "revision"),
            token_source=token_source,
            score_contract=_require_str(payload, "score_contract"),
            promotion_policy=_require_str(payload, "promotion_policy"),
        )

    @classmethod
    def load(cls, path: Path) -> "StudySpec":
        import json

        try:
            raw = Path(path).read_text()
        except OSError as exc:
            raise SpecError(f"cannot read study spec {path}: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SpecError(f"study spec {path} is not valid JSON: {exc}") from exc
        return cls.from_json(payload)

    # -- derived -------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "schema_version": self.schema_version,
            "task_manifest_hash": self.task_manifest_hash,
            "task_ids": list(self.task_ids),
            "arms": [a.to_json() for a in self.arms],
            "baseline_arm": self.baseline_arm,
            "repetitions": self.repetitions,
            "attempt_policy": self.attempt_policy,
            "max_attempts": self.max_attempts,
            "model": self.model,
            "harness": self.harness,
            "revision": self.revision,
            "token_source": self.token_source,
            "score_contract": self.score_contract,
            "promotion_policy": self.promotion_policy,
        }

    @property
    def spec_hash(self) -> str:
        """Content hash of every frozen field.

        Receipts carry it, so a spec edited mid-study orphans its own receipts
        instead of absorbing them.
        """

        return content_hash(self.to_json())

    @property
    def arm_names(self) -> tuple[str, ...]:
        return tuple(a.name for a in self.arms)

    @property
    def contrast_arms(self) -> tuple[str, ...]:
        """Non-baseline arms, in declaration order.

        Contrasts are derived here rather than hard-coded downstream, which is
        what kept the CLI arm out of every reward delta and every chart.
        """

        return tuple(n for n in self.arm_names if n != self.baseline_arm)

    def slots(self) -> tuple[tuple[str, str, int], ...]:
        """Every prespecified (task, arm, repetition) the study must fill."""

        return tuple(
            (task_id, arm, rep)
            for task_id in self.task_ids
            for arm in self.arm_names
            for rep in range(1, self.repetitions + 1)
        )

    def trial_id(self, task_id: str, arm: str, repetition: int, attempt: int) -> TrialID:
        """Compile one trial ID, refusing coordinates the spec never declared."""

        if task_id not in self.task_ids:
            raise SpecError(f"task {task_id!r} is not in study {self.study_id!r}")
        if arm not in self.arm_names:
            raise SpecError(f"arm {arm!r} is not declared by study {self.study_id!r}")
        if not 1 <= repetition <= self.repetitions:
            raise SpecError(
                f"repetition {repetition} is outside the declared range 1..{self.repetitions}"
            )
        if not 1 <= attempt <= self.max_attempts:
            raise SpecError(
                f"attempt {attempt} is outside the declared range 1..{self.max_attempts}"
            )
        return TrialID(
            study_id=self.study_id,
            task_id=task_id,
            arm=arm,
            repetition=repetition,
            attempt=attempt,
        )

    def canonical_text(self) -> str:
        return canonical_json(self.to_json())


# ---------------------------------------------------------------------------
# Field readers
# ---------------------------------------------------------------------------


def _require_str(payload: dict[str, Any], field: str) -> str:
    value = payload[field]
    if not isinstance(value, str) or not value:
        raise SpecError(f"spec.{field} must be a non-empty string, got {value!r}")
    return value


def _require_list(payload: dict[str, Any], field: str) -> list[Any]:
    value = payload[field]
    if not isinstance(value, list):
        raise SpecError(f"spec.{field} must be a list, got {type(value).__name__}")
    return value


def _require_positive_int(payload: dict[str, Any], field: str) -> int:
    value = payload[field]
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise SpecError(f"spec.{field} must be an integer >= 1, got {value!r}")
    return value
