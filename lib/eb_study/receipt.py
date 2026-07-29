"""Immutable per-trial receipts.

A receipt is what one execution says about itself, keyed by the trial ID the
spec compiled. It is written once, appended to a JSONL log, and never edited —
so "what did this study actually run" is answerable without trusting a
directory layout, a file mtime, or a later rescore pass.

Validity is typed and decided at write time, not inferred at read time. The
failure this guards is specific: a run whose repository clone failed, or whose
Tier-2 judge was unavailable, used to continue and emit a number. That number
is a measurement of the outage, and once it is in a ``scores`` block nothing
downstream can tell it apart from a real one. Here it cannot be written at all —
a non-valid receipt carries a failure class and no score.

The provenance requirements on a *valid* receipt are the other half. A receipt
that cannot name its image digest, its arm-gate proof, its score contract, and
its authoritative SDK usage does not describe a comparable trial, so it is
rejected rather than admitted with blanks that read as zeroes downstream.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import ReceiptError
from .json_io import strict_json_loads
from .spec import TrialID

RECEIPT_SCHEMA_VERSION = 1

#: The trial ran to completion under its declared arm and produced a score.
#: Only this status enters a paired comparison.
STATUS_VALID = "valid"

#: The environment, verifier, or judge failed. The agent's ability was never
#: measured, so there is no score to record — see the module docstring.
STATUS_INFRA_INVALID = "infra_invalid"

#: The arm gate refused the task: this task cannot be attempted under this arm
#: at all. Distinct from an infrastructure failure because it is a property of
#: the study design, not of the run.
STATUS_INELIGIBLE = "ineligible"

STATUSES = (STATUS_VALID, STATUS_INFRA_INVALID, STATUS_INELIGIBLE)
PRE_AGENT_MCP_ARTIFACTS = frozenset({"injected_instruction.md", "results.json"})
TRIAL_FIELDS = frozenset({"study_id", "task_id", "arm", "repetition", "attempt"})
USAGE_FIELDS = frozenset({"source", "cost_usd", "model_usage"})
RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "trial",
        "spec_hash",
        "task_manifest_hash",
        "status",
        "failure_class",
        "image_digest",
        "arm_gate_proof",
        "task_hash",
        "harness_hash",
        "verifier_hash",
        "score",
        "score_contract",
        "usage",
        "tool_use",
        "artifacts",
        "started_at",
        "ended_at",
    }
)


def is_zero_cost_pre_agent_mcp_failure(receipt: TrialReceipt) -> bool:
    """Return whether a validated receipt proves failure before agent startup."""

    return (
        receipt.usage is None
        and receipt.status == STATUS_INFRA_INVALID
        and receipt.failure_class == "infra_mcp_preflight"
        and receipt.score is None
        and receipt.score_contract is None
        and receipt.arm_gate_proof is None
        and not receipt.tool_use
        and "results.json" in receipt.artifacts
        and set(receipt.artifacts) <= PRE_AGENT_MCP_ARTIFACTS
    )


@dataclass(frozen=True)
class TrialUsage:
    """Authoritative token accounting for one trial.

    ``model_usage`` is the vendor's own per-model block, stored verbatim. It is
    kept rather than reduced to a total because a multi-model run cannot be
    re-priced from a single collapsed number, and the collapse is not
    reversible.
    """

    source: str
    cost_usd: float | None
    model_usage: Mapping[str, Any]

    @classmethod
    def from_json(cls, payload: Any) -> "TrialUsage":
        if not isinstance(payload, dict):
            raise ReceiptError(f"usage must be an object, got {type(payload).__name__}")
        _reject_unknown_fields(payload, USAGE_FIELDS, "usage")
        source = payload.get("source")
        if not isinstance(source, str) or not source:
            raise ReceiptError("usage.source must be a non-empty string")
        cost = payload.get("cost_usd")
        try:
            parsed_cost = None if cost is None else _finite_float(cost)
        except ReceiptError as exc:
            raise ReceiptError("usage.cost_usd must be a finite number >= 0") from exc
        if parsed_cost is not None and parsed_cost < 0:
            raise ReceiptError("usage.cost_usd must be a finite number >= 0")
        model_usage = payload.get("model_usage")
        if not isinstance(model_usage, dict) or not model_usage:
            raise ReceiptError("usage.model_usage must be a non-empty object")
        return cls(
            source=source,
            cost_usd=parsed_cost,
            model_usage=model_usage,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "cost_usd": self.cost_usd,
            "model_usage": dict(self.model_usage),
        }


@dataclass(frozen=True)
class TrialReceipt:
    """One immutable execution record."""

    trial: TrialID
    schema_version: int
    spec_hash: str
    task_manifest_hash: str
    status: str
    failure_class: str | None
    image_digest: str | None
    arm_gate_proof: str | None
    task_hash: str | None
    harness_hash: str | None
    verifier_hash: str | None
    score: float | None
    score_contract: str | None
    usage: TrialUsage | None
    tool_use: Mapping[str, Any]
    artifacts: Mapping[str, str]
    started_at: str
    ended_at: str

    @property
    def is_valid(self) -> bool:
        return self.status == STATUS_VALID

    # -- serialization -------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trial": self.trial.to_json(),
            "spec_hash": self.spec_hash,
            "task_manifest_hash": self.task_manifest_hash,
            "status": self.status,
            "failure_class": self.failure_class,
            "image_digest": self.image_digest,
            "arm_gate_proof": self.arm_gate_proof,
            "task_hash": self.task_hash,
            "harness_hash": self.harness_hash,
            "verifier_hash": self.verifier_hash,
            "score": self.score,
            "score_contract": self.score_contract,
            "usage": self.usage.to_json() if self.usage is not None else None,
            "tool_use": dict(self.tool_use),
            "artifacts": dict(self.artifacts),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    @classmethod
    def from_json(cls, payload: Any) -> "TrialReceipt":
        if not isinstance(payload, dict):
            raise ReceiptError(
                f"receipt must be an object, got {type(payload).__name__}"
            )
        _reject_unknown_fields(payload, RECEIPT_FIELDS, "receipt")

        version = payload.get("schema_version")
        if version != RECEIPT_SCHEMA_VERSION:
            raise ReceiptError(
                f"receipt schema_version {version!r} is not supported "
                f"(this build reads {RECEIPT_SCHEMA_VERSION})"
            )

        trial = _trial_from_json(payload.get("trial"))
        status = payload.get("status")
        if status not in STATUSES:
            raise ReceiptError(
                f"receipt {trial.key}: status {status!r} is not one of {STATUSES}"
            )

        receipt = cls(
            trial=trial,
            schema_version=RECEIPT_SCHEMA_VERSION,
            spec_hash=_require_str(payload, "spec_hash", trial),
            task_manifest_hash=_require_str(payload, "task_manifest_hash", trial),
            status=status,
            failure_class=_optional_str(payload, "failure_class", trial),
            image_digest=_optional_str(payload, "image_digest", trial),
            arm_gate_proof=_optional_str(payload, "arm_gate_proof", trial),
            task_hash=_optional_str(payload, "task_hash", trial),
            harness_hash=_optional_str(payload, "harness_hash", trial),
            verifier_hash=_optional_str(payload, "verifier_hash", trial),
            score=_optional_score(payload, trial),
            score_contract=_optional_str(payload, "score_contract", trial),
            usage=(
                TrialUsage.from_json(payload["usage"])
                if payload.get("usage") is not None
                else None
            ),
            tool_use=_require_mapping(payload, "tool_use", trial),
            artifacts=_require_artifacts(payload, trial),
            started_at=_require_str(payload, "started_at", trial),
            ended_at=_require_str(payload, "ended_at", trial),
        )
        receipt._check_status_invariants()
        return receipt

    # -- invariants ----------------------------------------------------

    def _check_status_invariants(self) -> None:
        """Reject a receipt whose provenance does not match its own status."""

        key = self.trial.key
        if self.status == STATUS_VALID:
            required = {
                "image_digest": self.image_digest,
                "arm_gate_proof": self.arm_gate_proof,
                "task_hash": self.task_hash,
                "harness_hash": self.harness_hash,
                "verifier_hash": self.verifier_hash,
                "score_contract": self.score_contract,
            }
            absent = sorted(name for name, value in required.items() if not value)
            if absent:
                raise ReceiptError(
                    f"receipt {key}: valid trial is missing required provenance: "
                    f"{', '.join(absent)}"
                )
            if self.score is None:
                raise ReceiptError(f"receipt {key}: valid trial carries no score")
            if self.usage is None:
                raise ReceiptError(
                    f"receipt {key}: valid trial carries no authoritative usage"
                )
            if self.failure_class:
                raise ReceiptError(
                    f"receipt {key}: valid trial also names failure_class "
                    f"{self.failure_class!r}"
                )
            return

        if not self.failure_class:
            raise ReceiptError(
                f"receipt {key}: {self.status} trial names no failure_class"
            )
        if self.score is not None:
            raise ReceiptError(
                f"receipt {key}: {self.status} trial carries score {self.score!r}. "
                "An unmeasured trial has no score to report."
            )


# ---------------------------------------------------------------------------
# Append-only log
# ---------------------------------------------------------------------------


def append_receipt(path: Path, receipt: TrialReceipt) -> None:
    """Append one receipt to the study's JSONL log.

    Append-only and duplicate-refusing: a trial ID that already has a receipt
    cannot get a second one. Rewriting a trial's outcome after seeing it is the
    exact move the capsule exists to prevent, and a retry is a new *attempt*
    with its own ID, not an overwrite.
    """

    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
        with handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.seek(0)
                for existing in _parse_receipt_lines(path, handle):
                    if existing.trial == receipt.trial:
                        raise ReceiptError(
                            f"receipt {receipt.trial.key} already exists in {path}. "
                            "Receipts are append-only; a retry is a new attempt."
                        )
                handle.seek(0, os.SEEK_END)
                handle.write(json.dumps(receipt.to_json(), sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise ReceiptError(f"cannot append receipt to {path}: {exc}") from exc


def _parse_receipt_lines(path: Path, lines: Iterable[str]) -> list[TrialReceipt]:
    receipts: list[TrialReceipt] = []
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = strict_json_loads(line)
        except ValueError as exc:
            raise ReceiptError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
        try:
            receipts.append(TrialReceipt.from_json(payload))
        except ReceiptError as exc:
            raise ReceiptError(f"{path}:{lineno}: {exc}") from exc
    return receipts


def read_receipts(path: Path) -> list[TrialReceipt]:
    """Read every receipt in a JSONL log, failing on the first malformed line."""

    path = Path(path)
    try:
        handle = path.open("r", encoding="utf-8")
        with handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            try:
                lines = list(handle)
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise ReceiptError(f"cannot read receipts {path}: {exc}") from exc

    return _parse_receipt_lines(path, lines)


def cache_isolated_receipt_costs(path: Path) -> tuple[float, ...]:
    """Return trusted historical costs, including proven pre-agent zeroes."""

    costs: list[float] = []
    for index, receipt in enumerate(read_receipts(path), start=1):
        if is_zero_cost_pre_agent_mcp_failure(receipt):
            costs.append(0.0)
            continue
        usage = receipt.usage
        isolation = receipt.tool_use.get("cache_isolation")
        cost = usage.cost_usd if usage is not None else None
        if (
            cost is None
            or not isinstance(isolation, dict)
            or isolation.get("valid") is not True
            or isolation.get("cache_write_tokens") != 0
            or isolation.get("cross_run_cache_read_tokens") != 0
        ):
            raise ReceiptError(
                f"{path}: receipt {index} lacks cache-isolated outer cost"
            )
        costs.append(cost)
    return tuple(costs)


# ---------------------------------------------------------------------------
# Field readers
# ---------------------------------------------------------------------------


def _trial_from_json(payload: Any) -> TrialID:
    if not isinstance(payload, dict):
        raise ReceiptError(
            f"receipt.trial must be an object, got {type(payload).__name__}"
        )
    _reject_unknown_fields(payload, TRIAL_FIELDS, "receipt.trial")
    missing = [
        f
        for f in ("study_id", "task_id", "arm", "repetition", "attempt")
        if f not in payload
    ]
    if missing:
        raise ReceiptError(f"receipt.trial is missing: {', '.join(missing)}")
    for field in ("study_id", "task_id", "arm"):
        if not isinstance(payload[field], str) or not payload[field]:
            raise ReceiptError(f"receipt.trial.{field} must be a non-empty string")
    for field in ("repetition", "attempt"):
        value = payload[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ReceiptError(
                f"receipt.trial.{field} must be an integer >= 1, got {value!r}"
            )
    return TrialID(
        study_id=payload["study_id"],
        task_id=payload["task_id"],
        arm=payload["arm"],
        repetition=payload["repetition"],
        attempt=payload["attempt"],
    )


def _require_str(payload: dict[str, Any], field: str, trial: TrialID) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ReceiptError(f"receipt {trial.key}: {field} must be a non-empty string")
    return value


def _optional_str(payload: dict[str, Any], field: str, trial: TrialID) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ReceiptError(
            f"receipt {trial.key}: {field} must be a non-empty string or null"
        )
    return value


def _optional_score(payload: dict[str, Any], trial: TrialID) -> float | None:
    value = payload.get("score")
    if value is None:
        return None
    try:
        parsed = _finite_float(value)
    except ReceiptError as exc:
        raise ReceiptError(
            f"receipt {trial.key}: score must be a finite number or null"
        ) from exc
    if not 0.0 <= parsed <= 1.0:
        raise ReceiptError(
            f"receipt {trial.key}: score {value!r} is outside 0..1. The receipt records the "
            "score contract's already-normalized value; nothing downstream renormalizes it."
        )
    return parsed


def _finite_float(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ReceiptError("value must be a finite number")
    try:
        parsed = float(value)
    except OverflowError as exc:
        raise ReceiptError("value must be a finite number") from exc
    if not math.isfinite(parsed):
        raise ReceiptError("value must be a finite number")
    return parsed


def _reject_unknown_fields(
    payload: Mapping[str, Any],
    allowed: frozenset[str],
    label: str,
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ReceiptError(f"{label} has unknown field(s): {', '.join(unknown)}")


def _require_mapping(
    payload: dict[str, Any], field: str, trial: TrialID
) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise ReceiptError(f"receipt {trial.key}: {field} must be an object")
    return value


def _require_artifacts(payload: dict[str, Any], trial: TrialID) -> dict[str, str]:
    value = _require_mapping(payload, "artifacts", trial)
    for name, digest in value.items():
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise ReceiptError(
                f"receipt {trial.key}: artifact {name!r} must map to a 'sha256:' digest"
            )
    return value
