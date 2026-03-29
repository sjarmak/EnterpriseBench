#!/usr/bin/env python3
"""Detect duplicate and near-duplicate benchmark tasks.

Checks:
1. Identical ground-truth file path sets
2. High instruction.md text similarity (Jaccard on word n-grams, threshold >0.7)
3. Same repo+rev+PR combination
4. Identical check script content across tasks of the same type
"""

import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.tasks import find_task_dirs

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        import tomllib  # Python 3.11+

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent / "benchmarks"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "analysis"


def load_task_toml(task_dir):
    """Load task.toml from a task directory."""
    toml_path = task_dir / "task.toml"
    if not toml_path.exists():
        return None
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def load_instruction(task_dir):
    """Load instruction.md text."""
    path = task_dir / "instruction.md"
    if not path.exists():
        return ""
    return path.read_text()


def load_ground_truth(task_dir):
    """Load ground_truth.json."""
    path = task_dir / "ground_truth.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def get_gt_file_paths(task_toml, gt_json):
    """Extract ground truth file paths from task.toml and ground_truth.json."""
    paths = set()
    # From task.toml
    if task_toml:
        gt = task_toml.get("ground_truth", {})
        for f in gt.get("required_files", []):
            if isinstance(f, str):
                paths.add(f)
            elif isinstance(f, dict):
                p = f.get("path", "")
                if p:
                    paths.add(p)
        for f in gt.get("sufficient_files", []):
            if isinstance(f, str):
                paths.add(f)
            elif isinstance(f, dict):
                p = f.get("path", "")
                if p:
                    paths.add(p)
    # From ground_truth.json
    if gt_json:
        for f in gt_json.get("required_files", []):
            if isinstance(f, str):
                paths.add(f)
            elif isinstance(f, dict):
                p = f.get("path", "")
                if p:
                    paths.add(p)
        for f in gt_json.get("sufficient_files", []):
            if isinstance(f, str):
                paths.add(f)
            elif isinstance(f, dict):
                p = f.get("path", "")
                if p:
                    paths.add(p)
    return frozenset(paths)


def get_repos_info(task_toml):
    """Extract repo URLs and revisions."""
    if not task_toml:
        return []
    repos = task_toml.get("repos", [])
    return [(r.get("url", ""), r.get("rev", "")) for r in repos]


def get_pr_refs(gt_json):
    """Extract PR references from ground_truth.json."""
    refs = set()
    if not gt_json:
        return refs
    fix_pr = gt_json.get("fix_pr", "")
    if fix_pr:
        refs.add(fix_pr)
    candidate_ref = gt_json.get("candidate_ref", "")
    if candidate_ref:
        refs.add(candidate_ref)
    return refs


def word_ngrams(text, n=3):
    """Generate word n-grams from text."""
    # Normalize: lowercase, remove punctuation, split on whitespace
    words = re.findall(r'[a-z0-9_]+', text.lower())
    if len(words) < n:
        return set(tuple(words),) if words else set()
    return {tuple(words[i:i+n]) for i in range(len(words) - n + 1)}


def jaccard_similarity(set_a, set_b):
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def get_check_scripts(task_dir):
    """Get content hashes of check scripts."""
    checks_dir = task_dir / "checks"
    if not checks_dir.exists():
        return {}
    scripts = {}
    for script in sorted(checks_dir.iterdir()):
        if script.suffix == ".sh":
            content = script.read_text()
            scripts[script.name] = hashlib.md5(content.encode()).hexdigest()
    return scripts


