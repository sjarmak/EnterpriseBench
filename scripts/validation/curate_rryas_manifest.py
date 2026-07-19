#!/usr/bin/env python3
"""Curate the rryas 3-arm headline dataset: eligible pool, exclusions, candidate manifest.

Reproduces selection from ``results/rryas_dataset/gate_analysis.json`` (produced by
``curated_gate_analyzer.py``) plus the 2026-07-19 hard-exclusion directive on
EnterpriseBench-rryas.8: drop any task affected by the open verifier/reward-integrity
findings (EnterpriseBench-639lv / mgodn / ozbjt / v9okc) unless the defect is fixed
AND independently verified; prefer exclusion over delaying the study.

Two exclusion layers (the class scan is load-bearing — gate3 alone does NOT discharge
ozbjt or v9okc, only mgodn):

  * name-set: tasks explicitly named by an open finding, snapshotted here for the
    record.
  * per-vector class scan: any all_pass task whose checks emit a hardcoded full-credit
    score inside an absent/empty ground-truth branch (ozbjt "freebie": e.g.
    dead-code-003/check_feature_flags.sh returns score 1.0 when the GT collection is
    empty) or grep a patch/diff (v9okc patch-grep). gate3 (own-``instruction.md`` echo
    == 0) proves same-prompt echo resistance only; it does not see the freebie branch
    (it errors to inconclusive on a non-JSON echo) nor the patch-grep vector.

The closed-book / foreign-prompt residual of ozbjt (a task answerable from world
knowledge without reading the repo) is NOT structurally detectable and is deferred to
the empirical mini 3-arm pilot's "baseline does not trivially win" criterion — recorded
as a limitation, not silently discharged.

Design choices (see the architect review folded into MANIFEST.md):
  * verified-clean tasks are NEVER pre-deleted to flatten a type histogram. Type skew
    (dependency_graph is the largest surviving type) is handled at analysis time via
    stratified per-type reporting, not by dropping signal. So candidate_manifest.json
    is the full survivor set, not an arbitrarily balanced ~35.
  * "candidate", never "final": arm separation is unproven until the pilot runs, and a
    non-trivial fraction of structurally-clean tasks are expected to fail it (the
    calibration-001 lesson: 41 turns, 0 sgx calls, gated infra_sgx_unused).

Usage:
    python3 scripts/validation/curate_rryas_manifest.py            # writes artifacts
    python3 scripts/validation/curate_rryas_manifest.py --check    # exit 1 on drift
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH = REPO_ROOT / "benchmarks"
OUT_DIR = REPO_ROOT / "results" / "rryas_dataset"
GATE_ANALYSIS = OUT_DIR / "gate_analysis.json"

# Open verifier/reward-integrity findings the 2026-07-19 directive excludes.
FINDING_BEADS = ["EnterpriseBench-639lv", "EnterpriseBench-mgodn",
                 "EnterpriseBench-ozbjt", "EnterpriseBench-v9okc"]
BD_TIMEOUT = 60  # seconds for a `bd show`

# A check emits a hardcoded full-credit score, as a JSON literal, a shell/python
# assignment, or a named full-credit constant. `1`, `1.0`, `1.00` all count.
_FULL_CREDIT_RE = re.compile(
    r'"score"\s*:\s*1(?:\.0+)?\b'
    r'|(?:score|full_credit|FULL_CREDIT)\s*=\s*1(?:\.0+)?\b',
    re.I,
)
# ...and does so guarded by an absence/emptiness test on ground truth (ozbjt freebie).
_ABSENCE_HINT_RE = re.compile(r"\bnot\b|\bempty\b|\bno\b|==\s*0|len\(|\.get\(|absent|missing",
                              re.I)
# Proximity window (chars) between the full-credit emission and the absence hint.
# LIMITATION (documented, like the closed-book residual): this is a proximity +
# literal-value heuristic, not an AST/block analysis. A guard set >_FREEBIE_WINDOW
# chars from the credit line, or full credit reached through multi-hop variable
# indirection, can evade it. 0/48 eligible tasks trip either mode today; the invariant
# test re-runs this scan so a regression that lands a freebie in a manifest task's
# checks fails CI, but a novel evasion shape would need the detector widened.
_FREEBIE_WINDOW = 600
# v9okc: scoring by grepping a patch/diff.
_PATCH_RE = re.compile(r"\bgit\s+(diff|apply)\b|\.patch\b|\.diff\b|\bdiff\b.*grep", re.I)


def task_dir(task_id: str) -> Path | None:
    hits = [os.path.dirname(t) for t in glob.glob(str(BENCH / "*" / task_id / "task.toml"))]
    return Path(hits[0]) if hits else None


def freebie_checks(tdir: Path) -> list[str]:
    """Check basenames that emit full credit inside an absence/empty GT branch (ozbjt)."""
    hits = []
    for chk in sorted(glob.glob(str(tdir / "checks" / "*.sh"))):
        txt = Path(chk).read_text(errors="replace")
        for m in _FULL_CREDIT_RE.finditer(txt):
            window = txt[max(0, m.start() - _FREEBIE_WINDOW):m.end() + 40]
            if _ABSENCE_HINT_RE.search(window):
                hits.append(os.path.basename(chk))
                break
    return hits


def patch_checks(tdir: Path) -> list[str]:
    """Check basenames that score by grepping a patch/diff (v9okc)."""
    return [
        os.path.basename(chk)
        for chk in sorted(glob.glob(str(tdir / "checks" / "*.sh")))
        if _PATCH_RE.search(Path(chk).read_text(errors="replace"))
    ]


def real_task_ids() -> set[str]:
    return {
        os.path.basename(os.path.dirname(t))
        for t in glob.glob(str(BENCH / "*" / "*" / "task.toml"))
        if "_archived" not in t and "mined" not in t
    }


class FindingLookupError(RuntimeError):
    """`bd` could not be queried for an integrity finding — fail loud, never silently
    treat an infra outage as 'no task is named' (that would make the name-set
    exclusion layer, and its guard test, vacuous)."""


def finding_named_sets() -> dict[str, list[str]]:
    """Real task-ids named by each open finding, via ``bd show``.

    Raises FindingLookupError if ``bd`` is missing, times out, exits nonzero, or
    returns empty output for a finding that must exist. An absent signal is NOT an
    absence of finding — surfacing it is required by the same scorer-guard doctrine
    the module relies on (a verdict is valid only if the pristine query actually ran).
    """
    reals = real_task_ids()
    named: dict[str, list[str]] = {}
    for bead in FINDING_BEADS:
        try:
            proc = subprocess.run(["bd", "show", bead], capture_output=True,
                                  text=True, timeout=BD_TIMEOUT)
        except (FileNotFoundError, subprocess.SubprocessError) as e:
            raise FindingLookupError(f"`bd show {bead}` failed: {e}") from e
        if proc.returncode != 0 or not proc.stdout.strip():
            raise FindingLookupError(
                f"`bd show {bead}` returned rc={proc.returncode} / empty output; "
                f"refusing to treat a bd outage as 'no task named' — {proc.stderr.strip()[:200]}"
            )
        named[bead] = sorted(t for t in reals if t in proc.stdout)
    return named


def _is_json_deliverable(deliverables: list[str]) -> bool:
    return any(d.endswith(".json") for d in deliverables)


def curate() -> dict:
    # A plain exception (not SystemExit) so importers — the invariant test calls
    # curate() directly — get a catchable error, not a BaseException.
    if not GATE_ANALYSIS.exists():
        raise FileNotFoundError(
            f"missing {GATE_ANALYSIS}; run curated_gate_analyzer.py --json first")
    pool = json.loads(GATE_ANALYSIS.read_text(encoding="utf-8"))
    named = finding_named_sets()
    named_union = set().union(*named.values())

    eligible, exclusions = [], []
    for t in pool:
        tid = t["task_id"]
        tdir = task_dir(tid)
        rec = {
            "task_id": tid, "suite": t["suite"], "stratum": t["stratum"],
            "task_type": t["task_type"], "repos": t["repos"],
            "deliverables": t["deliverables"],
        }
        # Non-all_pass tasks are excluded by the structural gates first.
        if not t["all_pass"]:
            if _is_json_deliverable(t["deliverables"]):
                reason = "639lv-class: JSON deliverable, no JSON-shaped echo vector — certified-clean-without-exercise"
            elif t["gate2_suspects"]:
                reason = f"gate2: non-indexed ground-truth files {t['gate2_suspects']}"
            elif t["gate3_pass"] is False:
                reason = "gate3: prompt-echo leak (mgodn-class)"
            elif t["gate3_pass"] is None:
                reason = "gate3-inconclusive: deliverable not md-grep-testable"
            elif t["gate4_pass"] is False:
                reason = "gate4: expected_solution does not pass its own checks"
            else:
                reason = f"gate4-inconclusive: {t['gate4_note'] or 'no expected_solution.json'}"
            exclusions.append({**rec, "excluded": True, "reason": reason})
            continue
        # all_pass: apply name-set + per-vector class exclusions (C1).
        # Fail CLOSED if the task dir vanished — never let an all_pass task skip the
        # load-bearing class scan and fall through to eligible unexamined.
        if tdir is None:
            exclusions.append({**rec, "excluded": True,
                               "reason": "tdir-not-found: freebie/patch class scan could not run (fail-closed)"})
            continue
        fb = freebie_checks(tdir)
        pc = patch_checks(tdir)
        if tid in named_union:
            owners = [b for b, ids in named.items() if tid in ids]
            exclusions.append({**rec, "excluded": True,
                               "reason": f"named by open finding(s) {owners}"})
        elif fb:
            exclusions.append({**rec, "excluded": True,
                               "reason": f"ozbjt-class freebie (full credit on absent GT) in {fb}"})
        elif pc:
            exclusions.append({**rec, "excluded": True,
                               "reason": f"v9okc-class patch-grep scoring in {pc}"})
        else:
            eligible.append(rec)

    return {"pool_size": len(pool), "named": named,
            "eligible": eligible, "exclusions": exclusions}


def _dist(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _dump(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def write_artifacts(result: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    eligible = result["eligible"]
    by_type = _dist(eligible, "task_type")
    by_stratum = _dist(eligible, "stratum")

    _dump(OUT_DIR / "eligible_pool.json", {
        "count": len(eligible),
        "by_type": by_type,
        "by_stratum": by_stratum,
        "tasks": sorted(eligible, key=lambda r: (r["task_type"], r["task_id"])),
    })
    _dump(OUT_DIR / "exclusions.json", {
        "count": len(result["exclusions"]),
        "finding_named_snapshot": result["named"],
        "tasks": sorted(result["exclusions"], key=lambda r: (r["reason"], r["task_id"])),
    })
    # The candidate manifest IS the full eligible survivor set (no type pre-capping).
    _dump(OUT_DIR / "candidate_manifest.json", {
        "status": "CANDIDATE — arm separation unproven; empirical 3-arm pilot + PL sign-off gate the final lock",
        "count": len(eligible),
        "by_type": by_type,
        "by_stratum": by_stratum,
        "note": "verified-clean tasks are NOT pre-deleted for balance; dependency_graph skew "
                "is handled by stratified per-type analysis. Candidates != final trials "
                "(calibration-001-class pilot attrition expected).",
        "task_ids": sorted(r["task_id"] for r in eligible),
    })


def _drift(result: dict) -> list[str]:
    """Committed artifacts vs a fresh curate() — id sets AND exclusion reason map."""
    stale: list[str] = []
    fresh_eligible = {r["task_id"] for r in result["eligible"]}
    fresh_excl = {r["task_id"]: r["reason"] for r in result["exclusions"]}
    checks: list[tuple[str, set | dict]] = [
        ("eligible_pool.json", fresh_eligible),
        ("candidate_manifest.json", fresh_eligible),
        ("exclusions.json", fresh_excl),
    ]
    for name, fresh in checks:
        path = OUT_DIR / name
        if not path.exists():
            stale.append(f"{name} missing")
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if name == "exclusions.json":
            committed: set | dict = {t["task_id"]: t["reason"] for t in doc["tasks"]}
        elif "task_ids" in doc:
            committed = set(doc["task_ids"])
        else:
            committed = {t["task_id"] for t in doc.get("tasks", [])}
        if committed != fresh:
            stale.append(f"{name}: committed != fresh (re-run curate_rryas_manifest.py)")
    return stale


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if regenerated artifacts differ from committed ones")
    args = ap.parse_args()
    try:
        result = curate()
    except (FileNotFoundError, FindingLookupError) as e:
        print(f"ERROR: {e}")
        return 2
    if args.check:
        stale = _drift(result)
        if stale:
            print("STALE:\n  " + "\n  ".join(stale))
            return 1
        print(f"OK: {len(result['eligible'])} eligible, {len(result['exclusions'])} excluded — in sync")
        return 0
    write_artifacts(result)
    print(f"eligible={len(result['eligible'])} excluded={len(result['exclusions'])} "
          f"-> {OUT_DIR}/{{eligible_pool,exclusions,candidate_manifest}}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
