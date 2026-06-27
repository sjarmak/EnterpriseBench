#!/usr/bin/env python3
"""Run the baseline re-score over N independent judge passes and aggregate by
per-task median (+min/max/vals) — EnterpriseBench-aq8e.

Mirrors uu17's 7-pass median methodology exactly (the cc:haiku Tier-2 judge is
noisy at the partial-credit boundary; a single pass is not defensible). Produces
results/rescore_aq8e/aggregated_median.json in the SAME schema uu17 emitted, so
the symmetric headline recompute can consume both arms identically.

Usage: python3 aggregate_baseline_aq8e.py [--passes 7] [--jobs 4]
"""
from __future__ import annotations

import argparse
import json
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import rescore_baseline_aq8e as rb

OUT = rb.OUT
AGG = OUT / "aggregated_median.json"


def run_pass(affected: list[dict], jobs: int) -> dict[str, dict]:
    """One full re-score pass. Returns {task: record}."""
    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {
            ex.submit(rb.rescore_one, t["task"], t["toml"]): t["task"] for t in affected
        }
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                out[name] = fut.result()
            except Exception as exc:  # surface, do not bury
                out[name] = {"task": name, "error": repr(exc)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", type=int, default=7)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()

    affected = json.loads(rb.AFFECTED.read_text())["tasks"]
    OUT.mkdir(parents=True, exist_ok=True)

    # task -> list of per-pass task_scores (None entries = infra/err passes)
    series: dict[str, list] = {t["task"]: [] for t in affected}
    infra: dict[str, object] = {}
    for p in range(args.passes):
        recs = run_pass(affected, args.jobs)
        for task, rec in recs.items():
            score = rec.get("new_baseline_score")
            if rec.get("verifier_infra_error"):
                infra[task] = rec["verifier_infra_error"]
            series[task].append(score)
        moved = sum(1 for r in recs.values() if r.get("moved"))
        print(f"pass {p + 1}/{args.passes}: {moved} moved")

    agg: dict[str, dict] = {}
    for task, vals in series.items():
        clean = [float(v) for v in vals if isinstance(v, (int, float))]
        if not clean:
            agg[task] = {
                "median": None,
                "min": None,
                "max": None,
                "vals": vals,
                "infra": True,
            }
            continue
        agg[task] = {
            "median": statistics.median(clean),
            "min": min(clean),
            "max": max(clean),
            "vals": vals,
        }
        if task in infra:
            agg[task]["infra"] = True

    AGG.write_text(json.dumps(agg, indent=2))
    unstable = {t: v for t, v in agg.items() if v["min"] != v["max"]}
    print(f"\naggregated {len(agg)} tasks over {args.passes} passes -> {AGG}")
    print(f"unstable (min != max across passes): {len(unstable)}")
    for t, v in sorted(unstable.items()):
        print(f"  {t:42} median={v['median']} band=[{v['min']},{v['max']}]")
    if infra:
        print(f"infra/no-judge cells: {sorted(infra)}")


if __name__ == "__main__":
    main()
