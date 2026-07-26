"""Named-capsule validation and staging for benchmark promotion."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from eb_study import (
    CapsuleError,
    ReceiptError,
    SpecError,
    StudyCapsule,
    StudySpec,
    TrialReceipt,
)

if __package__:
    from .promotion_types import CapsuleSnapshot, PromotionContext, StepOutcome
else:
    from promotion_types import CapsuleSnapshot, PromotionContext, StepOutcome

SubprocessRunner = Callable[[list[str], Path], tuple[int, str, str]]


def validate_inputs(ctx: PromotionContext) -> StepOutcome:
    """Validate the exact named Study Capsule that promotion will consume."""

    if not ctx.raw_run_dir.is_dir():
        raise FileNotFoundError(f"Raw run directory not found: {ctx.raw_run_dir}")

    try:
        snapshot = capsule_snapshot(ctx)
        spec = snapshot.spec
    except CapsuleError as exc:
        raise ValueError(f"invalid study capsule: {exc}") from exc

    try:
        capsule = snapshot.capsule
        paired = capsule.paired_valid()
    except CapsuleError as exc:
        raise ValueError(f"study capsule is incomplete or invalid: {exc}") from exc
    if paired.excluded:
        raise ValueError(
            f"study capsule is incomplete: {len(paired.excluded)} declared "
            "task(s) are missing one or more arm/repetition slots"
        )

    return StepOutcome(
        step_name="validate_inputs",
        status="reversible",
        details=(
            f"study_id={spec.study_id} spec_hash={spec.spec_hash} "
            f"receipts={len(capsule.receipts)}"
        ),
    )


def capsule_snapshot(ctx: PromotionContext) -> CapsuleSnapshot:
    """Read and validate one immutable in-memory snapshot of the named capsule."""

    if ctx.capsule_snapshot is not None:
        return ctx.capsule_snapshot

    try:
        spec_source = ctx.spec_path.read_text()
    except OSError as exc:
        raise SpecError(f"cannot read study spec {ctx.spec_path}: {exc}") from exc
    try:
        receipts_source = ctx.receipts_path.read_text()
    except OSError as exc:
        raise ReceiptError(f"cannot read receipts {ctx.receipts_path}: {exc}") from exc

    try:
        spec_payload = json.loads(spec_source)
    except json.JSONDecodeError as exc:
        raise SpecError(f"study spec {ctx.spec_path} is not valid JSON: {exc}") from exc
    spec = StudySpec.from_json(spec_payload)
    if spec.study_id != ctx.run_id:
        raise SpecError(
            f"study_id {spec.study_id!r} does not match promoted run {ctx.run_id!r}"
        )

    receipts: list[TrialReceipt] = []
    for lineno, line in enumerate(receipts_source.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReceiptError(
                f"{ctx.receipts_path}:{lineno} is not valid JSON: {exc}"
            ) from exc
        try:
            receipts.append(TrialReceipt.from_json(payload))
        except ReceiptError as exc:
            raise ReceiptError(f"{ctx.receipts_path}:{lineno}: {exc}") from exc

    capsule = StudyCapsule.build(spec, receipts)
    return CapsuleSnapshot(
        spec_source=spec_source,
        receipts_source=receipts_source,
        spec=spec,
        capsule=capsule,
    )


def assert_capsule_source_unchanged(
    ctx: PromotionContext, snapshot: CapsuleSnapshot
) -> None:
    """Fail if the raw capsule changed after its validation snapshot."""

    try:
        current_spec = ctx.spec_path.read_text()
        current_receipts = ctx.receipts_path.read_text()
    except OSError as exc:
        raise RuntimeError(f"capsule changed after validation: {exc}") from exc
    if (
        current_spec != snapshot.spec_source
        or current_receipts != snapshot.receipts_source
    ):
        raise RuntimeError("capsule changed after validation")


def declared_task_tomls(ctx: PromotionContext) -> tuple[Path, ...]:
    """Resolve every spec task ID to exactly one benchmark task.toml."""

    spec = capsule_snapshot(ctx).spec
    expected = set(spec.task_ids)
    matches: dict[str, list[Path]] = {task_id: [] for task_id in spec.task_ids}
    for path in (ctx.repo_root / "benchmarks").rglob("task.toml"):
        try:
            with path.open("rb") as handle:
                task_id = tomllib.load(handle).get("task", {}).get("id")
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeError(
                f"cannot read declared task candidate {path}: {exc}"
            ) from exc
        if task_id in expected:
            matches[task_id].append(path)

    invalid = {task_id: paths for task_id, paths in matches.items() if len(paths) != 1}
    if invalid:
        detail = ", ".join(
            f"{task_id}={len(paths)} matches" for task_id, paths in invalid.items()
        )
        raise RuntimeError(f"declared task resolution failed: {detail}")
    return tuple(matches[task_id][0] for task_id in spec.task_ids)


def stage_metrics(
    ctx: PromotionContext,
    run_subprocess: SubprocessRunner,
    max_error_detail_len: int,
) -> StepOutcome:
    """Build the validated named capsule's report into staging."""

    if ctx.dry_run:
        return StepOutcome(
            step_name="stage_metrics",
            status="dry_run",
            details="would aggregate metrics into staging",
        )

    snapshot = capsule_snapshot(ctx)
    assert_capsule_source_unchanged(ctx, snapshot)
    ctx.staging_dir.mkdir(parents=True, exist_ok=True)
    output_path = ctx.staging_dir / "score_analysis.json"
    staged_spec = ctx.staging_dir / "study_spec.json"
    staged_receipts = ctx.staging_dir / "receipts.jsonl"
    staged_spec.write_text(snapshot.spec_source)
    staged_receipts.write_text(snapshot.receipts_source)
    cmd = [
        sys.executable,
        str(ctx.study_report_path),
        "--spec",
        str(staged_spec),
        "--receipts",
        str(staged_receipts),
        "--output",
        str(output_path),
    ]
    rc, _stdout, stderr = run_subprocess(cmd, ctx.repo_root)
    if rc != 0:
        raise RuntimeError(
            f"study_report.py exited {rc}: {stderr[-max_error_detail_len:]}"
        )
    if not output_path.is_file():
        raise RuntimeError(f"study_report.py did not write {output_path}")

    paired_tasks = validate_study_analysis(output_path, snapshot.spec)
    return StepOutcome(
        step_name="stage_metrics",
        status="reversible",
        details=f"wrote {output_path.name} ({paired_tasks} paired tasks)",
        artifacts=(
            str(output_path),
            str(staged_spec),
            str(staged_receipts),
        ),
    )


