#!/usr/bin/env python3
"""Audit difficulty calibration and MCP benefit rationale for all active tasks.

Produces two reports:
  results/analysis/difficulty_calibration.md
  results/analysis/mcp_validation.md
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.tasks import find_task_dirs as _find_task_dirs

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11


ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS = ROOT / "benchmarks"
SAMPLE_RUNS = ROOT / "results" / "sample_runs"
OUTPUT_DIR = ROOT / "results" / "analysis"

# Mapping from sample_runs directory names to task_type values
SAMPLE_RUN_TYPE_MAP = {
    "api_contract": "api_contract",
    "dead_code": "dead_code_necropsy",
    "dep_traversal": "dependency_graph",
    "monorepo_boundary": "monorepo_boundary",
    "provenance": "error_provenance",
    "refactor_orchestration": "refactor_orchestration",
    "schema_evolution": "db_schema_evolution",
    "support_mapping": "support_code_mapping",
}

# Reverse: task directory prefix -> sample_runs directory
TASK_DIR_TO_SAMPLE = {
    "api-contract-": "api_contract",
    "dead-code-": "dead_code",
    "dep-traversal-": "dep_traversal",
    "monorepo-boundary-": "monorepo_boundary",
    "err-provenance-": "provenance",
    "refactor-orchestration-": "refactor_orchestration",
    "schema-evolution-": "schema_evolution",
    "support-mapping-": "support_mapping",
}


@dataclass
class TaskInfo:
    task_dir: str  # directory name e.g. "api-contract-001"
    suite: str
    task_type: str
    difficulty: str
    difficulty_stratum: str
    repos_count: int
    checkpoint_count: int
    gt_item_count: int
    instruction_word_count: int
    expected_mcp_benefit: str
    mcp_benefit_rationale: str
    baseline_score: float | None = None
    mcp_score: float | None = None
    difficulty_flags: list[str] = field(default_factory=list)
    mcp_flags: list[str] = field(default_factory=list)


def count_gt_items(gt: dict) -> int:
    """Count total ground truth items across all list/dict fields."""
    total = 0
    for v in gt.values():
        if isinstance(v, list):
            total += len(v)
        elif isinstance(v, dict):
            total += count_gt_items(v)
    return total


def load_sample_scores() -> dict[str, dict[str, float]]:
    """Load baseline and MCP scores from sample runs.

    Returns {task_dir_name: {"baseline": score, "mcp": score}}
    """
    scores: dict[str, dict[str, float]] = {}
    if not SAMPLE_RUNS.exists():
        return scores

    for run_log in SAMPLE_RUNS.rglob("run_log.json"):
        with open(run_log) as f:
            data = json.load(f)
        mode = data.get("mode", "")
        # task_dir is the immediate parent directory of run_log.json
        task_dir = run_log.parent.name
        total = sum(c["weight"] * c["score"] for c in data.get("checkpoints", []))
        if task_dir not in scores:
            scores[task_dir] = {}
        scores[task_dir][mode] = round(total, 2)

    return scores


def find_task_dirs() -> list[Path]:
    """Find all active task directories (containing task.toml, not in _archived)."""
    return _find_task_dirs(BENCHMARKS)


def parse_task(task_path: Path, sample_scores: dict) -> TaskInfo:
    """Parse a task directory into TaskInfo."""
    toml_path = task_path / "task.toml"
    gt_path = task_path / "ground_truth.json"
    instruction_path = task_path / "instruction.md"

    with open(toml_path, "rb") as f:
        toml_data = tomllib.load(f)

    task_section = toml_data.get("task", {})
    tool_access = toml_data.get("tool_access", {})
    repos = toml_data.get("repos", [])
    checkpoints = toml_data.get("checkpoints", [])

    # Ground truth item count
    gt_count = 0
    if gt_path.exists():
        with open(gt_path) as f:
            gt_data = json.load(f)
        gt_count = count_gt_items(gt_data)

    # Instruction word count
    word_count = 0
    if instruction_path.exists():
        word_count = len(instruction_path.read_text().split())

    # Sample run scores
    task_dir = task_path.name
    scores = sample_scores.get(task_dir, {})

    # Also check for alternate naming (e.g. refactor-orch-003 vs refactor-orchestration-003)
    if not scores:
        # Try with shortened names used in sample runs
        alt_names = {
            "refactor-orchestration-": "refactor-orch-",
        }
        for prefix, alt_prefix in alt_names.items():
            if task_dir.startswith(prefix):
                alt_name = task_dir.replace(prefix, alt_prefix, 1)
                scores = sample_scores.get(alt_name, {})
                break

    return TaskInfo(
        task_dir=task_dir,
        suite=task_section.get("suite", ""),
        task_type=task_section.get("task_type", ""),
        difficulty=task_section.get("difficulty", ""),
        difficulty_stratum=toml_data.get("difficulty_stratum", ""),
        repos_count=len(repos),
        checkpoint_count=len(checkpoints),
        gt_item_count=gt_count,
        instruction_word_count=word_count,
        expected_mcp_benefit=tool_access.get("expected_mcp_benefit", ""),
        mcp_benefit_rationale=tool_access.get("mcp_benefit_rationale", ""),
        baseline_score=scores.get("baseline"),
        mcp_score=scores.get("mcp"),
    )


def check_difficulty(task: TaskInfo) -> None:
    """Flag difficulty mismatches."""
    d = task.difficulty

    # Medium tasks with high complexity indicators
    if d == "medium":
        if task.repos_count > 3:
            task.difficulty_flags.append(
                f"medium with {task.repos_count} repos (>3) -> probably hard"
            )
        if task.gt_item_count > 10:
            task.difficulty_flags.append(
                f"medium with {task.gt_item_count} GT items (>10) -> probably hard"
            )

    # Expert tasks that seem too simple
    if d == "expert":
        if task.repos_count == 1 and task.gt_item_count < 5:
            task.difficulty_flags.append(
                f"expert with 1 repo and {task.gt_item_count} GT items (<5) -> probably medium"
            )

    # Hard tasks that seem too simple
    if d == "hard":
        if task.repos_count == 1 and task.gt_item_count < 5:
            task.difficulty_flags.append(
                f"hard with 1 repo and {task.gt_item_count} GT items (<5) -> review"
            )

    # Tasks where baseline score > 0.8 -> possibly too easy
    if task.baseline_score is not None and task.baseline_score > 0.8:
        task.difficulty_flags.append(
            f"baseline score {task.baseline_score:.2f} > 0.8 -> too easy for {d}?"
        )

    # Stratum vs repos count consistency
    if task.difficulty_stratum == "calibration" and task.repos_count > 1:
        task.difficulty_flags.append(
            f"calibration stratum but {task.repos_count} repos"
        )
    if task.difficulty_stratum == "dual_repo" and task.repos_count != 2:
        task.difficulty_flags.append(
            f"dual_repo stratum but {task.repos_count} repos"
        )
    if task.difficulty_stratum == "3_5_repo" and not (3 <= task.repos_count <= 5):
        task.difficulty_flags.append(
            f"3_5_repo stratum but {task.repos_count} repos"
        )


def check_mcp(task: TaskInfo) -> None:
    """Flag MCP benefit mismatches."""
    expected = task.expected_mcp_benefit

    # Check against actual scores if available
    if task.baseline_score is not None and task.mcp_score is not None:
        gap = task.mcp_score - task.baseline_score
        if expected == "high" and gap < 0.3:
            task.mcp_flags.append(
                f"expected high but actual gap={gap:.2f} (<0.3): "
                f"baseline={task.baseline_score:.2f}, mcp={task.mcp_score:.2f}"
            )
        if expected == "medium" and (gap < 0.1 or gap > 0.3):
            task.mcp_flags.append(
                f"expected medium but actual gap={gap:.2f} (not 0.1-0.3): "
                f"baseline={task.baseline_score:.2f}, mcp={task.mcp_score:.2f}"
            )
        if expected == "low" and gap > 0.1:
            task.mcp_flags.append(
                f"expected low but actual gap={gap:.2f} (>0.1): "
                f"baseline={task.baseline_score:.2f}, mcp={task.mcp_score:.2f}"
            )

    # Plausibility checks for tasks without sample runs
    if task.baseline_score is None:
        # Single-repo tasks claiming high MCP benefit — but monorepo/cross-pkg
        # strata legitimately benefit from MCP even with 1 repo, so only flag
        # plain large_single tasks.
        monorepo_strata = {
            "monorepo_cross_package",
        }
        is_monorepo = task.difficulty_stratum in monorepo_strata
        if expected == "high" and task.repos_count == 1 and not is_monorepo:
            task.mcp_flags.append(
                f"claims high MCP benefit but single-repo (large_single) — "
                f"grep may suffice unless codebase is very large"
            )

        # Multi-repo tasks with low/no MCP benefit
        if expected == "low" and task.repos_count >= 3:
            task.mcp_flags.append(
                f"claims low MCP benefit but {task.repos_count} repos — "
                f"cross-repo navigation typically benefits from MCP"
            )

        # Missing rationale
        if not task.mcp_benefit_rationale:
            task.mcp_flags.append("missing mcp_benefit_rationale")

        # Missing expected benefit
        if not expected:
            task.mcp_flags.append("missing expected_mcp_benefit")


def generate_difficulty_report(tasks: list[TaskInfo]) -> str:
    """Generate difficulty calibration markdown report."""
    flagged = [t for t in tasks if t.difficulty_flags]
    clean = [t for t in tasks if not t.difficulty_flags]

    lines = [
        "# Difficulty Calibration Audit",
        "",
        f"**Total tasks audited:** {len(tasks)}",
        f"**Tasks with flags:** {len(flagged)}",
        f"**Clean tasks:** {len(clean)}",
        "",
        "## Distribution",
        "",
    ]

    # Difficulty distribution
    diff_counts: dict[str, int] = {}
    for t in tasks:
        diff_counts[t.difficulty] = diff_counts.get(t.difficulty, 0) + 1
    lines.append("| Difficulty | Count |")
    lines.append("|-----------|-------|")
    for d in ["easy", "medium", "hard", "expert"]:
        if d in diff_counts:
            lines.append(f"| {d} | {diff_counts[d]} |")
    lines.append("")

    # Stratum distribution
    strat_counts: dict[str, int] = {}
    for t in tasks:
        s = t.difficulty_stratum or "(none)"
        strat_counts[s] = strat_counts.get(s, 0) + 1
    lines.append("| Stratum | Count |")
    lines.append("|---------|-------|")
    for s, c in sorted(strat_counts.items()):
        lines.append(f"| {s} | {c} |")
    lines.append("")

    # Full table
    lines.append("## All Tasks")
    lines.append("")
    lines.append("| Task | Suite | Type | Difficulty | Stratum | Repos | Checkpoints | GT Items | Words | Baseline | MCP |")
    lines.append("|------|-------|------|-----------|---------|-------|-------------|----------|-------|----------|-----|")
    for t in tasks:
        bl = f"{t.baseline_score:.2f}" if t.baseline_score is not None else "-"
        mc = f"{t.mcp_score:.2f}" if t.mcp_score is not None else "-"
        lines.append(
            f"| {t.task_dir} | {t.suite} | {t.task_type} | {t.difficulty} | "
            f"{t.difficulty_stratum} | {t.repos_count} | {t.checkpoint_count} | "
            f"{t.gt_item_count} | {t.instruction_word_count} | {bl} | {mc} |"
        )
    lines.append("")

    # Flagged tasks
    if flagged:
        lines.append("## Flagged Tasks")
        lines.append("")
        for t in flagged:
            lines.append(f"### {t.task_dir}")
            lines.append(f"- **Difficulty:** {t.difficulty} | **Stratum:** {t.difficulty_stratum}")
            lines.append(f"- **Repos:** {t.repos_count} | **GT items:** {t.gt_item_count} | **Checkpoints:** {t.checkpoint_count}")
            if t.baseline_score is not None:
                lines.append(f"- **Baseline:** {t.baseline_score:.2f} | **MCP:** {t.mcp_score:.2f}" if t.mcp_score is not None else f"- **Baseline:** {t.baseline_score:.2f}")
            lines.append("- **Flags:**")
            for flag in t.difficulty_flags:
                lines.append(f"  - {flag}")
            lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    flag_categories: dict[str, int] = {}
    for t in flagged:
        for flag in t.difficulty_flags:
            if "probably hard" in flag:
                cat = "medium -> probably hard"
            elif "probably medium" in flag:
                cat = "expert -> probably medium"
            elif "too easy" in flag:
                cat = "baseline too easy for label"
            elif "stratum" in flag:
                cat = "stratum mismatch"
            elif "review" in flag:
                cat = "hard -> needs review"
            else:
                cat = "other"
            flag_categories[cat] = flag_categories.get(cat, 0) + 1

    for cat, count in sorted(flag_categories.items()):
        lines.append(f"- **{cat}:** {count} tasks")
    lines.append("")

    return "\n".join(lines)


def generate_mcp_report(tasks: list[TaskInfo]) -> str:
    """Generate MCP benefit validation markdown report."""
    flagged = [t for t in tasks if t.mcp_flags]
    with_scores = [t for t in tasks if t.baseline_score is not None and t.mcp_score is not None]
    clean = [t for t in tasks if not t.mcp_flags]

    lines = [
        "# MCP Benefit Rationale Validation",
        "",
        f"**Total tasks audited:** {len(tasks)}",
        f"**Tasks with sample runs:** {len(with_scores)}",
        f"**Tasks with flags:** {len(flagged)}",
        f"**Clean tasks:** {len(clean)}",
        "",
        "## Expected MCP Benefit Distribution",
        "",
    ]

    benefit_counts: dict[str, int] = {}
    for t in tasks:
        b = t.expected_mcp_benefit or "(none)"
        benefit_counts[b] = benefit_counts.get(b, 0) + 1
    lines.append("| Expected Benefit | Count |")
    lines.append("|-----------------|-------|")
    for b in ["low", "medium", "high", "(none)"]:
        if b in benefit_counts:
            lines.append(f"| {b} | {benefit_counts[b]} |")
    lines.append("")

    # Tasks with actual scores
    if with_scores:
        lines.append("## Empirical Validation (Tasks with Sample Runs)")
        lines.append("")
        lines.append("| Task | Expected | Baseline | MCP | Gap | Status |")
        lines.append("|------|----------|----------|-----|-----|--------|")
        for t in with_scores:
            gap = t.mcp_score - t.baseline_score
            expected = t.expected_mcp_benefit
            # Determine status
            if expected == "high":
                status = "OK" if gap >= 0.3 else f"GAP TOO SMALL ({gap:.2f})"
            elif expected == "medium":
                status = "OK" if 0.1 <= gap <= 0.3 else f"MISMATCH ({gap:.2f})"
            elif expected == "low":
                status = "OK" if gap <= 0.1 else f"GAP TOO LARGE ({gap:.2f})"
            else:
                status = "NO LABEL"
            lines.append(
                f"| {t.task_dir} | {expected} | {t.baseline_score:.2f} | "
                f"{t.mcp_score:.2f} | {gap:.2f} | {status} |"
            )
        lines.append("")

    # Plausibility assessment for all tasks
    lines.append("## Plausibility Assessment (All Tasks)")
    lines.append("")
    lines.append("| Task | Expected | Repos | Stratum | Rationale (truncated) | Plausible? |")
    lines.append("|------|----------|-------|---------|----------------------|------------|")
    for t in tasks:
        rat = t.mcp_benefit_rationale[:60] + "..." if len(t.mcp_benefit_rationale) > 60 else t.mcp_benefit_rationale
        # Assess plausibility
        plausible = "yes"
        monorepo_s = {"monorepo_cross_package"}
        is_mr = t.difficulty_stratum in monorepo_s
        if t.expected_mcp_benefit == "high" and t.repos_count == 1 and not is_mr:
            plausible = "REVIEW"
        elif t.expected_mcp_benefit == "low" and t.repos_count >= 3:
            plausible = "REVIEW"
        elif not t.expected_mcp_benefit:
            plausible = "MISSING"
        lines.append(
            f"| {t.task_dir} | {t.expected_mcp_benefit or '-'} | {t.repos_count} | "
            f"{t.difficulty_stratum} | {rat} | {plausible} |"
        )
    lines.append("")

    # Flagged tasks
    if flagged:
        lines.append("## Flagged Tasks")
        lines.append("")
        for t in flagged:
            lines.append(f"### {t.task_dir}")
            lines.append(f"- **Expected MCP benefit:** {t.expected_mcp_benefit or '(none)'}")
            lines.append(f"- **Repos:** {t.repos_count} | **Stratum:** {t.difficulty_stratum}")
            if t.baseline_score is not None and t.mcp_score is not None:
                lines.append(f"- **Baseline:** {t.baseline_score:.2f} | **MCP:** {t.mcp_score:.2f} | **Gap:** {t.mcp_score - t.baseline_score:.2f}")
            lines.append(f"- **Rationale:** {t.mcp_benefit_rationale}")
            lines.append("- **Flags:**")
            for flag in t.mcp_flags:
                lines.append(f"  - {flag}")
            lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    flag_types: dict[str, int] = {}
    for t in flagged:
        for flag in t.mcp_flags:
            if "actual gap" in flag:
                cat = "empirical score mismatch"
            elif "single-repo" in flag:
                cat = "high benefit + single repo"
            elif "cross-repo" in flag:
                cat = "low benefit + multi repo"
            elif "missing" in flag.lower():
                cat = "missing field"
            else:
                cat = "other"
            flag_types[cat] = flag_types.get(cat, 0) + 1
    for cat, count in sorted(flag_types.items()):
        lines.append(f"- **{cat}:** {count} tasks")
    lines.append("")

    return "\n".join(lines)


def main():
    sample_scores = load_sample_scores()
    task_dirs = find_task_dirs()

    print(f"Found {len(task_dirs)} task directories")
    print(f"Found {len(sample_scores)} sample run entries")

    tasks: list[TaskInfo] = []
    for td in task_dirs:
        try:
            info = parse_task(td, sample_scores)
            check_difficulty(info)
            check_mcp(info)
            tasks.append(info)
        except Exception as e:
            print(f"  ERROR parsing {td.name}: {e}", file=sys.stderr)

    print(f"Parsed {len(tasks)} tasks successfully")

    # Generate reports
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    diff_report = generate_difficulty_report(tasks)
    diff_path = OUTPUT_DIR / "difficulty_calibration.md"
    diff_path.write_text(diff_report)
    print(f"Wrote {diff_path}")

    mcp_report = generate_mcp_report(tasks)
    mcp_path = OUTPUT_DIR / "mcp_validation.md"
    mcp_path.write_text(mcp_report)
    print(f"Wrote {mcp_path}")

    # Print summary
    flagged_diff = sum(1 for t in tasks if t.difficulty_flags)
    flagged_mcp = sum(1 for t in tasks if t.mcp_flags)
    print(f"\nDifficulty flags: {flagged_diff} tasks")
    print(f"MCP flags: {flagged_mcp} tasks")

    return 0 if (flagged_diff + flagged_mcp) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
