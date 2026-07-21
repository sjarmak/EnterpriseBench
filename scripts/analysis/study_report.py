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
SCHEMA_VERSION = 1


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
        "excluded_tasks": {tid: list(slots) for tid, slots in sorted(paired.excluded.items())},
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

    paired_by_arm: dict[str, float] = {arm: 0.0 for arm in paired.arms}
    for trial in paired.trials:
        if trial.usage:
            paired_by_arm[trial.trial.arm] += trial.usage.cost_usd

    all_by_arm: dict[str, float] = {arm: 0.0 for arm in capsule.spec.arm_names}
    for receipt in capsule.receipts:
        if receipt.usage:
            all_by_arm[receipt.trial.arm] += receipt.usage.cost_usd

    return {
        "paired_valid": {
            "population": "prespecified comparable trials, complete in every declared arm",
            "total_cost_usd": paired.cost_usd,
            "by_arm_usd": {arm: round(v, 6) for arm, v in sorted(paired_by_arm.items())},
            "trials": len(paired.trials),
        },
        "all_attempts": {
            "population": "every receipt the study emitted, valid or not",
            "total_cost_usd": capsule.all_attempts().cost_usd,
            "by_arm_usd": {arm: round(v, 6) for arm, v in sorted(all_by_arm.items())},
            "receipts": len(capsule.receipts),
        },
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
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


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

    payload = json.dumps(report, indent=2) + "\n"
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
        f"  paired-valid ${econ['paired_valid']['total_cost_usd']:.2f} · "
        f"all-attempts ${econ['all_attempts']['total_cost_usd']:.2f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
