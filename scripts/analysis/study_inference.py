"""Deterministic inference for a frozen capsule study.

The study manifest binds task strata and the manifest binds the analysis-plan
bytes.  This module refuses to infer either from result paths or task names.
Confirmatory output is withheld until every declared task has a complete,
valid paired cell.
"""

from __future__ import annotations

import hashlib
import math
import re
import statistics
from typing import Any, Mapping, Sequence

from analysis.study_analysis_contract import (  # noqa: F401
    AnalysisContract,
    load_analysis_contract,
    parse_analysis_contract,
)
from eb_study import CapsuleError

PARITY_CONFIDENCE_LEVEL = 0.90
FAMILYWISE_ALPHA = 0.05
SAFE_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")


def bootstrap_mean_difference(
    baseline_scores: Sequence[float],
    candidate_scores: Sequence[float],
    *,
    repetitions: int,
    seed: int,
    confidence_levels: tuple[float, ...],
) -> dict[str, Any]:
    """Paired percentile bootstrap of the unweighted mean task difference."""

    baseline = _score_sample(baseline_scores, "baseline")
    candidate = _score_sample(candidate_scores, "candidate")
    if len(baseline) != len(candidate):
        raise CapsuleError("paired bootstrap samples must have equal length")
    if (
        not isinstance(repetitions, int)
        or isinstance(repetitions, bool)
        or repetitions < 1
    ):
        raise CapsuleError("bootstrap repetitions must be a positive integer")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise CapsuleError("bootstrap seed must be a non-negative integer")
    if not confidence_levels or any(
        not _is_finite_number(level) or not 0 < level < 1 for level in confidence_levels
    ):
        raise CapsuleError("bootstrap confidence levels must be between zero and one")

    raw = _bootstrap_analysis(
        baseline,
        candidate,
        resample_indices=_flat_resample_indices(
            sample_size=len(baseline),
            repetitions=repetitions,
            seed=seed,
        ),
        confidence_levels=confidence_levels,
    )
    return {
        "n_paired": len(baseline),
        "mean_delta": _round_metric(raw["mean_delta"]),
        "confidence_intervals": {
            key: {
                "low": _round_metric(interval["low"]),
                "high": _round_metric(interval["high"]),
            }
            for key, interval in raw["confidence_intervals"].items()
        },
        "p_value_two_sided_centered_bootstrap": _round_metric(
            raw["p_value_two_sided_centered_bootstrap"]
        ),
    }


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values with deterministic tie ordering."""

    if not p_values:
        raise CapsuleError("Holm adjustment requires at least one p-value")
    if any(
        not isinstance(name, str)
        or SAFE_NAME_RE.fullmatch(name) is None
        or not _is_finite_number(value)
        or not 0 <= value <= 1
        for name, value in p_values.items()
    ):
        raise CapsuleError("Holm adjustment received an invalid p-value")

    adjusted = _holm_adjust_raw(p_values)
    return {name: _round_metric(adjusted[name]) for name in sorted(adjusted)}


def build_inference(
    *,
    per_task_scores: Mapping[str, Mapping[str, float]],
    contract: AnalysisContract,
    complete: bool,
) -> dict[str, Any]:
    """Produce inference only for the complete manifest-bound task population."""

    declared = set(contract.task_types)
    observed = set(per_task_scores)
    unexpected = sorted(observed - declared)
    if unexpected:
        raise CapsuleError("paired scores contain tasks outside the task manifest")
    missing = sorted(declared - observed)
    if not complete or missing:
        return {
            "status": "withheld_incomplete",
            "analysis_plan_hash": contract.plan_hash,
            "task_manifest_hash": contract.manifest_hash,
            "declared_tasks": len(declared),
            "paired_tasks": len(observed),
            "missing_task_ids": missing,
            "reason": (
                "confirmatory inference requires every declared task to be "
                "paired and valid"
            ),
        }

    task_ids = tuple(contract.task_types)
    required_arms = {
        arm
        for contrast in (
            *contract.primary_contrasts,
            contract.descriptive_contrast,
        )
        for arm in contrast
    }
    _validate_score_matrix(per_task_scores, task_ids, required_arms)

    resample_indices = _stratified_resample_indices(
        task_ids=task_ids,
        task_types=contract.task_types,
        repetitions=contract.bootstrap_repetitions,
        seed=contract.bootstrap_seed,
    )
    primary = {
        _contrast_name(candidate, baseline): _contrast_analysis(
            per_task_scores,
            task_ids,
            candidate,
            baseline,
            contract,
            resample_indices=resample_indices,
            include_parity=True,
        )
        for candidate, baseline in contract.primary_contrasts
    }
    descriptive_candidate, descriptive_baseline = contract.descriptive_contrast
    descriptive_result = _contrast_analysis(
        per_task_scores,
        task_ids,
        descriptive_candidate,
        descriptive_baseline,
        contract,
        resample_indices=resample_indices,
        include_parity=False,
    )
    by_task_type = _stratified_analysis(per_task_scores, contract)

    return {
        "status": "complete",
        "analysis_plan_hash": contract.plan_hash,
        "task_manifest_hash": contract.manifest_hash,
        "method": {
            "bootstrap_repetitions": contract.bootstrap_repetitions,
            "bootstrap_seed": contract.bootstrap_seed,
            "bootstrap_unit": "paired_task",
            "bootstrap_sampling": "within_task_type_fixed_stratum_sizes",
            "prng": "sha256_counter_rejection_v1",
            "quantile_method": "linear_type_7",
            "interval": "percentile",
            "primary_confidence_level": contract.confidence_level,
            "parity_confidence_level": PARITY_CONFIDENCE_LEVEL,
            "multiplicity": "holm",
            "familywise_alpha": FAMILYWISE_ALPHA,
            "significance_testing": ("withheld_raw_p_value_estimator_not_frozen"),
        },
        "primary": dict(sorted(primary.items())),
        "descriptive_only": {
            "contrast": _contrast_name(
                descriptive_candidate,
                descriptive_baseline,
            ),
            "reason": contract.descriptive_reason,
            "confirmatory_claim_eligible": False,
            **descriptive_result,
        },
        "by_task_type": by_task_type,
    }


def _contrast_analysis(
    per_task_scores: Mapping[str, Mapping[str, float]],
    task_ids: tuple[str, ...],
    candidate: str,
    baseline: str,
    contract: AnalysisContract,
    *,
    resample_indices: tuple[tuple[int, ...], ...],
    include_parity: bool,
) -> dict[str, Any]:
    baseline_scores = tuple(
        float(per_task_scores[task_id][baseline]) for task_id in task_ids
    )
    candidate_scores = tuple(
        float(per_task_scores[task_id][candidate]) for task_id in task_ids
    )
    raw = _bootstrap_analysis(
        baseline_scores,
        candidate_scores,
        resample_indices=resample_indices,
        confidence_levels=(
            (contract.confidence_level, PARITY_CONFIDENCE_LEVEL)
            if include_parity
            else (contract.confidence_level,)
        ),
    )
    confidence_intervals = raw["confidence_intervals"]
    analysis = {
        "n_paired": len(task_ids),
        "mean_delta": _round_metric(raw["mean_delta"]),
        "confidence_interval_95": _rounded_interval(
            confidence_intervals[_level_key(contract.confidence_level)]
        ),
    }
    if include_parity:
        raw_parity_interval = confidence_intervals[_level_key(PARITY_CONFIDENCE_LEVEL)]
        analysis["parity"] = {
            "absolute_task_score_margin": contract.parity_margin,
            "confidence_interval_90": _rounded_interval(raw_parity_interval),
            "established": (
                raw_parity_interval["low"] >= -contract.parity_margin
                and raw_parity_interval["high"] <= contract.parity_margin
            ),
        }
    return analysis


def _stratified_analysis(
    per_task_scores: Mapping[str, Mapping[str, float]],
    contract: AnalysisContract,
) -> dict[str, Any]:
    task_types = sorted(set(contract.task_types.values()))
    return {
        task_type: _one_stratum(per_task_scores, contract, task_type)
        for task_type in task_types
    }


def _one_stratum(
    per_task_scores: Mapping[str, Mapping[str, float]],
    contract: AnalysisContract,
    task_type: str,
) -> dict[str, Any]:
    task_ids = tuple(
        sorted(
            task_id
            for task_id, declared_type in contract.task_types.items()
            if declared_type == task_type
        )
    )
    arms = sorted(
        {
            arm
            for candidate, baseline in contract.primary_contrasts
            for arm in (candidate, baseline)
        }
    )
    seed = _derived_seed(contract.bootstrap_seed, task_type)
    resample_indices = _flat_resample_indices(
        sample_size=len(task_ids),
        repetitions=contract.bootstrap_repetitions,
        seed=seed,
    )
    return {
        "n_tasks": len(task_ids),
        "by_arm": {
            arm: {
                "mean": _round_metric(
                    statistics.mean(
                        per_task_scores[task_id][arm] for task_id in task_ids
                    )
                )
            }
            for arm in arms
        },
        "contrasts": {
            _contrast_name(candidate, baseline): _contrast_analysis(
                per_task_scores,
                task_ids,
                candidate,
                baseline,
                contract,
                resample_indices=resample_indices,
                include_parity=False,
            )
            for candidate, baseline in contract.primary_contrasts
        },
    }


def _bootstrap_analysis(
    baseline_scores: tuple[float, ...],
    candidate_scores: tuple[float, ...],
    *,
    resample_indices: tuple[tuple[int, ...], ...],
    confidence_levels: tuple[float, ...],
) -> dict[str, Any]:
    deltas = tuple(
        candidate - baseline
        for baseline, candidate in zip(baseline_scores, candidate_scores)
    )
    observed = statistics.mean(deltas)
    bootstrap_means = tuple(
        statistics.mean(deltas[index] for index in replicate)
        for replicate in resample_indices
    )
    ordered = tuple(sorted(bootstrap_means))
    intervals = {
        _level_key(level): {
            "low": _percentile(ordered, (1 - level) / 2),
            "high": _percentile(ordered, 1 - (1 - level) / 2),
        }
        for level in confidence_levels
    }
    extreme = sum(
        1
        for estimate in bootstrap_means
        if abs(estimate - observed) >= abs(observed) - 1e-15
    )
    return {
        "mean_delta": observed,
        "confidence_intervals": intervals,
        "p_value_two_sided_centered_bootstrap": (
            (extreme + 1) / (len(bootstrap_means) + 1)
        ),
    }


def _flat_resample_indices(
    *,
    sample_size: int,
    repetitions: int,
    seed: int,
) -> tuple[tuple[int, ...], ...]:
    stream = _Sha256IndexStream(seed)
    return tuple(
        tuple(stream.next(sample_size) for _ in range(sample_size))
        for _ in range(repetitions)
    )


def _stratified_resample_indices(
    *,
    task_ids: tuple[str, ...],
    task_types: Mapping[str, str],
    repetitions: int,
    seed: int,
) -> tuple[tuple[int, ...], ...]:
    positions_by_type: dict[str, tuple[int, ...]] = {
        task_type: tuple(
            index
            for index, task_id in enumerate(task_ids)
            if task_types[task_id] == task_type
        )
        for task_type in sorted(set(task_types.values()))
    }
    if any(not positions for positions in positions_by_type.values()):
        raise CapsuleError("task manifest contains an empty task-type stratum")
    stream = _Sha256IndexStream(seed)
    return tuple(
        tuple(
            positions[stream.next(len(positions))]
            for positions in positions_by_type.values()
            for _ in positions
        )
        for _ in range(repetitions)
    )


class _Sha256IndexStream:
    """Version-stable unbiased index stream for reproducible resampling."""

    def __init__(self, seed: int) -> None:
        self._seed = str(seed).encode("ascii")
        self._counter = 0

    def next(self, upper_bound: int) -> int:
        if upper_bound < 1:
            raise CapsuleError("bootstrap stratum must not be empty")
        modulus = 1 << 64
        limit = modulus - (modulus % upper_bound)
        while True:
            digest = hashlib.sha256(
                b"enterprisebench-bootstrap-v1:"
                + self._seed
                + b":"
                + self._counter.to_bytes(16, "big")
            ).digest()
            self._counter += 1
            value = int.from_bytes(digest[:8], "big")
            if value < limit:
                return value % upper_bound


def _holm_adjust_raw(p_values: Mapping[str, float]) -> dict[str, float]:
    ranked = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    family_size = len(ranked)
    running_max = 0.0
    adjusted: dict[str, float] = {}
    for rank, (name, value) in enumerate(ranked):
        running_max = max(running_max, (family_size - rank) * value)
        adjusted[name] = min(1.0, running_max)
    return adjusted


def _rounded_interval(interval: Mapping[str, float]) -> dict[str, float]:
    return {
        "low": _round_metric(interval["low"]),
        "high": _round_metric(interval["high"]),
    }


def _validate_score_matrix(
    per_task_scores: Mapping[str, Mapping[str, float]],
    task_ids: tuple[str, ...],
    required_arms: set[str],
) -> None:
    for task_id in task_ids:
        row = per_task_scores[task_id]
        if not isinstance(row, Mapping) or not required_arms.issubset(row):
            raise CapsuleError("paired score matrix is missing a declared arm")
        _score_sample(
            [row[arm] for arm in sorted(required_arms)],
            "paired score matrix",
        )


def _score_sample(scores: Sequence[float], label: str) -> tuple[float, ...]:
    if not scores:
        raise CapsuleError(f"{label} score sample must not be empty")
    parsed = tuple(scores)
    if any(not _is_finite_number(score) or not 0 <= score <= 1 for score in parsed):
        raise CapsuleError(f"{label} scores must be finite numbers in [0, 1]")
    return tuple(float(score) for score in parsed)


def _percentile(ordered: tuple[float, ...], quantile: float) -> float:
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _derived_seed(seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{seed}:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _contrast_name(candidate: str, baseline: str) -> str:
    return f"{candidate}_vs_{baseline}"


def _level_key(level: float) -> str:
    return format(level, "g")


def _round_metric(value: float) -> float:
    return round(value, 8)


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )
