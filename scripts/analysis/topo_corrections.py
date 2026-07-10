"""Apply the pt0n/lyse read-only topo_order corrections to headline inputs.

The docker-cp regression (bead hktt/pt0n, verifier fix 16280cf) silently zeroed
``topo_order`` for a handful of refactor-orch runs. ``rescore_topo_order_pt0n.py``
re-scored the preserved answers under the fixed verifier; the corrected
task_scores live in ``results/rescore_topo_order_pt0n/topo_corrections.json``.

These helpers apply those corrections to the in-memory median / 9awn-baseline
dicts each ``recompute_headline_*`` script builds, so the correction is explicit
and single-sourced while the published median/results artifacts keep their
original provenance (nothing on disk is mutated by these functions).
"""

from __future__ import annotations

import json
from pathlib import Path

_CORRECTIONS = (
    Path(__file__).resolve().parents[2]
    / "results" / "rescore_topo_order_pt0n" / "topo_corrections.json"
)


def load() -> dict:
    return json.loads(_CORRECTIONS.read_text())


def apply_median(median: dict, corrections: dict) -> list[str]:
    """Overwrite median/min/max/vals of each corrected task with the corrected
    scalar. Valid only because the topo_order fix is deterministic and constant
    across judge passes (asserted by the caller: all vals were identical).
    Returns the list of tasks actually applied (present in ``median``).
    """
    applied: list[str] = []
    for task, score in corrections.items():
        if task in median:
            median[task] = {
                **median[task],
                "median": score,
                "min": score,
                "max": score,
                "vals": [score] * len(median[task].get("vals", [score])),
                "topo_corrected": True,
            }
            applied.append(task)
    return applied


def apply_scalar(scalar: dict, corrections: dict) -> list[str]:
    """Overwrite a {task: task_score} dict (e.g. the 9awn re-run baseline) with
    the corrected task_scores. Returns the list of tasks applied."""
    applied: list[str] = []
    for task, score in corrections.items():
        scalar[task] = score
        applied.append(task)
    return applied
