"""Context construction and CLI adapter for run promotion."""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Optional

if __package__:
    from .promotion_types import PromotionContext
else:
    from promotion_types import PromotionContext

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VALID_TARGET_STATES = frozenset({"official", "candidate"})
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def build_context(
    run_id: str,
    target_state: str,
    repo_root: Optional[Path] = None,
    dry_run: bool = False,
    resume_from: int = 0,
    raw_runs_root: Optional[Path] = None,
    official_runs_root: Optional[Path] = None,
    spec_path: Optional[Path] = None,
    receipts_path: Optional[Path] = None,
    task_manifest_path: Optional[Path] = None,
    analysis_plan_path: Optional[Path] = None,
    study_report_path: Optional[Path] = None,
) -> PromotionContext:
    """Build immutable paths for one named promotion."""

    root = repo_root or REPO_ROOT
    if RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError(
            "run_id must be a single safe path component containing only "
            "letters, digits, '.', '_' or '-'"
        )
    raw_root = raw_runs_root or (root / "results" / "runs")
    official_root = official_runs_root or (root / "results" / "official_runs")
    raw_run_dir = raw_root / run_id
    study_config_dir = root / "configs" / "studies" / run_id
    return PromotionContext(
        run_id=run_id,
        target_state=target_state,
        repo_root=root,
        study_report_path=(
            study_report_path or (root / "scripts" / "analysis" / "study_report.py")
        ),
        raw_run_dir=raw_run_dir,
        spec_path=spec_path or (raw_run_dir / "study_spec.json"),
        receipts_path=receipts_path or (raw_run_dir / "receipts.jsonl"),
        task_manifest_path=(
            task_manifest_path or (study_config_dir / "final_manifest.json")
        ),
        analysis_plan_path=(
            analysis_plan_path or (study_config_dir / "analysis_plan.json")
        ),
        staging_dir=official_root / f".{run_id}.staging",
        final_dir=official_root / run_id,
        registry_path=official_root / "_registry.json",
        forensics_dir=official_root / "_failures",
        dry_run=dry_run,
        resume_from=resume_from,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Atomic run-promotion orchestrator for EnterpriseBench. "
            "Promotes a raw run directory to official-run state with "
            "per-step rollback on failure."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --run-id 20260429_001 --target-state official\n"
            "  %(prog)s --run-id 20260429_001 --validate-only\n"
            "  %(prog)s --run-id 20260429_001 --resume-from-step 5\n"
        ),
    )
    parser.add_argument("--run-id", required=True, help="Identifier of the run")
    parser.add_argument(
        "--spec",
        type=Path,
        default=None,
        help="Exact StudySpec JSON path (default: raw run/study_spec.json)",
    )
    parser.add_argument(
        "--receipts",
        type=Path,
        default=None,
        help="Exact receipt JSONL path (default: raw run/receipts.jsonl)",
    )
    parser.add_argument(
        "--task-manifest",
        type=Path,
        default=None,
        help=(
            "Exact final task-manifest JSON path "
            "(default: configs/studies/<run-id>/final_manifest.json)"
        ),
    )
    parser.add_argument(
        "--analysis-plan",
        type=Path,
        default=None,
        help=(
            "Exact frozen analysis-plan JSON path "
            "(default: configs/studies/<run-id>/analysis_plan.json)"
        ),
    )
    parser.add_argument(
        "--target-state",
        default="official",
        choices=sorted(VALID_TARGET_STATES),
        help="State to promote to (default: official)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run only read-only validators; never write promotion artifacts",
    )
    parser.add_argument(
        "--resume-from-step",
        type=int,
        default=0,
        metavar="N",
        help="Skip non-validation steps with 1-based index less than N",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be executed without writing artifacts",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the promotion report as JSON to stdout",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Parse CLI arguments and invoke the orchestration domain object."""

    if __package__:
        from . import run_promotion_orchestrator as orchestrator_module
    else:
        import run_promotion_orchestrator as orchestrator_module

    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ctx = build_context(
        run_id=args.run_id,
        target_state=args.target_state,
        dry_run=args.dry_run,
        resume_from=args.resume_from_step,
        spec_path=args.spec,
        receipts_path=args.receipts,
        task_manifest_path=args.task_manifest,
        analysis_plan_path=args.analysis_plan,
    )
    report = orchestrator_module.RunPromotionOrchestrator(ctx).run(
        validate_only=args.validate_only
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(
            f"[promotion] run_id={report.run_id} "
            f"target={report.target_state} "
            f"succeeded={report.succeeded}"
        )
        for step in report.steps:
            print(
                f"  - {step.step_name:30s} "
                f"{step.status:12s} "
                f"({step.duration_seconds:.2f}s) "
                f"{step.details}"
            )
        if report.forensics_path:
            print(f"[promotion] forensics: {report.forensics_path}")
        if report.error:
            print(f"[promotion] error: {report.error}")
    return 0 if report.succeeded else 1
