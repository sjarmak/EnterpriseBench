#!/usr/bin/env python3
"""Symmetric MCP-vs-baseline headline recompute over the locked N=105 — aq8e.

uu17 closed the 9awn recompute with a MIXED method: the baseline arm was a fresh
9awn RE-RUN, the mcp_only arm a RE-SCORE. This script removes that asymmetry: it
re-scores the BASELINE arm the same way (aggregate_baseline_aq8e.py) and
recomputes the headline with BOTH arms re-scored under @94e0e0d.

It prints THREE headlines over the SAME locked-105 membership for a clean
side-by-side:
  1. OLD locked (p6ux.28).
  2. uu17 MIXED   : baseline = 9awn re-run, mcp = uu17 re-score (the accepted
     close; expected mean -0.1041 / median 0.0).
  3. aq8e SYMMETRIC: baseline = aq8e re-score (median), mcp = uu17 re-score.

The mcp arm is held fixed at uu17's accepted re-score so the ONLY change between
(2) and (3) is the baseline arm's re-run -> re-score swap, isolating the
verifier effect from baseline agent re-run noise.

gocp-module-007: under the RE-SCORE its locked baseline transcript is intact and
re-scorable, so (unlike the 9awn re-run, which hit verifier_infra_error) no
infra-fallback cell is needed. If any baseline re-score cell IS infra, it falls
back to the locked baseline value (never scored 0).

READ-ONLY. No re-runs, no token.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

MAIN = Path("/home/ds/projects/EnterpriseBench")
RERUN9 = Path("/home/ds/projects/EnterpriseBench-9awn/results/rerun_9awn")
AQ8E = Path(__file__).resolve().parent
BASE_MEDIAN = AQ8E / "results" / "rescore_aq8e" / "aggregated_median.json"
MCP_MEDIAN = AQ8E / "results" / "rescore_aq8e" / "mcp_only_uu17_median.json"

sys.path.insert(0, str(MAIN / "results" / "analysis"))
import os

os.chdir(MAIN)
import aggregate_mcp_clean as amc  # noqa: E402


def locked_clean() -> dict[str, tuple]:
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


def summarize(deltas: list[float]) -> dict:
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


def _fmt(v) -> str:
    return f"{v:.4f}" if isinstance(v, float) else str(v)


def main() -> None:
    clean = locked_clean()
    affected = json.loads((RERUN9 / "affected_tasklist.json").read_text())["tasks"]
    affected_names = {t["task"] for t in affected}
    base_median = json.loads(BASE_MEDIAN.read_text())
    mcp_median = json.loads(MCP_MEDIAN.read_text())

    # uu17's baseline arm = 9awn RE-RUN — only trust phase==complete & success.
    # An infra-error re-run (gocp-module-007) is NOT a measurement; fall back to
    # the locked baseline value (never score its 0.0).
    rerun_baseline: dict[str, float] = {}
    rerun_infra: list[str] = []
    for t in affected:
        fp = RERUN9 / t["task"] / "baseline" / "results.json"
        if fp.is_file():
            d = json.loads(fp.read_text())
            if d.get("phase") == "complete" and d.get("success") is True:
                rerun_baseline[t["task"]] = (d.get("scores") or {}).get("task_score")
            else:
                rerun_infra.append(t["task"])

    # aq8e baseline arm = RE-SCORE median. Infra cell -> locked fallback.
    rescore_infra: list[str] = [
        t for t, v in base_median.items() if v.get("infra") or v.get("median") is None
    ]

    old_deltas = [ms - bs for (bs, ms) in clean.values()]
    old = summarize(old_deltas)

    mixed_deltas, sym_deltas = [], []
    sym_resel_deltas = []  # variant A: re-apply baseline!=0 membership on symmetric
    band_promcp, band_antimcp = [], []  # symmetric judge-noise extremes
    moves = []
    dropped_baseline_dead = []
    base_fallback_used: list[str] = []
    for name, (bs, ms) in clean.items():
        # mcp arm (shared by mixed + symmetric): uu17 re-score median, else locked.
        nm = mcp_median[name]["median"] if name in affected_names and name in mcp_median else ms
        nm_max = mcp_median[name]["max"] if name in affected_names and name in mcp_median else ms
        nm_min = mcp_median[name]["min"] if name in affected_names and name in mcp_median else ms

        # mixed baseline (uu17): 9awn re-run, infra -> locked fallback.
        b_mixed = bs
        if name in affected_names and name in rerun_baseline and rerun_baseline[name] is not None:
            b_mixed = rerun_baseline[name]

        # symmetric baseline (aq8e): re-score median, infra -> locked fallback.
        b_sym = bs
        b_sym_min = b_sym_max = bs
        if name in affected_names and name in base_median and base_median[name].get("median") is not None:
            b_sym = base_median[name]["median"]
            b_sym_min = base_median[name]["min"]
            b_sym_max = base_median[name]["max"]
        elif name in affected_names and name in rescore_infra:
            base_fallback_used.append(name)

        mixed_deltas.append(nm - b_mixed)
        sym_deltas.append(nm - b_sym)
        # symmetric noise band: pro-MCP = mcp highest & baseline lowest; anti = inverse.
        band_promcp.append(nm_max - b_sym_min)
        band_antimcp.append(nm_min - b_sym_max)

        if b_sym == 0.0:
            dropped_baseline_dead.append(name)
        else:
            sym_resel_deltas.append(nm - b_sym)

        if name in affected_names and (abs(b_sym - bs) > 1e-9 or abs(nm - ms) > 1e-9 or abs(b_mixed - bs) > 1e-9):
            moves.append(
                {
                    "task": name,
                    "b_locked": bs,
                    "m_locked": ms,
                    "b_rerun_9awn": round(b_mixed, 4),
                    "b_rescore_aq8e": round(b_sym, 4),
                    "m_rescore_uu17": round(nm, 4),
                    "d_locked": round(ms - bs, 4),
                    "d_mixed_uu17": round(nm - b_mixed, 4),
                    "d_symmetric": round(nm - b_sym, 4),
                }
            )

    mixed = summarize(mixed_deltas)
    sym = summarize(sym_deltas)
    sym_resel = summarize(sym_resel_deltas)
    bmax = summarize(band_promcp)
    bmin = summarize(band_antimcp)

    n_aff = sum(1 for n in clean if n in affected_names)
    print(f"locked clean N = {len(clean)}  (affected-in-clean = {n_aff})")
    if rerun_infra:
        print(f"9awn baseline re-run infra (locked fallback): {rerun_infra}")
    print(f"aq8e baseline re-score infra (locked fallback): {rescore_infra or 'NONE'}")

    print("\n=== THREE HEADLINES over locked-105 (mcp - baseline) ===")
    print(f"  {'metric':10}{'OLD locked':>14}{'uu17 MIXED':>14}{'aq8e SYMMETRIC':>16}")
    for k in ("n", "mean", "median", "better", "tie", "worse"):
        print(f"  {k:10}{_fmt(old[k]):>14}{_fmt(mixed[k]):>14}{_fmt(sym[k]):>16}")

    print("\n=== affected-task moves ===")
    hdr = ("task", "b_lock", "m_lock", "b_rerun", "b_resc", "m_resc", "d_mix", "d_sym")
    print("  {:40}{:>7}{:>7}{:>8}{:>7}{:>7}{:>7}{:>7}".format(*hdr))
    for m in sorted(moves, key=lambda x: x["d_symmetric"]):
        print(
            "  {task:40}{b_locked:>7}{m_locked:>7}{b_rerun_9awn:>8}{b_rescore_aq8e:>7}"
            "{m_rescore_uu17:>7}{d_mixed_uu17:>7}{d_symmetric:>7}".format(**m)
        )

    print("\n=== conclusion check (does the parity verdict change?) ===")
    def direction(mean):
        return "MCP_worse" if mean < -1e-9 else ("MCP_better" if mean > 1e-9 else "parity")
    d_old, d_mixed, d_sym = direction(old["mean"]), direction(mixed["mean"]), direction(sym["mean"])
    print(f"  OLD locked     mean={old['mean']:.4f} median={old['median']:.4f} dir={d_old}")
    print(f"  uu17 MIXED     mean={mixed['mean']:.4f} median={mixed['median']:.4f} dir={d_mixed}")
    print(f"  aq8e SYMMETRIC mean={sym['mean']:.4f} median={sym['median']:.4f} dir={d_sym}")
    changed = d_sym != d_mixed
    print(f"  symmetric vs mixed: {'*** CONCLUSION CHANGED — ESCALATE ***' if changed else '(unchanged: no MCP win)'}")

    print("\n=== symmetric judge-noise band (both arms varied) ===")
    print(f"  pro-MCP extreme (mcp_max - base_min): mean={bmax['mean']:.4f} median={bmax['median']:.4f} b/t/w={bmax['better']}/{bmax['tie']}/{bmax['worse']}")
    print(f"  anti-MCP extreme (mcp_min - base_max): mean={bmin['mean']:.4f} median={bmin['median']:.4f} b/t/w={bmin['better']}/{bmin['tie']}/{bmin['worse']}")
    band_flips = bmax["mean"] > 1e-9
    print(f"  pro-MCP extreme flips to MCP win? {'YES — investigate' if band_flips else 'NO (no MCP win across full symmetric noise band)'}")

    print("\n=== variant A: re-applied membership (baseline==0 dropped) — symmetric ===")
    print(f"  dropped baseline-dead: {dropped_baseline_dead}")
    print(f"  N={sym_resel['n']} mean={sym_resel['mean']:.4f} median={sym_resel['median']:.4f} b/t/w={sym_resel['better']}/{sym_resel['tie']}/{sym_resel['worse']}")

    out = {
        "locked_clean_n": len(clean),
        "affected_in_clean": n_aff,
        "old_locked": old,
        "uu17_mixed": mixed,
        "aq8e_symmetric": sym,
        "symmetric_band_pro_mcp": bmax,
        "symmetric_band_anti_mcp": bmin,
        "symmetric_variant_A_reselected": sym_resel,
        "dropped_baseline_dead": dropped_baseline_dead,
        "baseline_rescore_infra_fallback": rescore_infra,
        "baseline_rerun_infra_fallback": rerun_infra,
        "conclusion_changed_vs_mixed": changed,
        "direction": {"old": d_old, "mixed": d_mixed, "symmetric": d_sym},
        "moves": moves,
    }
    (AQ8E / "results" / "rescore_aq8e" / "headline_recompute.json").write_text(
        json.dumps(out, indent=2)
    )
    print(f"\nwrote {AQ8E / 'results' / 'rescore_aq8e' / 'headline_recompute.json'}")


if __name__ == "__main__":
    main()
