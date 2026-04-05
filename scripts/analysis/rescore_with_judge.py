#!/usr/bin/env python3
"""Re-score existing ablation results using the LLM judge.

Reads agent output from results/runs/<task_id>/<variant>/rep<N>/
and evaluates each checkpoint against expected_solution.json using
the LLM judge. Compares grep-based vs LLM-judged scores.

Usage:
    python scripts/analysis/rescore_with_judge.py \
        --task-dir benchmarks/incident_response/incident-investigation-004 \
        --results-dir results/runs/incident-inv-docker-shutdown-004 \
        --variants baseline,ablate-moby,ablate-containerd \
        --model cc:haiku
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from eb_verify.judge import CheckpointJudgeInput, LLMJudge


def load_expected_solution(task_dir: Path) -> dict:
    """Load expected_solution.json from task directory."""
    path = task_dir / "expected_solution.json"
    if not path.exists():
        raise FileNotFoundError(f"No expected_solution.json in {task_dir}")
    return json.loads(path.read_text())


def load_agent_output(rep_dir: Path) -> str:
    """Load agent output from a rep directory.

    Checks for answer.json (support-mapping tasks) or
    INCIDENT_REPORT.md (incident tasks) inside the agent trace.
    """
    # Try extracting answer.json from agent stdout log
    stdout_log = rep_dir / "agent" / "stdout.log"
    if stdout_log.exists():
        for line in stdout_log.read_text().splitlines():
            try:
                msg = json.loads(line)
                if msg.get("type") == "assistant":
                    for block in msg.get("message", {}).get("content", []):
                        if (
                            block.get("type") == "tool_use"
                            and block.get("name") == "Write"
                        ):
                            inp = block.get("input", {})
                            fpath = inp.get("file_path", "")
                            if "answer.json" in fpath or "INCIDENT_REPORT" in fpath:
                                return inp.get("content", "")
            except (json.JSONDecodeError, KeyError):
                continue

    # Fallback: look for agent_stdout.log at rep level
    alt_log = rep_dir / "agent_stdout.log"
    if alt_log.exists():
        for line in alt_log.read_text().splitlines():
            try:
                msg = json.loads(line)
                if msg.get("type") == "assistant":
                    for block in msg.get("message", {}).get("content", []):
                        if (
                            block.get("type") == "tool_use"
                            and block.get("name") == "Write"
                        ):
                            inp = block.get("input", {})
                            fpath = inp.get("file_path", "")
                            if "answer.json" in fpath or "INCIDENT_REPORT" in fpath:
                                return inp.get("content", "")
            except (json.JSONDecodeError, KeyError):
                continue

    return ""


def load_grep_scores(rep_dir: Path) -> dict[str, float]:
    """Load grep-based checkpoint scores from results.json."""
    results_path = rep_dir / "results.json"
    if not results_path.exists():
        return {}
    data = json.loads(results_path.read_text())
    scores = {}
    for cp in data.get("scores", {}).get("checkpoints", []):
        scores[cp["name"]] = cp["score"]
    return scores


def load_task_description(task_dir: Path) -> str:
    """Load task description from instruction.md or task.toml."""
    instruction = task_dir / "instruction.md"
    if instruction.exists():
        return instruction.read_text()[:2000]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-score with LLM judge")
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument(
        "--variants", type=str, required=True, help="Comma-separated variant names"
    )
    parser.add_argument("--model", type=str, default="cc:haiku")
    parser.add_argument("--reps", type=int, default=3)
    args = parser.parse_args()

    expected = load_expected_solution(args.task_dir)
    task_desc = load_task_description(args.task_dir)
    judge = LLMJudge(model=args.model)

    variants = [v.strip() for v in args.variants.split(",")]

    print(f"Task: {expected['task_id']}")
    print(f"Judge model: {args.model}")
    print(f"Checkpoints: {list(expected['checkpoints'].keys())}")
    print()

    for variant in variants:
        print(f"=== {variant} ===")
        for rep in range(1, args.reps + 1):
            rep_dir = args.results_dir / variant / f"rep{rep}"
            if not rep_dir.exists():
                print(f"  rep{rep}: (not found)")
                continue

            agent_output = load_agent_output(rep_dir)
            if not agent_output:
                print(f"  rep{rep}: (no agent output found)")
                continue

            grep_scores = load_grep_scores(rep_dir)

            judge_scores: dict[str, float] = {}
            for cp_name, cp_data in expected["checkpoints"].items():
                result = judge.evaluate_checkpoint(
                    CheckpointJudgeInput(
                        task_id=expected["task_id"],
                        checkpoint_name=cp_name,
                        agent_output=agent_output,
                        expected_solution=cp_data["expected_solution"],
                        evaluation_criteria=cp_data.get("evaluation_criteria", []),
                    ),
                    task_description=task_desc,
                    checkpoint_description=cp_data.get("expected_solution", "")[:200],
                )
                judge_scores[cp_name] = result.score

            # Print comparison
            grep_total = sum(grep_scores.values()) if grep_scores else 0
            judge_total = sum(judge_scores.values())
            print(f"  rep{rep}:")
            print(f"    grep_total={grep_total:.1f}  judge_total={judge_total:.1f}")
            for cp_name in expected["checkpoints"]:
                # Map checkpoint names (task.toml names may differ from verifier names)
                g = grep_scores.get(cp_name, grep_scores.get(cp_name.split("_")[0], -1))
                j = judge_scores.get(cp_name, -1)
                marker = " !!!" if abs(g - j) > 0.3 else ""
                print(f"    {cp_name:30s}  grep={g:.2f}  judge={j:.2f}{marker}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
