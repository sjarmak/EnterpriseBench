#!/usr/bin/env python3
"""Re-score the locked N=105 mcp_only transcripts for the 29 k4tv-affected
llm_curator tasks under the FIXED verifier (origin/main @94e0e0d) — EnterpriseBench-uu17.

READ-ONLY over the locked set; NO container, NO agent execution, NO SG token.

Method (mirrors the precedent scripts/analysis/reverify_masked.py, but for the
Tier-2 llm_curator cap that the k4tv/hmcp fix repaired):
  1. The locked mcp_only run's deterministic checkpoint `score`s already ARE the
     uncapped grep scores (the k4tv bug recorded grep un-capped because the judge
     never ran). The verifier fix did NOT change Tier-1 grep, so those scores
     remain valid under @94e0e0d.
  2. Reconstruct the agent's answer artifact from the captured agent_trace.jsonl
     Write tool-calls (the same bytes that were in-container), so the Tier-2
     judge can read it WITHOUT a live container.
  3. Call the EXACT fixed run_task._apply_llm_judge() (monkeypatching only the
     container `cat` with the reconstructed artifact) so the judge runs and
     min(grep, judge) caps are applied identically to how the 9awn baseline arm
     was scored under the same @94e0e0d code.

Output: results/rescore_uu17/<task>/mcp_only/results.json (rescored scores) +
a summary index. The locked set under results/runs/ is never modified.

Usage: python3 rescore_mcp_only_uu17.py [--task <name>] [--jobs N]
"""
from __future__ import annotations

import argparse
import json
import sys
import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

UU17 = Path(__file__).resolve().parent
MAIN = Path("/home/ds/projects/EnterpriseBench")
LOCKED_RUNS = MAIN / "results" / "runs"
AFFECTED = Path(
    "/home/ds/projects/EnterpriseBench-9awn/results/rerun_9awn/affected_tasklist.json"
)
OUT = UU17 / "results" / "rescore_uu17"

# Import the FIXED @94e0e0d scoring code from this worktree.
sys.path.insert(0, str(UU17 / "scripts" / "orchestration"))
sys.path.insert(0, str(UU17 / "lib"))
import run_task  # noqa: E402  (resolved from the uu17 worktree = @94e0e0d)


def _reconstruct_writes(trace_path: Path) -> dict[str, str]:
    """Return {container_file_path: last_written_content} from trace Write calls."""
    writes: dict[str, str] = {}
    if not trace_path.is_file():
        return writes
    with trace_path.open(errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or '"tool_use"' not in line or '"Write"' not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            def walk(node: object) -> None:
                if isinstance(node, dict):
                    if (
                        node.get("type") == "tool_use"
                        and node.get("name") == "Write"
                    ):
                        inp = node.get("input") or {}
                        fp = inp.get("file_path")
                        content = inp.get("content")
                        if isinstance(fp, str) and isinstance(content, str):
                            writes[fp] = content
                    for v in node.values():
                        walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)

            walk(obj)
    return writes


def _pick_artifact(candidates: list[str], writes: dict[str, str]) -> tuple[str, str]:
    """Pick the artifact the fixed verifier would read: first candidate present.

    Matches the in-container resolution order from _derive_artifact_candidates:
    exact path first, then basename fallback (the agent may write the same
    filename under a slightly different dir).
    """
    for cand in candidates:
        if cand in writes:
            return cand, writes[cand]
    for cand in candidates:
        base = cand.rsplit("/", 1)[-1]
        for fp, content in writes.items():
            if fp.rsplit("/", 1)[-1] == base:
                return cand, content
    return "", ""


