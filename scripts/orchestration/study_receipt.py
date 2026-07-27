#!/usr/bin/env python3
"""Turn one finished run directory into one immutable trial receipt.

This is the producer half of the study capsule. The runner already writes
``results.json``, ``agent_stdout.log``, and a trace; what it did not write was a
record keyed by the study's own trial identity, so everything downstream had to
recover that identity from the shape of the path the run landed in.

Three decisions are made here and nowhere else:

**Whether the trial is valid.** A run whose status is INVALID, whose scorer
produced nothing, or whose authoritative usage block is unreadable becomes a
typed non-valid receipt with no score. It is not "a run that scored zero" —
nothing about the agent was measured, and a zero in an aggregate is
indistinguishable from a real one.

**Which number is the score.** The scorer's ``task_score`` is already the
weight-weighted sum of the checkpoint scores. It is copied through, not divided
again by the checkpoint count — that second division is what turned a perfect
four-checkpoint task into a 0.25. The contract is named in the receipt and the
weights are checked against it, so a task whose weights do not sum to 1.0
cannot emit a receipt claiming this contract.

**Where the money came from.** Cost is billed from the vendor's own
``modelUsage`` block via the same parser the cost report uses. There is no
trace-derived fallback here: the trace records one model per run and no
sub-agent usage, so a run without a vendor block cannot be priced for a
comparison and is recorded as infrastructure-invalid instead.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from cost_tracker import VendorUsage, parse_model_usage  # noqa: E402
from eb_study import (  # noqa: E402
    STATUS_INELIGIBLE,
    STATUS_INFRA_INVALID,
    STATUS_VALID,
    ReceiptError,
    StudySpec,
    TrialReceipt,
    file_hash,
)
from eb_verify.score_contract import (  # noqa: E402
    SCORE_CONTRACT_VERSION,
    ScoreContractError,
    read_task_score,
)

#: The score semantics this emitter implements. A spec that froze a different
#: contract will not accept these receipts — see StudyCapsule._check_belongs.
SCORE_CONTRACT = "weighted-mean-v2"

#: Files worth content-addressing. Absent ones are simply not listed; the
#: receipt records what exists rather than asserting paths that do not.
ARTIFACT_NAMES = (
    "results.json",
    "agent_stdout.log",
    "agent_trace.jsonl",
    "injected_instruction.md",
)


@dataclass(frozen=True)
class RunEvidence:
    """The proofs only the running harness can produce.

    These are arguments rather than derivations because none of them can be
    recovered from the output directory after the fact: the image is gone, the
    gate applied at runtime, and the hashes describe inputs the run consumed.
    """

    image_digest: str | None
    arm_gate_proof: str | None
    task_hash: str | None
    harness_hash: str | None
    verifier_hash: str | None
    started_at: str
    ended_at: str


def build_receipt(
    spec: StudySpec,
    run_dir: Path,
    *,
    repetition: int,
    attempt: int,
    evidence: RunEvidence,
) -> TrialReceipt:
    """Build the receipt for one finished run.

    Raises ``SpecError`` when the run's task or mode is not part of the study —
    a run outside the study cannot emit into it, whatever directory it wrote to.
    """

    run_dir = Path(run_dir)
    results = _read_results(run_dir)
    task_id = results.get("task_id")
    mode = results.get("config", {}).get("mode")
    if not task_id or not mode:
        raise ReceiptError(f"{run_dir}/results.json names no task_id/config.mode")

    trial = spec.trial_id(task_id, mode, repetition, attempt)
    vendor = parse_model_usage(run_dir / "agent_stdout.log")
    usage = _usage(spec, vendor, results)
    artifacts = {
        name: file_hash(run_dir / name)
        for name in ARTIFACT_NAMES
        if (run_dir / name).exists()
    }

    common: dict[str, Any] = {
        "schema_version": 1,
        "trial": trial.to_json(),
        "spec_hash": spec.spec_hash,
        "task_manifest_hash": spec.task_manifest_hash,
        "image_digest": evidence.image_digest,
        "arm_gate_proof": evidence.arm_gate_proof,
        "task_hash": evidence.task_hash,
        "harness_hash": evidence.harness_hash,
        "verifier_hash": evidence.verifier_hash,
        "usage": usage,
        "tool_use": results.get("tool_usage") or {},
        "artifacts": artifacts,
        "started_at": evidence.started_at,
        "ended_at": evidence.ended_at,
    }

    invalid = _invalidity(results, usage)
    if invalid is not None:
        status, failure_class = invalid
        return TrialReceipt.from_json(
            {
                **common,
                "status": status,
                "failure_class": failure_class,
                "score": None,
                "score_contract": None,
            }
        )

    return TrialReceipt.from_json(
        {
            **common,
            "status": STATUS_VALID,
            "failure_class": None,
            "score": _score(results["scores"], trial.key),
            "score_contract": SCORE_CONTRACT,
        }
    )


# ---------------------------------------------------------------------------
# Validity
# ---------------------------------------------------------------------------


def _invalidity(
    results: dict[str, Any],
    usage: dict[str, Any] | None,
) -> tuple[str, str] | None:
    """Classify the run, or return None when it is a measured trial.

    Order matters: the runner's own verdict is asked first, so a run that
    already knows why it failed is not relabelled by a downstream symptom of
    that same failure.
    """

    failure_class = results.get("failure_class")
    if failure_class == "task_ineligible":
        return (STATUS_INELIGIBLE, failure_class)

    status = results.get("status")
    if status or not (results.get("success") or results.get("phase") == "complete"):
        return (STATUS_INFRA_INVALID, failure_class or "run_invalid")

    scores = results.get("scores")
    if not scores or not scores.get("checkpoints"):
        return (STATUS_INFRA_INVALID, "scorer_produced_no_checkpoints")

    if usage is None:
        return (STATUS_INFRA_INVALID, "authoritative_usage_missing")

    return None


def _score(scores: dict[str, Any], trial_key: str) -> float:
    """Read the scorer's normalized value through the normative v2 contract."""

    try:
        return read_task_score(scores, f"receipt {trial_key}")
    except ScoreContractError as exc:
        raise ReceiptError(
            f"receipt {trial_key}: score contract must be version "
            f"{SCORE_CONTRACT_VERSION}: {exc}"
        ) from exc


