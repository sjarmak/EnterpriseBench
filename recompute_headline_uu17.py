#!/usr/bin/env python3
"""Recompute the locked N=105 MCP-vs-baseline headline after the k4tv re-score (uu17).

Combines:
  * locked clean N=105 selection + per-task scores (aggregate_mcp_clean.py, the
    generator of the p6ux.28 headline) — read from the MAIN worktree.
  * the 29 affected tasks' BASELINE arm re-run under @94e0e0d (9awn, given).
  * the 29 affected tasks' MCP_ONLY arm RE-SCORED under @94e0e0d (this bead),
    aggregated as the per-task MEDIAN across N judge passes (judge is noisy at
    the partial-credit boundary; median dampens it).

Prints OLD vs NEW headline (mean/median delta, better/tie/worse) over the SAME
locked 105 tasks, and the per-task moves for the affected set.

READ-ONLY. No re-runs, no token.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

MAIN = Path("/home/ds/projects/EnterpriseBench")
RERUN9 = Path("/home/ds/projects/EnterpriseBench-9awn/results/rerun_9awn")
UU17 = Path(__file__).resolve().parent
AGG_MEDIAN = UU17 / "results" / "rescore_uu17" / "aggregated_median.json"

# Build the locked clean set using the canonical generator.
sys.path.insert(0, str(MAIN / "results" / "analysis"))
import os

os.chdir(MAIN)
import aggregate_mcp_clean as amc  # noqa: E402


def locked_clean():
    """Return {task: (baseline_score, mcp_score)} for the locked clean N set."""
    tasks = {}
    for d in amc.task_dirs():
        rec = {m: amc.load_mode(d, m) for m in amc.MODES}
        tasks[d.name] = rec
    clean = {}
    for name, rec in tasks.items():
        if name in amc.DELETED:
            continue
        b, m = rec["baseline"], rec["mcp_only"]
        if not (b and b.get("present") and m and m.get("present")):
            continue
        if m["class"] in ("NO-OP", "INVALID") or b["class"] in ("NO-OP", "INVALID"):
            continue
        bs, ms = b["score"], m["score"]
        if bs is None or ms is None:
            continue
        if bs == 0.0:  # baseline_dead — excluded from clean headline (amc convention)
            continue
        clean[name] = (bs, ms)
    return clean


def summarize(deltas):
    better = sum(1 for d in deltas if d > 1e-9)
    worse = sum(1 for d in deltas if d < -1e-9)
    tie = sum(1 for d in deltas if abs(d) <= 1e-9)
    return {
        "n": len(deltas),
        "mean": statistics.mean(deltas) if deltas else None,
        "median": statistics.median(deltas) if deltas else None,
        "better": better,
        "tie": tie,
        "worse": worse,
    }


def main():
    clean = locked_clean()
    affected = json.loads((RERUN9 / "affected_tasklist.json").read_text())["tasks"]
    affected_names = {t["task"] for t in affected}
    median_agg = json.loads(AGG_MEDIAN.read_text())

    # Re-run baseline scores for affected tasks — ONLY trust phase==complete,
    # success runs. A verifier_infra_error re-run (e.g. gocp-module-007) is NOT
    # a measurement: its 0.0 must not be scored. For those we fall back to the
    # locked baseline value (no valid re-run replacement exists yet).
    rerun_baseline = {}
    baseline_infra = []
    for t in affected:
        fp = RERUN9 / t["task"] / "baseline" / "results.json"
        if fp.is_file():
            d = json.loads(fp.read_text())
            if d.get("phase") == "complete" and d.get("success") is True:
                rerun_baseline[t["task"]] = (d.get("scores") or {}).get("task_score")
            else:
                baseline_infra.append(t["task"])
    if baseline_infra:
        print(f"NOTE: baseline re-run NOT valid (infra-error, locked fallback): {baseline_infra}")

    # OLD headline over locked clean set.
    old_deltas = [ms - bs for (bs, ms) in clean.values()]
    old = summarize(old_deltas)

    # NEW headline: same task membership; override affected arms.
    # Three mcp_only aggregations to bound judge noise: median (point estimate),
    # max (most pro-MCP extreme), min (most anti-MCP extreme). Baseline is the
    # given 9awn re-run. If even the pro-MCP extreme does not flip to an MCP
    # win, the "no MCP win" conclusion is robust to the judge noise.
    new_deltas = []          # variant B: fixed-105 membership
    resel_deltas = []        # variant A: re-apply baseline!=0 membership
    band_max_deltas = []
    band_min_deltas = []
    moves = []
    dropped_baseline_dead = []
    for name, (bs, ms) in clean.items():
        nb = bs
        nm_med = nm_max = nm_min = ms
        if name in affected_names:
            if name in rerun_baseline and rerun_baseline[name] is not None:
                nb = rerun_baseline[name]
            if name in median_agg:
                nm_med = median_agg[name]["median"]
                nm_max = median_agg[name]["max"]
                nm_min = median_agg[name]["min"]
            if nb != bs or nm_med != ms:
                moves.append((name, bs, ms, nb, nm_med, (ms - bs), (nm_med - nb)))
        # Variant B: keep all 105 tasks.
        new_deltas.append(nm_med - nb)
        band_max_deltas.append(nm_max - nb)
        band_min_deltas.append(nm_min - nb)
        # Variant A: re-apply the locked clean-set rule (baseline==0 -> dead -> drop).
        if nb == 0.0:
            dropped_baseline_dead.append(name)
        else:
            resel_deltas.append(nm_med - nb)
    new = summarize(new_deltas)
    resel = summarize(resel_deltas)
    band_max = summarize(band_max_deltas)  # mcp at its highest judged score
    band_min = summarize(band_min_deltas)  # mcp at its lowest judged score

    n_aff_in_clean = sum(1 for n in clean if n in affected_names)
    print(f"locked clean N = {len(clean)}  (affected-in-clean = {n_aff_in_clean})")
    print("\n=== HEADLINE: OLD (locked) vs NEW (k4tv re-scored) ===")
    for k in ("n", "mean", "median", "better", "tie", "worse"):
        ov, nv = old[k], new[k]
        ovs = f"{ov:.4f}" if isinstance(ov, float) else str(ov)
        nvs = f"{nv:.4f}" if isinstance(nv, float) else str(nv)
        print(f"  {k:8} old={ovs:>10}   new={nvs:>10}")

    print("\n=== affected-task moves (locked -> re-scored) ===")
    print(f"  {'task':40} {'b_old':>6}{'m_old':>6} {'b_new':>6}{'m_new':>6} "
          f"{'d_old':>7}{'d_new':>7}")
    for (name, bo, mo, bn, mn, do, dn) in sorted(moves, key=lambda x: x[6] - x[5]):
        print(f"  {name:40} {bo:>6}{mo:>6} {bn:>6}{mn:>6} {do:>7.2f}{dn:>7.2f}")

    # Verdict signal: did the parity conclusion (mean ~ -0.093, median 0.0, no MCP win) change?
    print("\n=== conclusion check ===")
    print(f"  old: mean={old['mean']:.4f} median={old['median']:.4f} "
          f"better/tie/worse={old['better']}/{old['tie']}/{old['worse']}")
    print(f"  new: mean={new['mean']:.4f} median={new['median']:.4f} "
          f"better/tie/worse={new['better']}/{new['tie']}/{new['worse']}")
    sign_old = "MCP_worse" if old["mean"] < -1e-9 else ("MCP_better" if old["mean"] > 1e-9 else "parity")
    sign_new = "MCP_worse" if new["mean"] < -1e-9 else ("MCP_better" if new["mean"] > 1e-9 else "parity")
    print(f"  direction: old={sign_old}  new={sign_new}  "
          f"{'*** CONCLUSION CHANGED ***' if sign_old != sign_new else '(unchanged: no MCP win)'}")
    print("\n=== judge-noise sensitivity band (mcp_only extremes vs given baseline) ===")
    print(f"  mcp_MAX (most pro-MCP): mean={band_max['mean']:.4f} median={band_max['median']:.4f} "
          f"b/t/w={band_max['better']}/{band_max['tie']}/{band_max['worse']}")
    print(f"  mcp_MIN (most anti-MCP): mean={band_min['mean']:.4f} median={band_min['median']:.4f} "
          f"b/t/w={band_min['better']}/{band_min['tie']}/{band_min['worse']}")
    band_flips = band_max["mean"] > 1e-9
    print(f"  pro-MCP extreme flips to MCP win? {'YES — investigate' if band_flips else 'NO (no MCP win across full noise band)'}")
    print("\n=== variant A: re-applied membership (baseline==0 dropped per locked convention) ===")
    print(f"  dropped baseline-dead after re-run: {dropped_baseline_dead}")
    print(f"  N={resel['n']} mean={resel['mean']:.4f} median={resel['median']:.4f} "
          f"b/t/w={resel['better']}/{resel['tie']}/{resel['worse']}")

    out = {
        "locked_clean_n": len(clean),
        "affected_in_clean": n_aff_in_clean,
        "old": old,
        "new": new,
        "band_mcp_max": band_max,
        "band_mcp_min": band_min,
        "variant_A_reselected": resel,
        "dropped_baseline_dead": dropped_baseline_dead,
        "baseline_infra_fallback": baseline_infra,
        "moves": [
            {"task": m[0], "b_old": m[1], "m_old": m[2], "b_new": m[3],
             "m_new": m[4], "delta_old": m[5], "delta_new": m[6]}
            for m in moves
        ],
    }
    (UU17 / "results" / "rescore_uu17" / "headline_recompute.json").write_text(
        json.dumps(out, indent=2)
    )


if __name__ == "__main__":
    main()
