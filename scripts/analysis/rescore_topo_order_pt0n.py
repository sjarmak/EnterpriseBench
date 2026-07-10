#!/usr/bin/env python3
"""Read-only topo_order rescore of the 5 docker-cp-contaminated pairs (pt0n/lyse).

The docker-cp package-drop regression (bead hktt/pt0n, fixed on main @16280cf)
made ``check_topo_order.sh``'s ``from eb_verify.plugins.topological_order import
...`` fail with ModuleNotFoundError; test_runner recorded a silent ``topo_order``
0.0 (exit_code=1) with no infra flag. The agents' answers were fine — only the
verifier crashed — so the correct fix is to RE-SCORE the preserved answer under
the fixed verifier, not to re-run the agent.

Method (identical spirit to rescore_baseline_aq8e / rescore_mcp_only_uu17):
reconstruct ``REFACTOR_PLAN.md`` from the locked ``agent_trace.jsonl`` Write
calls, score it with the current (fixed) ``validate_refactor_plan_markdown``
against the task's ``ground_truth.json[dependency_graph]``, and recompute the
task_score (raw weighted sum) with the corrected ``topo_order`` checkpoint.

READ-ONLY over the locked set: NO container, NO agent execution, NO SG token,
NO API key. results/runs/ is never modified.

Usage: python3 scripts/analysis/rescore_topo_order_pt0n.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from eb_verify.plugins.topological_order import validate_refactor_plan_markdown  # noqa: E402

LOCKED_RUNS = REPO_ROOT / "results" / "runs"
BENCH = REPO_ROOT / "benchmarks" / "technical_debt"

# The 5 contaminated (task, mode) pairs + the lyse pair (owner = which rescore
# headline they feed), plus the two tasks a full-locked-set completeness scan
# (topo_order exit_code=1) surfaced beyond the handoff scope: tri-babel-001 and
# tri-tokio-001, both contaminated in BOTH arms. Both arms lift by +1.0 there, so
# the MCP-vs-baseline delta is unchanged and the headline is unaffected — they
# are rescored here for completeness/auditability, not because they move a number.
PAIRS = [
    {"task": "refactor-orch-004", "mode": "baseline", "owner": "aq8e"},
    {"task": "refactor-orch-007", "mode": "baseline", "owner": "aq8e"},
    {"task": "refactor-orch-001", "mode": "mcp_only", "owner": "uu17"},
    {"task": "refactor-orch-007", "mode": "mcp_only", "owner": "uu17"},
    {"task": "refactor-orch-008", "mode": "mcp_only", "owner": "uu17"},
    {"task": "refactor-orch-006", "mode": "mcp_only", "owner": "lyse"},
    {"task": "refactor-orchestration-tri-babel-001", "mode": "baseline", "owner": "completeness"},
    {"task": "refactor-orchestration-tri-babel-001", "mode": "mcp_only", "owner": "completeness"},
    {"task": "refactor-orchestration-tri-tokio-001", "mode": "baseline", "owner": "completeness"},
    {"task": "refactor-orchestration-tri-tokio-001", "mode": "mcp_only", "owner": "completeness"},
]


def _task_dir(task_id: str) -> Path:
    """Task-definition dir. Handles both the short results id (refactor-orch-004
    -> refactor-orchestration-004) and the full-name tri-* ids."""
    if (BENCH / task_id).is_dir():
        return BENCH / task_id
    return BENCH / f"refactor-orchestration-{task_id.rsplit('-', 1)[-1]}"


def _reconstruct_writes(trace_path: Path) -> dict[str, str]:
    """Return {container_file_path: last_written_content} from trace Write calls."""
    writes: dict[str, str] = {}
    for line in trace_path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or '"tool_use"' not in line or '"Write"' not in line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = entry.get("message", entry)
        content = msg.get("content", []) if isinstance(msg, dict) else []
        for node in content if isinstance(content, list) else []:
            if not isinstance(node, dict):
                continue
            if node.get("type") == "tool_use" and node.get("name") == "Write":
                inp = node.get("input", {}) or {}
                fp = inp.get("file_path")
                body = inp.get("content")
                if isinstance(fp, str) and isinstance(body, str):
                    writes[fp] = body
    return writes


def _pick_refactor_plan(writes: dict[str, str]) -> str | None:
    """Last Write whose basename is REFACTOR_PLAN.md (what the checker reads)."""
    chosen: str | None = None
    for fp, body in writes.items():
        if Path(fp).name == "REFACTOR_PLAN.md":
            chosen = body  # dict preserves insertion order -> last write wins
    return chosen


def _resolve_run_dir(task_id: str, mode: str) -> Path | None:
    """Flat ``<task>/<mode>/`` layout, else the max-scoring ``rep*`` subdir."""
    base = LOCKED_RUNS / task_id / mode
    if (base / "agent_trace.jsonl").is_file():
        return base
    reps = sorted(base.glob("rep*"))
    reps = [r for r in reps if (r / "agent_trace.jsonl").is_file()]
    if not reps:
        return None
    # Pick the rep whose results.json task_score is the locked (max) score.
    best, best_score = None, -1.0
    for r in reps:
        rj = r / "results.json"
        if rj.is_file():
            sc = json.loads(rj.read_text()).get("scores", {}).get("task_score", -1.0)
            if isinstance(sc, (int, float)) and sc > best_score:
                best, best_score = r, float(sc)
    return best or reps[0]


def _rescore_pair(task_id: str, mode: str) -> dict:
    run_dir = _resolve_run_dir(task_id, mode)
    if run_dir is None:
        return {"error": "no locked run dir / trace"}

    results = json.loads((run_dir / "results.json").read_text())
    scores = results.get("scores", {})
    checkpoints = scores.get("checkpoints", [])
    topo_cp = next((c for c in checkpoints if c.get("name") == "topo_order"), None)
    if topo_cp is None:
        return {"error": "no topo_order checkpoint in locked results"}

    gt_path = _task_dir(task_id) / "ground_truth.json"
    dep_graph = json.loads(gt_path.read_text()).get("dependency_graph", {})

    writes = _reconstruct_writes(run_dir / "agent_trace.jsonl")
    plan = _pick_refactor_plan(writes)
    if plan is None:
        # Agent never wrote REFACTOR_PLAN.md — the 0.0 is a genuine miss, not
        # docker-cp contamination. Report it distinctly, don't fabricate a lift.
        return {
            "error": "no REFACTOR_PLAN.md write in trace (genuine 0, not contamination)",
            "contaminated_topo": topo_cp.get("score"),
            "topo_exit_code": topo_cp.get("exit_code"),
        }

    corrected = validate_refactor_plan_markdown(plan, dep_graph)
    corrected_topo = round(float(corrected["score"]), 4)
    old_topo = float(topo_cp.get("score", 0.0))
    topo_weight = float(topo_cp.get("weight", 1.0))

    old_task = float(scores.get("task_score", 0.0))
    new_task = round(old_task - old_topo * topo_weight + corrected_topo * topo_weight, 4)

    return {
        "run_dir": str(run_dir.relative_to(REPO_ROOT)),
        "contaminated_topo": old_topo,
        "topo_exit_code": topo_cp.get("exit_code"),
        "corrected_topo": corrected_topo,
        "corrected_topo_detail": corrected["detail"],
        "topo_weight": topo_weight,
        "old_task_score": old_task,
        "new_task_score": new_task,
        "delta_task_score": round(new_task - old_task, 4),
        "other_checkpoints": {
            c.get("name"): c.get("score")
            for c in checkpoints if c.get("name") != "topo_order"
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=None, help="Write summary JSON here (default: stdout).")
    args = parser.parse_args(argv)

    summary = {"method": "read_only_topo_rescore", "pairs": []}
    for spec in PAIRS:
        result = _rescore_pair(spec["task"], spec["mode"])
        summary["pairs"].append({**spec, **result})

    # Human table to stderr.
    print(f"{'task':<20}{'mode':<10}{'owner':<7}{'old_topo':>9}{'new_topo':>9}"
          f"{'old_task':>10}{'new_task':>10}", file=sys.stderr)
    for p in summary["pairs"]:
        if "error" in p and "corrected_topo" not in p:
            print(f"{p['task']:<20}{p['mode']:<10}{p['owner']:<7}  ERROR: {p['error']}", file=sys.stderr)
            continue
        print(f"{p['task']:<20}{p['mode']:<10}{p['owner']:<7}"
              f"{p.get('contaminated_topo',0):>9}{p.get('corrected_topo',0):>9}"
              f"{p.get('old_task_score',0):>10}{p.get('new_task_score',0):>10}", file=sys.stderr)

    text = json.dumps(summary, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(f"\nsummary written to {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