def main():
    task_dirs = find_task_dirs()
    print(f"Found {len(task_dirs)} tasks")

    # Collect data for each task
    tasks_data = {}
    for td in task_dirs:
        task_id = f"{td.parent.name}/{td.name}"
        toml_data = load_task_toml(td)
        gt_data = load_ground_truth(td)
        instruction = load_instruction(td)
        task_type = toml_data.get("task", {}).get("task_type", "") if toml_data else ""

        tasks_data[task_id] = {
            "dir": td,
            "toml": toml_data,
            "gt": gt_data,
            "instruction": instruction,
            "task_type": task_type,
            "gt_paths": get_gt_file_paths(toml_data, gt_data),
            "repos": get_repos_info(toml_data),
            "pr_refs": get_pr_refs(gt_data),
            "ngrams": word_ngrams(instruction),
            "check_scripts": get_check_scripts(td),
        }

    findings = []

    # --- Check 1: Identical GT file path sets ---
    gt_groups = defaultdict(list)
    for task_id, data in tasks_data.items():
        if data["gt_paths"]:
            gt_groups[data["gt_paths"]].append(task_id)

    identical_gt = {k: v for k, v in gt_groups.items() if len(v) > 1}
    if identical_gt:
        for paths, task_ids in sorted(identical_gt.items(), key=lambda x: len(x[1]), reverse=True):
            findings.append({
                "type": "identical_gt_paths",
                "severity": "HIGH",
                "tasks": sorted(task_ids),
                "paths": sorted(paths),
            })

    # --- Check 2: Instruction text similarity (Jaccard on word trigrams) ---
    task_ids = sorted(tasks_data.keys())
    high_similarity_pairs = []
    for i, id_a in enumerate(task_ids):
        for id_b in task_ids[i+1:]:
            sim = jaccard_similarity(tasks_data[id_a]["ngrams"], tasks_data[id_b]["ngrams"])
            if sim > 0.7:
                high_similarity_pairs.append({
                    "type": "high_instruction_similarity",
                    "severity": "HIGH" if sim > 0.85 else "MEDIUM",
                    "tasks": [id_a, id_b],
                    "similarity": round(sim, 3),
                })

    findings.extend(sorted(high_similarity_pairs, key=lambda x: x["similarity"], reverse=True))

    # --- Check 3: Same repo+rev+PR combination ---
    repo_rev_pr_groups = defaultdict(list)
    for task_id, data in tasks_data.items():
        for url, rev in data["repos"]:
            for pr in data["pr_refs"]:
                key = (url, rev, pr)
                repo_rev_pr_groups[key].append(task_id)

    for key, task_ids in repo_rev_pr_groups.items():
        if len(task_ids) > 1:
            findings.append({
                "type": "same_repo_rev_pr",
                "severity": "HIGH",
                "tasks": sorted(task_ids),
                "repo": key[0],
                "rev": key[1],
                "pr": key[2],
            })

    # Also check just repo+rev (no PR needed)
    repo_rev_groups = defaultdict(list)
    for task_id, data in tasks_data.items():
        for url, rev in data["repos"]:
            repo_rev_groups[(url, rev)].append(task_id)

    # --- Check 4: Identical check script content across tasks of the same type ---
    type_script_groups = defaultdict(lambda: defaultdict(list))
    for task_id, data in tasks_data.items():
        for script_name, content_hash in data["check_scripts"].items():
            type_script_groups[(data["task_type"], script_name)][content_hash].append(task_id)

    for (task_type, script_name), hash_groups in type_script_groups.items():
        for content_hash, task_ids in hash_groups.items():
            if len(task_ids) > 1:
                findings.append({
                    "type": "identical_check_scripts",
                    "severity": "MEDIUM",
                    "tasks": sorted(task_ids),
                    "task_type": task_type,
                    "script_name": script_name,
                })

    # --- Generate report ---
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / "duplicate_detection.md"

    lines = [
        "# Duplicate and Near-Duplicate Task Detection Report",
        "",
        f"**Date:** 2026-03-29",
        f"**Tasks scanned:** {len(task_dirs)}",
        f"**Findings:** {len(findings)}",
        "",
    ]

    # Summary counts
    by_type = defaultdict(int)
    by_severity = defaultdict(int)
    for f in findings:
        by_type[f["type"]] += 1
        by_severity[f["severity"]] += 1

    lines.append("## Summary")
    lines.append("")
    lines.append("| Check | Count |")
    lines.append("|-------|-------|")
    for t in ["identical_gt_paths", "high_instruction_similarity", "same_repo_rev_pr", "identical_check_scripts"]:
        lines.append(f"| {t} | {by_type.get(t, 0)} |")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for s in ["HIGH", "MEDIUM", "LOW"]:
        if by_severity.get(s, 0) > 0:
            lines.append(f"| {s} | {by_severity[s]} |")
    lines.append("")

    # Detailed findings
    lines.append("## Findings")
    lines.append("")

    # Group by type
    for check_type in ["identical_gt_paths", "same_repo_rev_pr", "high_instruction_similarity", "identical_check_scripts"]:
        type_findings = [f for f in findings if f["type"] == check_type]
        if not type_findings:
            continue

        type_label = {
            "identical_gt_paths": "Identical Ground-Truth File Path Sets",
            "high_instruction_similarity": "High Instruction Text Similarity (Jaccard >0.7)",
            "same_repo_rev_pr": "Same Repo+Rev+PR Combination",
            "identical_check_scripts": "Identical Check Script Content (same task type)",
        }[check_type]

        lines.append(f"### {type_label}")
        lines.append("")

        for i, f in enumerate(type_findings, 1):
            lines.append(f"**{i}. [{f['severity']}]** Tasks: {', '.join(f['tasks'])}")
            if check_type == "identical_gt_paths":
                lines.append(f"   - Shared paths: {', '.join(f['paths'][:5])}")
                if len(f['paths']) > 5:
                    lines.append(f"   - ...and {len(f['paths']) - 5} more")
            elif check_type == "high_instruction_similarity":
                lines.append(f"   - Jaccard similarity: {f['similarity']}")
            elif check_type == "same_repo_rev_pr":
                lines.append(f"   - Repo: {f['repo']}, Rev: {f['rev']}, PR: {f['pr']}")
            elif check_type == "identical_check_scripts":
                lines.append(f"   - Script: {f['script_name']}, Type: {f['task_type']}")
            lines.append("")

    # Repo overlap analysis (informational)
    lines.append("### Repo+Rev Overlap (Informational)")
    lines.append("")
    lines.append("Tasks sharing the same repo and revision (expected for same-codebase tasks):")
    lines.append("")
    for (url, rev), task_ids in sorted(repo_rev_groups.items(), key=lambda x: len(x[1]), reverse=True):
        if len(task_ids) > 1:
            lines.append(f"- **{url}@{rev}** ({len(task_ids)} tasks): {', '.join(sorted(task_ids)[:10])}")
            if len(task_ids) > 10:
                lines.append(f"  ...and {len(task_ids) - 10} more")
    lines.append("")

    # Verdict
    high_count = by_severity.get("HIGH", 0)
    lines.append("## Verdict")
    lines.append("")
    if high_count == 0:
        lines.append("No HIGH-severity duplicates detected. Tasks appear sufficiently distinct.")
    else:
        lines.append(f"**{high_count} HIGH-severity findings** require review. See details above.")
    lines.append("")

    report_content = "\n".join(lines)
    report_path.write_text(report_content)
    print(f"\nReport written to: {report_path}")
    print(f"\nHIGH: {by_severity.get('HIGH', 0)}, MEDIUM: {by_severity.get('MEDIUM', 0)}")

    # Also print summary to stdout
    for f in findings:
        if f["severity"] == "HIGH":
            print(f"  HIGH: {f['type']} — {', '.join(f['tasks'])}")


if __name__ == "__main__":
    main()
