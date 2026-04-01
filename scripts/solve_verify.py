#!/usr/bin/env python3
"""
Solve-verification loop: deterministic parsers vs bash verifier scores.

Loads ground truth from task.toml files, classifies tasks by parser
applicability, runs structural verification, and compares against
existing scored results from results/runs/.

Usage:
    python3 scripts/solve_verify.py
    python3 scripts/solve_verify.py --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from glob import glob
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

PARSER_LANGUAGES = {
    "python": "python_ast",
    "go": "go_ast",
    "javascript": "manifests",
    "typescript": "manifests",
    "java": "manifests",
    "ruby": "manifests",
}

# Languages where we can structurally verify file path claims
STRUCTURAL_LANGUAGES = set(PARSER_LANGUAGES.keys()) | {
    "yaml",
    "go-template",
    "protobuf",
    "c++",
    "cpp",
    "rust",
    "sql",
}


@dataclass(frozen=True)
class GroundTruthFile:
    """A single ground truth file claim."""

    path: str
    repo: str
    confidence: float = 0.0
    source: str = ""


@dataclass(frozen=True)
class TaskInfo:
    """Parsed task metadata for verification."""

    task_id: str
    suite: str
    task_type: str
    languages: list[str]
    difficulty: str
    ground_truth_tiers: list[str]
    required_files: list[GroundTruthFile]
    sufficient_files: list[GroundTruthFile]
    toml_path: str


@dataclass
class VerificationResult:
    """Result of deterministic verification for a single task."""

    task_id: str
    status: str  # PASS, FAIL, SKIP, GAP
    parser_type: str  # python_ast, go_ast, manifests, structural, none
    reason: str
    gt_file_count: int = 0
    gt_verified_count: int = 0
    gt_gaps: list[str] = field(default_factory=list)
    bash_score: float = 0.0
    bash_passed: bool = False
    suite: str = ""
    task_type: str = ""
    languages: list[str] = field(default_factory=list)


@dataclass
class SolveVerificationReport:
    """Summary report of solve-verification results."""

    total_scored: int = 0
    total_checked: int = 0
    total_pass: int = 0
    total_fail: int = 0
    total_skip: int = 0
    total_gap: int = 0
    pass_rate: float = 0.0
    by_suite: dict[str, dict[str, int]] = field(default_factory=dict)
    by_task_type: dict[str, dict[str, int]] = field(default_factory=dict)
    by_parser: dict[str, dict[str, int]] = field(default_factory=dict)
    ground_truth_gaps: list[dict[str, str]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_task_toml(path: str) -> TaskInfo | None:
    """Load and parse a task.toml file into TaskInfo."""
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None

    task = data.get("task", {})
    metadata = data.get("metadata", {})
    gt = data.get("ground_truth", {})

    task_id = task.get("id", "")
    if not task_id:
        return None

    required = [
        GroundTruthFile(
            path=rf.get("path", ""),
            repo=rf.get("repo", ""),
            confidence=rf.get("confidence", 0.0),
            source=rf.get("source", ""),
        )
        for rf in gt.get("required_files", [])
    ]

    sufficient = [
        GroundTruthFile(
            path=sf.get("path", ""),
            repo=sf.get("repo", ""),
            confidence=sf.get("confidence", 0.0),
            source=sf.get("source", ""),
        )
        for sf in gt.get("sufficient_files", [])
    ]

    return TaskInfo(
        task_id=task_id,
        suite=task.get("suite", ""),
        task_type=task.get("task_type", ""),
        languages=metadata.get("languages", []),
        difficulty=task.get("difficulty", ""),
        ground_truth_tiers=gt.get("tiers", []),
        required_files=required,
        sufficient_files=sufficient,
        toml_path=path,
    )


def load_scored_results(runs_dir: str) -> dict[str, dict[str, Any]]:
    """Load all results.json from scored runs."""
    results: dict[str, dict[str, Any]] = {}
    pattern = os.path.join(runs_dir, "*/results.json")
    for path in sorted(glob(pattern)):
        run_dir = os.path.basename(os.path.dirname(path))
        if run_dir.startswith("_"):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            results[data.get("task_id", run_dir)] = data
        except (OSError, json.JSONDecodeError):
            continue
    return results


def build_task_index(benchmarks_dir: str) -> dict[str, TaskInfo]:
    """Build task_id -> TaskInfo index from all task.toml files."""
    index: dict[str, TaskInfo] = {}
    pattern = os.path.join(benchmarks_dir, "*/*/task.toml")
    for path in sorted(glob(pattern)):
        info = load_task_toml(path)
        if info is not None:
            index[info.task_id] = info
    return index


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_parser(task: TaskInfo) -> str:
    """Determine which parser applies to a task.

    Returns: parser type string or 'none' if no parser applies.
    Priority: language-specific parser > structural > none.
    """
    if not task.languages:
        return "none"

    # Check for language-specific parsers
    for lang in task.languages:
        lang_lower = lang.lower()
        if lang_lower in PARSER_LANGUAGES:
            return PARSER_LANGUAGES[lang_lower]

    # Check if any language supports structural verification
    for lang in task.languages:
        if lang.lower() in STRUCTURAL_LANGUAGES:
            return "structural"

    return "none"


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_ground_truth_structure(task: TaskInfo) -> VerificationResult:
    """Verify ground truth claims are structurally valid.

    Checks:
    - required_files have non-empty path and repo
    - File paths have valid extensions matching claimed languages
    - Confidence values are in [0, 1]
    - No duplicate file claims
    """
    parser_type = classify_parser(task)

    if not task.required_files and not task.sufficient_files:
        return VerificationResult(
            task_id=task.task_id,
            status="GAP",
            parser_type=parser_type,
            reason="No ground truth files defined",
            suite=task.suite,
            task_type=task.task_type,
            languages=task.languages,
        )

    if parser_type == "none":
        return VerificationResult(
            task_id=task.task_id,
            status="SKIP",
            parser_type="none",
            reason=f"No parser for languages: {task.languages}",
            gt_file_count=len(task.required_files),
            suite=task.suite,
            task_type=task.task_type,
            languages=task.languages,
        )

    all_files = task.required_files + task.sufficient_files
    gaps: list[str] = []
    verified = 0

    seen_paths: set[tuple[str, str]] = set()
    for gf in all_files:
        key = (gf.repo, gf.path)

        # Check for empty path/repo
        if not gf.path:
            gaps.append(f"Empty path in ground truth for repo={gf.repo}")
            continue
        if not gf.repo:
            gaps.append(f"Empty repo for path={gf.path}")
            continue

        # Check for duplicates
        if key in seen_paths:
            gaps.append(f"Duplicate claim: {gf.repo}/{gf.path}")
            continue
        seen_paths.add(key)

        # Check confidence range
        if not (0.0 <= gf.confidence <= 1.0):
            gaps.append(f"Invalid confidence {gf.confidence} for {gf.repo}/{gf.path}")
            continue

        # Check path has a file extension (basic structural check)
        if "." not in os.path.basename(gf.path) and not gf.path.endswith("/"):
            gaps.append(f"Path lacks extension: {gf.repo}/{gf.path}")
            continue

        verified += 1

    # Determine status
    if gaps and verified == 0:
        status = "FAIL"
        reason = f"All {len(all_files)} ground truth claims have issues"
    elif gaps:
        status = "PASS"
        reason = f"{verified}/{len(all_files)} claims verified, {len(gaps)} gaps"
    else:
        status = "PASS"
        reason = f"All {verified} ground truth claims structurally valid"

    return VerificationResult(
        task_id=task.task_id,
        status=status,
        parser_type=parser_type,
        reason=reason,
        gt_file_count=len(all_files),
        gt_verified_count=verified,
        gt_gaps=gaps,
        suite=task.suite,
        task_type=task.task_type,
        languages=task.languages,
    )


def verify_file_language_consistency(task: TaskInfo) -> list[str]:
    """Check that ground truth file extensions are consistent with task languages."""
    extension_to_lang: dict[str, set[str]] = {
        ".py": {"python"},
        ".go": {"go"},
        ".js": {"javascript"},
        ".ts": {"typescript"},
        ".tsx": {"typescript"},
        ".jsx": {"javascript"},
        ".java": {"java"},
        ".rb": {"ruby"},
        ".rs": {"rust"},
        ".cpp": {"c++", "cpp"},
        ".cc": {"c++", "cpp"},
        ".h": {"c++", "cpp", "c"},
        ".yaml": {"yaml"},
        ".yml": {"yaml"},
        ".toml": {"python", "rust"},
        ".json": {"javascript", "typescript", "python", "go", "java", "ruby"},
        ".mod": {"go"},
        ".sum": {"go"},
        ".sql": {"sql"},
        ".proto": {"protobuf"},
        ".cfg": {"python"},
    }

    task_langs = {lang.lower() for lang in task.languages}
    gaps: list[str] = []

    for gf in task.required_files + task.sufficient_files:
        ext = os.path.splitext(gf.path)[1].lower()
        if ext in extension_to_lang:
            expected_langs = extension_to_lang[ext]
            # Config/manifest files match many languages, skip strict check
            if ext in (".json", ".yaml", ".yml", ".toml", ".cfg"):
                continue
            if not expected_langs & task_langs:
                gaps.append(
                    f"{gf.repo}/{gf.path} ({ext}) inconsistent with "
                    f"task languages {task.languages}"
                )

    return gaps


def compare_with_bash_scores(
    result: VerificationResult,
    scored: dict[str, Any],
) -> VerificationResult:
    """Enrich verification result with bash verifier scores for comparison."""
    scores = scored.get("scores", {})
    result.bash_score = scores.get("task_score", 0.0)
    result.bash_passed = scores.get("all_passed", False)
    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _increment(d: dict[str, dict[str, int]], key: str, status: str) -> None:
    if key not in d:
        d[key] = {"PASS": 0, "FAIL": 0, "SKIP": 0, "GAP": 0, "total": 0}
    d[key][status] = d[key].get(status, 0) + 1
    d[key]["total"] = d[key].get("total", 0) + 1


def generate_report(
    results: list[VerificationResult],
    total_scored: int,
) -> SolveVerificationReport:
    """Generate summary report from verification results."""
    report = SolveVerificationReport(total_scored=total_scored)

    for r in results:
        report.total_checked += 1
        if r.status == "PASS":
            report.total_pass += 1
        elif r.status == "FAIL":
            report.total_fail += 1
        elif r.status == "SKIP":
            report.total_skip += 1
        elif r.status == "GAP":
            report.total_gap += 1

        _increment(report.by_suite, r.suite, r.status)
        _increment(report.by_task_type, r.task_type, r.status)
        _increment(report.by_parser, r.parser_type, r.status)

        # Collect gaps
        for gap in r.gt_gaps:
            report.ground_truth_gaps.append({"task_id": r.task_id, "gap": gap})

        report.results.append(
            {
                "task_id": r.task_id,
                "status": r.status,
                "parser_type": r.parser_type,
                "reason": r.reason,
                "gt_file_count": r.gt_file_count,
                "gt_verified_count": r.gt_verified_count,
                "gt_gaps": r.gt_gaps,
                "bash_score": r.bash_score,
                "bash_passed": r.bash_passed,
                "suite": r.suite,
                "task_type": r.task_type,
                "languages": r.languages,
            }
        )

    applicable = report.total_pass + report.total_fail
    report.pass_rate = report.total_pass / applicable if applicable > 0 else 0.0

    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_verification(
    benchmarks_dir: str,
    runs_dir: str,
    verbose: bool = False,
) -> SolveVerificationReport:
    """Run the full solve-verification loop."""
    # Load data
    task_index = build_task_index(benchmarks_dir)
    scored = load_scored_results(runs_dir)

    if verbose:
        print(f"Loaded {len(task_index)} tasks, {len(scored)} scored runs")

    results: list[VerificationResult] = []

    for task_id, scored_data in sorted(scored.items()):
        task = task_index.get(task_id)
        if task is None:
            results.append(
                VerificationResult(
                    task_id=task_id,
                    status="SKIP",
                    parser_type="none",
                    reason="No task.toml found",
                )
            )
            continue

        # Structural verification of ground truth
        result = verify_ground_truth_structure(task)

        # Check language consistency
        lang_gaps = verify_file_language_consistency(task)
        if lang_gaps:
            result.gt_gaps.extend(lang_gaps)

        # Compare with bash scores
        result = compare_with_bash_scores(result, scored_data)

        results.append(result)

        if verbose:
            status_char = {
                "PASS": "+",
                "FAIL": "X",
                "SKIP": "-",
                "GAP": "?",
            }
            print(
                f"  [{status_char.get(result.status, '?')}] {task_id}: "
                f"{result.reason} (bash={result.bash_score:.2f})"
            )

    report = generate_report(results, total_scored=len(scored))

    if verbose:
        print()
        print(f"=== Solve Verification Summary ===")
        print(f"Total scored runs: {report.total_scored}")
        print(f"Total checked:     {report.total_checked}")
        print(f"  PASS: {report.total_pass}")
        print(f"  FAIL: {report.total_fail}")
        print(f"  SKIP: {report.total_skip}")
        print(f"  GAP:  {report.total_gap}")
        print(f"Pass rate (of applicable): {report.pass_rate:.1%}")
        print()
        if report.ground_truth_gaps:
            print(f"Ground truth gaps ({len(report.ground_truth_gaps)}):")
            for g in report.ground_truth_gaps:
                print(f"  {g['task_id']}: {g['gap']}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Solve-verification loop for deterministic parsers"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print detailed output"
    )
    parser.add_argument(
        "--benchmarks-dir",
        default=None,
        help="Path to benchmarks directory",
    )
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Path to results/runs directory",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Path to write JSON report",
    )
    args = parser.parse_args()

    # Resolve paths relative to project root
    project_root = Path(__file__).resolve().parent.parent
    benchmarks_dir = args.benchmarks_dir or str(project_root / "benchmarks")
    runs_dir = args.runs_dir or str(project_root / "results" / "runs")
    output_path = args.output or str(
        project_root / "results" / "solve_verification_report.json"
    )

    report = run_verification(benchmarks_dir, runs_dir, verbose=args.verbose)

    # Write report
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(asdict(report), f, indent=2)

    print(f"\nReport written to {output_path}")
    print(
        f"Pass rate: {report.pass_rate:.1%} "
        f"({report.total_pass}/{report.total_pass + report.total_fail} applicable)"
    )

    # Exit with non-zero if below 80% target
    if report.pass_rate < 0.80:
        print(f"WARNING: Below 80% target pass rate")
        sys.exit(1)


if __name__ == "__main__":
    main()
