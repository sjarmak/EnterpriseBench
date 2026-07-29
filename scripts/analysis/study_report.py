#!/usr/bin/env python3
"""Derive a study's headline from its capsule, and from nothing else.

The promotion path used to validate one raw-run directory and then hand the
analyzer no directory at all, so the analyzer fell back to recursively scanning
every ``results/runs``, ``mcp_batch*``, and ``smoke_*`` tree on the box. An
artifact promoted under one run ID could therefore contain scores from
unrelated or quarantined executions, and nothing in it said so.

This module takes a ``StudySpec`` and its receipt log, and reports what those
receipts say. There is no directory scan, no path parsing, and no fallback:
a receipt that does not belong to the named study is a hard failure, not a
skipped file.

Two economics views come out, from the same receipts and never blended:

``paired_valid``   spend on the prespecified comparable trials — the only
                   population an arm-to-arm cost claim may be built on.
``all_attempts``   every dollar the study incurred, including the
                   infrastructure failures that produced no measurement.

Contrasts are derived from the spec's declared arms rather than hard-coded, so
a third arm cannot execute correctly and then be absent from every delta.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from analyze_scores import statistical_tests  # noqa: E402
from eb_study import CapsuleError, PairedValid, StudyCapsule  # noqa: E402

logger = logging.getLogger(__name__)

#: Bumped when the report's shape changes, so a consumer refuses an unknown
#: version rather than reading a missing key through ``.get(key, 0)``.
SCHEMA_VERSION = 2

TOKEN_DEFINITION = (
    "combined_tokens = input + output + cache_creation + cache_read "
    "across every SDK-reported model"
)
TIMING_DEFINITION = (
    "elapsed_seconds = host-authored ended_at - started_at per receipt; "
    "totals sum trial durations and are not parallel makespan"
)
TOKEN_FIELD_ALIASES = {
    "input_tokens": ("input_tokens", "inputTokens"),
    "output_tokens": ("output_tokens", "outputTokens"),
    "cache_creation_tokens": (
        "cache_write_tokens",
        "cache_creation_input_tokens",
        "cacheCreationInputTokens",
    ),
    "cache_read_tokens": (
        "cache_read_tokens",
        "cache_read_input_tokens",
        "cacheReadInputTokens",
    ),
}
MODEL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}\Z")
MAX_TOKEN_COUNT = (1 << 63) - 1


def provenance(capsule: StudyCapsule) -> dict[str, Any]:
    """Everything the study froze before it observed an outcome."""

    spec = capsule.spec
    return {
        "study_id": spec.study_id,
        "spec_hash": spec.spec_hash,
        "task_manifest_hash": spec.task_manifest_hash,
        "arms": [a.to_json() for a in spec.arms],
        "baseline_arm": spec.baseline_arm,
        "repetitions": spec.repetitions,
        "attempt_policy": spec.attempt_policy,
        "model": spec.model,
        "harness": spec.harness,
        "revision": spec.revision,
        "token_source": spec.token_source,
        "score_contract": spec.score_contract,
        "promotion_policy": spec.promotion_policy,
    }


def completeness(capsule: StudyCapsule, paired: PairedValid) -> dict[str, Any]:
    """What the study declared against what it actually produced.

    Excluded tasks are named with the slots they were missing. A task that
    silently drops out of a comparison is indistinguishable from one that was
    never in it.
    """

    return {
        "declared_tasks": len(capsule.spec.task_ids),
        "paired_tasks": len(paired.task_ids),
        "paired_trials": len(paired.trials),
        "declared_slots": len(capsule.spec.slots()),
        "excluded_tasks": {
            tid: list(slots) for tid, slots in sorted(paired.excluded.items())
        },
        "receipts_by_status": capsule.all_attempts().count_by_status,
    }


def reward(capsule: StudyCapsule, paired: PairedValid) -> dict[str, Any]:
    """Per-arm distributions and every baseline contrast the spec declares."""

    per_task = {
        task_id: {arm: paired.mean_score(task_id, arm) for arm in paired.arms}
        for task_id in paired.task_ids
    }

    baseline = capsule.spec.baseline_arm
    contrasts = {
        f"{arm}_vs_{baseline}": _contrast(per_task, baseline, arm)
        for arm in capsule.spec.contrast_arms
    }

    return {
        "by_arm": {
            arm: _distribution([per_task[t][arm] for t in paired.task_ids])
            for arm in paired.arms
        },
        "contrasts": contrasts,
        "per_task": {
            task_id: {arm: round(score, 4) for arm, score in arms.items()}
            for task_id, arms in sorted(per_task.items())
        },
    }


def economics(capsule: StudyCapsule, paired: PairedValid) -> dict[str, Any]:
    """Both spend views, from the same receipts."""

    paired_costs = _costs_by_arm(paired.trials, paired.arms)
    all_costs = _costs_by_arm(capsule.receipts, capsule.spec.arm_names)
    paired_total = _finite_aggregate_cost(paired.cost_usd)
    all_total = _finite_aggregate_cost(capsule.all_attempts().cost_usd)

    return {
        "paired_valid": {
            "population": "prespecified comparable trials, complete in every declared arm",
            "total_cost_usd": paired_total,
            "by_arm_usd": paired_costs["by_arm_usd"],
            "per_task_usd": paired_costs["per_task_usd"],
            "cost_coverage": paired_costs["cost_coverage"],
            "trials": len(paired.trials),
        },
        "all_attempts": {
            "population": "every receipt the study emitted, valid or not",
            "total_cost_usd": all_total,
            "by_arm_usd": all_costs["by_arm_usd"],
            "per_task_usd": all_costs["per_task_usd"],
            "cost_coverage": all_costs["cost_coverage"],
            "receipts": len(capsule.receipts),
        },
    }


def tokens(capsule: StudyCapsule, paired: PairedValid) -> dict[str, Any]:
    """Report complete SDK token categories without collapsing away submodels."""

    return {
        "paired_valid": _token_view(paired.trials, paired.arms),
        "all_attempts": _token_view(capsule.receipts, capsule.spec.arm_names),
    }


def timing(capsule: StudyCapsule, paired: PairedValid) -> dict[str, Any]:
    """Report host-authored trial duration for both comparison populations."""

    return {
        "paired_valid": _timing_view(paired.trials, paired.arms),
        "all_attempts": _timing_view(capsule.receipts, capsule.spec.arm_names),
    }


def build_report(capsule: StudyCapsule) -> dict[str, Any]:
    paired = capsule.paired_valid()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance(capsule),
        "completeness": completeness(capsule, paired),
        "reward": reward(capsule, paired),
        "economics": economics(capsule, paired),
        "tokens": tokens(capsule, paired),
        "timing": timing(capsule, paired),
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _costs_by_arm(
    receipts: tuple[Any, ...],
    arms: tuple[str, ...],
) -> dict[str, Any]:
    costed = sum(
        1
        for receipt in receipts
        if receipt.usage is not None and receipt.usage.cost_usd is not None
    )
    return {
        "by_arm_usd": {arm: _cost_cell(receipts, arm=arm) for arm in sorted(arms)},
        "per_task_usd": {
            task_id: {
                arm: _cost_cell(receipts, arm=arm, task_id=task_id)
                for arm in sorted(arms)
            }
            for task_id in sorted({receipt.trial.task_id for receipt in receipts})
        },
        "cost_coverage": {
            "costed_trials": costed,
            "missing_cost_trials": len(receipts) - costed,
        },
    }


def _cost_cell(
    receipts: tuple[Any, ...],
    *,
    arm: str,
    task_id: str | None = None,
) -> float | None:
    cell = tuple(
        receipt
        for receipt in receipts
        if receipt.trial.arm == arm
        and (task_id is None or receipt.trial.task_id == task_id)
    )
    if not cell or any(
        receipt.usage is None or receipt.usage.cost_usd is None for receipt in cell
    ):
        return None
    return _finite_aggregate_cost(
        round(sum(receipt.usage.cost_usd for receipt in cell), 6)
    )


def _finite_aggregate_cost(cost_usd: float | None) -> float | None:
    if cost_usd is not None and not math.isfinite(cost_usd):
        raise CapsuleError("aggregate cost must be finite")
    return cost_usd


def _token_view(
    receipts: tuple[Any, ...],
    arms: tuple[str, ...],
) -> dict[str, Any]:
    normalized = tuple((receipt, _receipt_token_usage(receipt)) for receipt in receipts)
    known = tuple(
        (receipt, usage) for receipt, usage in normalized if usage is not None
    )
    missing = tuple(receipt for receipt, usage in normalized if usage is None)
    models = sorted({model for _receipt, usage in known for model in usage["by_model"]})
    return {
        "definition": TOKEN_DEFINITION,
        "coverage": {
            "tokenized_receipts": len(known),
            "missing_usage_receipts": len(missing),
        },
        "total": (
            None
            if missing
            else _sum_token_totals(tuple(usage["total"] for _, usage in known))
        ),
        "by_arm": {arm: _token_cell(normalized, arm=arm) for arm in sorted(arms)},
        "per_task": {
            task_id: {
                arm: _token_cell(normalized, task_id=task_id, arm=arm)
                for arm in sorted(arms)
            }
            for task_id in sorted({receipt.trial.task_id for receipt in receipts})
        },
        "by_model": {
            model: _sum_token_totals(
                tuple(
                    usage["by_model"][model]
                    for _receipt, usage in known
                    if model in usage["by_model"]
                )
            )
            for model in models
        },
    }


def _token_cell(
    normalized: tuple[tuple[Any, dict[str, Any] | None], ...],
    *,
    arm: str,
    task_id: str | None = None,
) -> dict[str, int] | None:
    cell = tuple(
        usage
        for receipt, usage in normalized
        if receipt.trial.arm == arm
        and (task_id is None or receipt.trial.task_id == task_id)
    )
    if not cell or any(usage is None for usage in cell):
        return None
    return _sum_token_totals(
        tuple(usage["total"] for usage in cell if usage is not None)
    )


def _receipt_token_usage(receipt: Any) -> dict[str, Any] | None:
    if receipt.usage is None:
        return None
    by_model = {
        model: _normalize_model_tokens(receipt.trial.key, model, usage)
        for model, usage in sorted(receipt.usage.model_usage.items())
    }
    return {
        "total": _sum_token_totals(tuple(by_model.values())),
        "by_model": by_model,
    }


def _normalize_model_tokens(
    trial_key: str,
    model: str,
    usage: Any,
) -> dict[str, int]:
    if not isinstance(model, str) or MODEL_NAME_RE.fullmatch(model) is None:
        raise CapsuleError(f"receipt {trial_key}: usage model name is invalid")
    if not isinstance(usage, dict):
        raise CapsuleError(f"receipt {trial_key}: usage model entry must be an object")
    totals = {
        field: _token_field(
            trial_key,
            model,
            usage,
            aliases,
            required=field in {"input_tokens", "output_tokens"},
        )
        for field, aliases in TOKEN_FIELD_ALIASES.items()
    }
    return {
        **totals,
        "combined_tokens": _checked_token_sum(tuple(totals.values())),
    }


def _token_field(
    trial_key: str,
    model: str,
    usage: dict[str, Any],
    aliases: tuple[str, ...],
    *,
    required: bool,
) -> int:
    present = tuple(alias for alias in aliases if alias in usage)
    if not present:
        if required:
            raise CapsuleError(
                f"receipt {trial_key}: usage model entry is missing {aliases[0]}"
            )
        return 0
    values = tuple(usage[alias] for alias in present)
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in values
    ):
        raise CapsuleError(
            f"receipt {trial_key}: usage model entry {present[0]} "
            "must be a non-negative integer"
        )
    if any(value > MAX_TOKEN_COUNT for value in values):
        raise CapsuleError(
            f"receipt {trial_key}: usage model token count "
            "must fit a signed 64-bit integer"
        )
    if len(set(values)) != 1:
        raise CapsuleError(
            f"receipt {trial_key}: usage model entry has conflicting "
            f"{'/'.join(present)} values"
        )
    value = values[0]
    return value


def _sum_token_totals(totals: tuple[dict[str, int], ...]) -> dict[str, int]:
    fields = (*TOKEN_FIELD_ALIASES, "combined_tokens")
    return {
        field: _checked_token_sum(tuple(total[field] for total in totals))
        for field in fields
    }


def _checked_token_sum(values: tuple[int, ...]) -> int:
    total = sum(values)
    if total > MAX_TOKEN_COUNT:
        raise CapsuleError("aggregate token count must fit a signed 64-bit integer")
    return total


def _timing_view(
    receipts: tuple[Any, ...],
    arms: tuple[str, ...],
) -> dict[str, Any]:
    timed = tuple((receipt, _elapsed_seconds(receipt)) for receipt in receipts)
    return {
        "definition": TIMING_DEFINITION,
        "total_elapsed_seconds": round(
            sum(seconds for _receipt, seconds in timed),
            6,
        ),
        "by_arm": {
            arm: _timing_summary(
                tuple(seconds for receipt, seconds in timed if receipt.trial.arm == arm)
            )
            for arm in sorted(arms)
        },
        "per_task_seconds": {
            task_id: {
                arm: round(
                    sum(
                        seconds
                        for receipt, seconds in timed
                        if receipt.trial.task_id == task_id and receipt.trial.arm == arm
                    ),
                    6,
                )
                for arm in sorted(arms)
            }
            for task_id in sorted({receipt.trial.task_id for receipt in receipts})
        },
    }


def _timing_summary(seconds: tuple[float, ...]) -> dict[str, Any]:
    if not seconds:
        return {
            "trials": 0,
            "total_elapsed_seconds": 0.0,
            "mean_elapsed_seconds": None,
        }
    return {
        "trials": len(seconds),
        "total_elapsed_seconds": round(sum(seconds), 6),
        "mean_elapsed_seconds": round(statistics.mean(seconds), 6),
    }


def _elapsed_seconds(receipt: Any) -> float:
    started = _parse_receipt_time(receipt.trial.key, "started_at", receipt.started_at)
    ended = _parse_receipt_time(receipt.trial.key, "ended_at", receipt.ended_at)
    elapsed = (ended - started).total_seconds()
    if elapsed < 0:
        raise CapsuleError(f"receipt {receipt.trial.key}: ended before it started")
    return elapsed


def _parse_receipt_time(trial_key: str, field: str, value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CapsuleError(f"receipt {trial_key}: invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CapsuleError(f"receipt {trial_key}: {field} must be timezone-aware")
    return parsed


def _format_cost(cost_usd: float | None) -> str:
    return "unavailable" if cost_usd is None else f"${cost_usd:.2f}"


def _distribution(scores: list[float]) -> dict[str, Any]:
    return {
        "n": len(scores),
        "mean": round(statistics.mean(scores), 4),
        "median": round(statistics.median(scores), 4),
        "std": round(statistics.stdev(scores), 4) if len(scores) > 1 else 0.0,
        "min": round(min(scores), 4),
        "max": round(max(scores), 4),
    }


def _contrast(
    per_task: dict[str, dict[str, float]],
    baseline: str,
    arm: str,
) -> dict[str, Any]:
    """Paired delta over the matched task set.

    Every task in ``per_task`` is complete in every declared arm — the capsule
    refuses to produce a paired view otherwise — so the pairing here cannot be
    an intersection that quietly shrank.
    """

    task_ids = sorted(per_task)
    baseline_scores = [per_task[t][baseline] for t in task_ids]
    arm_scores = [per_task[t][arm] for t in task_ids]
    deltas = [a - b for b, a in zip(baseline_scores, arm_scores)]

    n = len(deltas)
    improved = sum(1 for d in deltas if d > 0.001)
    degraded = sum(1 for d in deltas if d < -0.001)

    result: dict[str, Any] = {
        "n_paired": n,
        "mean_delta": round(statistics.mean(deltas), 4),
        "median_delta": round(statistics.median(deltas), 4),
        "pct_improved": round(improved / n, 4),
        "pct_degraded": round(degraded / n, 4),
        "pct_unchanged": round((n - improved - degraded) / n, 4),
    }
    result.update(statistical_tests(baseline_scores, arm_scores))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive a study headline from its capsule (spec + receipts).",
    )
    parser.add_argument("--spec", type=Path, required=True, help="StudySpec JSON path.")
    parser.add_argument(
        "--receipts", type=Path, required=True, help="Trial receipt JSONL path."
    )
    parser.add_argument("--output", type=Path, default=None, help="Report JSON path.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        capsule = StudyCapsule.load(args.spec, args.receipts)
        report = build_report(capsule)
    except CapsuleError as exc:
        # Fail closed. A study that cannot prove what it ran has no headline.
        logger.error("%s: %s", type(exc).__name__, exc)
        return 2

    try:
        payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
    except ValueError:
        logger.error("report contains a non-finite JSON number")
        return 2
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
        logger.info("Wrote %s", args.output)
    else:
        print(payload, end="")

    prov = report["provenance"]
    comp = report["completeness"]
    print(
        f"\n=== {prov['study_id']} ({prov['spec_hash'][:19]}) ===",
        file=sys.stderr,
    )
    print(
        f"  paired {comp['paired_tasks']}/{comp['declared_tasks']} tasks "
        f"across {len(prov['arms'])} arms; "
        f"{len(comp['excluded_tasks'])} excluded",
        file=sys.stderr,
    )
    for name, contrast in report["reward"]["contrasts"].items():
        print(
            f"  {name}: mean_delta={contrast['mean_delta']:+.3f} "
            f"cohens_d={contrast['cohens_d']:.3f} n={contrast['n_paired']}",
            file=sys.stderr,
        )
    econ = report["economics"]
    print(
        "  paired-valid "
        f"{_format_cost(econ['paired_valid']['total_cost_usd'])} · "
        "all-attempts "
        f"{_format_cost(econ['all_attempts']['total_cost_usd'])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