def _usage(
    spec: StudySpec,
    vendor: VendorUsage | None,
    results: dict[str, Any],
) -> dict[str, Any] | None:
    """The vendor's per-model split, kept whole rather than collapsed to a total."""

    if spec.token_source == "provider_native_usage":
        return _provider_native_usage(spec, results)
    if vendor is None:
        return None
    return {
        "source": spec.token_source,
        "cost_usd": round(vendor.total_cost_usd, 6),
        "model_usage": {
            m.model: {
                "input_tokens": m.input_tokens,
                "output_tokens": m.output_tokens,
                "cache_write_tokens": m.cache_write_tokens,
                "cache_read_tokens": m.cache_read_tokens,
                "cost_usd": m.cost_usd,
            }
            for m in vendor.models
        },
    }


def _provider_native_usage(
    spec: StudySpec,
    results: dict[str, Any],
) -> dict[str, Any] | None:
    """Normalize Codex/OpenCode's native usage without inventing dollar cost."""

    harness = _provider_harness(spec, results)
    tool_usage = results.get("tool_usage")
    if not isinstance(tool_usage, dict):
        return None
    activity = tool_usage.get("provider_activity")
    if not isinstance(activity, dict) or activity.get("provider") != harness:
        return None

    tokens = _provider_tokens(tool_usage)
    if tokens is None:
        return None
    input_tokens, output_tokens, cache_write, cache_read = tokens
    cost = _provider_cost(harness, tool_usage)
    if harness == "opencode" and cost is None:
        return None

    return {
        "source": spec.token_source,
        "cost_usd": round(cost, 6) if cost is not None else None,
        "model_usage": {
            spec.model: {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_write_tokens": cache_write,
                "cache_read_tokens": cache_read,
                "cost_usd": round(cost, 6) if cost is not None else None,
            }
        },
    }


def _provider_harness(spec: StudySpec, results: dict[str, Any]) -> str:
    config = results.get("config")
    if not isinstance(config, dict):
        raise ReceiptError("provider_native_usage run has no config")
    model = config.get("model")
    if model != spec.model:
        raise ReceiptError(
            f"run model {model!r} does not match study model {spec.model!r}"
        )
    harness = config.get("harness")
    if harness not in {"codex", "opencode"}:
        raise ReceiptError(
            "provider_native_usage requires harness 'codex' or 'opencode', "
            f"got {harness!r}"
        )
    return harness


def _provider_tokens(
    tool_usage: dict[str, Any],
) -> tuple[int, int, int, int] | None:
    input_tokens = _nonnegative_int(tool_usage.get("total_input_tokens"))
    output_tokens = _nonnegative_int(tool_usage.get("total_output_tokens"))
    isolation = tool_usage.get("cache_isolation")
    if input_tokens is None or output_tokens is None or not isinstance(isolation, dict):
        return None
    if (
        isolation.get("valid") is not True
        or _nonnegative_int(isolation.get("cross_run_cache_read_tokens")) != 0
    ):
        return None
    cache_write = _nonnegative_int(isolation.get("cache_write_tokens"))
    cache_read = _nonnegative_int(isolation.get("total_cache_read_tokens"))
    if input_tokens + output_tokens == 0 or cache_write is None or cache_read is None:
        return None
    return input_tokens, output_tokens, cache_write, cache_read


def _provider_cost(harness: str, tool_usage: dict[str, Any]) -> float | None:
    if harness == "codex":
        return None
    if tool_usage.get("cost_usd_observed") is not True:
        return None
    cost = tool_usage.get("cost_usd")
    if (
        isinstance(cost, (int, float))
        and not isinstance(cost, bool)
        and math.isfinite(cost)
        and cost >= 0
    ):
        return float(cost)
    return None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _read_results(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "results.json"
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        raise ReceiptError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReceiptError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReceiptError(f"{path} is not a JSON object")
    return payload


__all__ = ["RunEvidence", "SCORE_CONTRACT", "build_receipt"]