def validate_study_analysis(analysis_path: Path, spec: StudySpec) -> int:
    """Verify the staged report still names the exact validated capsule."""

    try:
        analysis = json.loads(analysis_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"staged analysis is unreadable: {analysis_path}: {exc}")
    if not isinstance(analysis, dict):
        raise RuntimeError(f"staged analysis is unreadable: {analysis_path}")
    provenance = analysis.get("provenance")
    completeness = analysis.get("completeness")
    if not isinstance(provenance, dict) or not isinstance(completeness, dict):
        raise RuntimeError(
            f"staged analysis is unreadable: {analysis_path}: "
            "missing provenance/completeness"
        )
    if provenance.get("study_id") != spec.study_id:
        raise RuntimeError(
            f"staged analysis study_id={provenance.get('study_id')!r}, "
            f"expected {spec.study_id!r}"
        )
    if provenance.get("spec_hash") != spec.spec_hash:
        raise RuntimeError(
            f"staged analysis spec_hash={provenance.get('spec_hash')!r}, "
            f"expected {spec.spec_hash!r}"
        )
    paired = completeness.get("paired_tasks")
    declared = completeness.get("declared_tasks")
    excluded = completeness.get("excluded_tasks")
    if not isinstance(paired, int) or paired < 1:
        raise RuntimeError("staged analysis has no paired tasks")
    if paired != declared or excluded:
        raise RuntimeError(
            "staged analysis is incomplete: paired_tasks must equal "
            "declared_tasks and excluded_tasks must be empty"
        )
    return paired