def rescore_one(task: str, toml_rel: str) -> dict:
    """Re-score one mcp_only task under @94e0e0d. Returns a result record."""
    locked = LOCKED_RUNS / task / "mcp_only"
    results_fp = locked / "results.json"
    trace_fp = locked / "agent_trace.jsonl"
    task_dir = UU17 / Path(toml_rel).parent  # benchmarks/<suite>/<taskdir>

    old = json.loads(results_fp.read_text())
    old_scores = old.get("scores") or {}
    old_task_score = old_scores.get("task_score")

    # Fresh copy of the checkpoint grep scores for the judge to cap.
    scores = {
        "task_score": old_task_score,
        "checkpoints": [dict(cp) for cp in old_scores.get("checkpoints", [])],
        "all_passed": old_scores.get("all_passed"),
        "checkpoints_passed": old_scores.get("checkpoints_passed"),
        "checkpoints_total": old_scores.get("checkpoints_total"),
    }

    has_expected = (task_dir / "expected_solution.json").is_file()

    writes = _reconstruct_writes(trace_fp)
    candidates = run_task._derive_artifact_candidates(task_dir)
    art_path, art_content = _pick_artifact(candidates, writes)

    # Monkeypatch the container artifact read for THIS call only.
    def fake_docker_exec(container_id, cmd, timeout=120, workdir="/workspace"):
        if len(cmd) >= 2 and cmd[0] == "cat":
            path = cmd[1]
            if path == art_path and art_content:
                return types.SimpleNamespace(returncode=0, stdout=art_content, stderr="")
        return types.SimpleNamespace(returncode=1, stdout="", stderr="not found")

    orig = run_task._docker_exec
    run_task._docker_exec = fake_docker_exec
    try:
        task_data = run_task._parse_task(task_dir / "task.toml")
        new_scores = run_task._apply_llm_judge(scores, task_dir, "uu17-fake", task_data)
    finally:
        run_task._docker_exec = orig

    infra = new_scores.pop("verifier_infra_error", None)
    new_task_score = new_scores.get("task_score")

    moved = (
        old_task_score is not None
        and new_task_score is not None
        and abs(float(new_task_score) - float(old_task_score)) > 1e-9
    )
    rec = {
        "task": task,
        "old_mcp_score": old_task_score,
        "new_mcp_score": new_task_score,
        "moved": moved,
        "has_expected_solution": has_expected,
        "judged": any("judge_score" in cp for cp in new_scores.get("checkpoints", [])),
        "artifact_path": art_path,
        "n_writes": len(writes),
        "verifier_infra_error": infra,
        "checkpoints": [
            {
                "name": cp.get("name"),
                "score": cp.get("score"),
                "grep_score": cp.get("grep_score"),
                "judge_score": cp.get("judge_score"),
            }
            for cp in new_scores.get("checkpoints", [])
        ],
    }

    # Persist the rescored results.json (mirrors run dir layout).
    dst = OUT / task / "mcp_only"
    dst.mkdir(parents=True, exist_ok=True)
    out_doc = dict(old)
    out_doc["scores"] = new_scores
    out_doc["rescored_under"] = "origin/main@94e0e0d (EnterpriseBench-uu17)"
    if infra:
        out_doc["verifier_infra_error"] = infra
    (dst / "results.json").write_text(json.dumps(out_doc, indent=2))
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default=None, help="re-score a single task only")
    ap.add_argument("--jobs", type=int, default=4, help="parallel judge workers")
    args = ap.parse_args()

    affected = json.loads(AFFECTED.read_text())["tasks"]
    if args.task:
        affected = [t for t in affected if t["task"] == args.task]
        if not affected:
            sys.exit(f"task {args.task} not in affected list")

    OUT.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {
            ex.submit(rescore_one, t["task"], t["toml"]): t["task"] for t in affected
        }
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                rec = fut.result()
            except Exception as exc:  # surface, do not bury
                rec = {"task": name, "error": repr(exc)}
            results.append(rec)
            tag = "MOVED" if rec.get("moved") else ("err" if rec.get("error") else "same")
            print(
                f"[{tag:5}] {name:42} "
                f"old={rec.get('old_mcp_score')} -> new={rec.get('new_mcp_score')} "
                f"{'(judged)' if rec.get('judged') else ''} "
                f"{rec.get('error','')}"
            )

    results.sort(key=lambda r: r["task"])
    (OUT / "rescore_summary.json").write_text(json.dumps(results, indent=2))
    moved = [r for r in results if r.get("moved")]
    errs = [r for r in results if r.get("error") or r.get("verifier_infra_error")]
    print(f"\n{len(results)} tasks re-scored; {len(moved)} moved; {len(errs)} infra/err")
    print(f"summary -> {OUT / 'rescore_summary.json'}")


if __name__ == "__main__":
    main()
