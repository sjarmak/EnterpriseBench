"""Aggregate EB ``results/<run>/results.json`` files into quality_metrics.

Walks the per-run directories under a ``results/`` root, projects each
record through :func:`eb_metrics.trace_quality_adapter.metrics_from_eb_record`,
and feeds the rows to codeprobe's :class:`TraceQualityReporter` so the
output matches the shared ``quality_metrics`` schema (schema_version 1)
exactly.

This module owns no judgment calls beyond glob ordering and skipping
unreadable files; all signal logic lives in the adapter.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, Sequence

from codeprobe.analysis.trace_quality import (
    TraceQualityMetrics,
    TraceQualityReporter,
)

from eb_metrics.trace_quality_adapter import metrics_from_results_file

logger = logging.getLogger(__name__)

__all__ = [
    "build_quality_metrics",
    "iter_quality_metrics",
]


def iter_quality_metrics(
    runs_dir: Path,
    *,
    pattern: str = "*/results.json",
    benchmarks_dir: Path | None = None,
) -> Iterable[TraceQualityMetrics]:
    """Yield TraceQualityMetrics rows for every results.json under ``runs_dir``.

    ``pattern`` is glob-relative to ``runs_dir``. The default matches the
    canonical ``results/<run_name>/results.json`` layout. The parent
    directory name is used as ``run_name`` (config bucket).

    When ``benchmarks_dir`` is provided, retrieval-quality metrics are
    computed for single-record run dirs that have a sibling
    ``agent_trace.jsonl`` (see :func:`metrics_from_results_file`).
    """
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        raise FileNotFoundError(f"runs_dir not found: {runs_dir}")

    for results_path in sorted(runs_dir.glob(pattern)):
        if not results_path.is_file():
            continue
        try:
            yield from metrics_from_results_file(
                results_path, benchmarks_dir=benchmarks_dir
            )
        except (OSError, json.JSONDecodeError, ValueError) as err:
            logger.warning(
                "skipping %s while building quality_metrics: %s",
                results_path,
                err,
            )


def build_quality_metrics(
    runs_dir: Path,
    *,
    pattern: str = "*/results.json",
    experiment_warnings: Sequence[str] = (),
    benchmarks_dir: Path | None = None,
) -> dict[str, Any]:
    """Walk ``runs_dir`` and emit the codeprobe quality_metrics dict.

    Top-level keys match codeprobe's ``aggregate.json[quality_metrics]``
    block: ``schema_version``, ``overall``, ``per_config``,
    ``low_quality_trials``.

    ``experiment_warnings`` is an opt-in sequence of warning kinds
    (e.g. ``"no_independent_baseline"``) the caller wants surfaced on the
    overall summary; EB does not currently produce any, so the default
    is empty.

    ``benchmarks_dir`` opts into retrieval-quality metrics (recall/f1) by
    joining each run's ``agent_trace.jsonl`` with its task ground truth.
    """
    metrics = list(
        iter_quality_metrics(
            Path(runs_dir), pattern=pattern, benchmarks_dir=benchmarks_dir
        )
    )
    reporter = TraceQualityReporter.from_metrics(
        metrics, experiment_warnings=experiment_warnings
    )
    return reporter.to_dict()
