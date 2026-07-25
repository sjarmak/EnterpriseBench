#!/usr/bin/env python3
"""Atomic run-promotion orchestrator for EnterpriseBench.

Coordinates the multi-step promotion of a benchmark run from raw
``results/runs/<run_id>/`` artefacts into the durable, official-run state at
``results/official_runs/<run_id>/``.

The promotion sequence has historically been a chain of ad-hoc Make targets
(``analyze`` → ``charts`` → ``report`` → manual copy), with no transactional
guarantee. A mid-flight failure leaves the official-runs tree in a partial
state — the same defect documented in CSB-BUG-011 (``docs/csb_bugs.md``).

This orchestrator wraps the sequence in:

* a stage → publish split (everything writes to a sibling staging dir; the
  final move is a single ``os.rename``);
* per-step rollback hooks executed LIFO when any step raises;
* a forensic snapshot of partial state on failure;
* ``--validate-only`` to gate read-only checks before any write happens;
* ``--resume-from-step N`` to pick up after a transient failure without
  re-running the upstream validators.

Usage::

    python3 scripts/orchestration/run_promotion_orchestrator.py \
        --run-id 20260429_001 --target-state official

    python3 scripts/orchestration/run_promotion_orchestrator.py \
        --run-id 20260429_001 --validate-only

    python3 scripts/orchestration/run_promotion_orchestrator.py \
        --run-id 20260429_001 --resume-from-step 5

The class :class:`RunPromotionOrchestrator` is also importable for callers
(CI, mayor-driven dispatch) that want to invoke promotion programmatically.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_RAW_RUNS_ROOT = REPO_ROOT / "results" / "runs"
DEFAULT_OFFICIAL_RUNS_ROOT = REPO_ROOT / "results" / "official_runs"
sys.path.insert(0, str(REPO_ROOT / "lib"))

from eb_study import CapsuleError, StudyCapsule, StudySpec  # noqa: E402

# Maximum failure-class string length retained for forensics; trimming keeps
# the forensics JSON readable when callers attach long stderr blobs.
MAX_ERROR_DETAIL_LEN = 4_000

VALID_TARGET_STATES = frozenset({"official", "candidate"})
MAX_SAFE_RESUME_STEP = 5
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepOutcome:
    """Immutable record of a single step execution.

    A ``status`` of ``"reversible"`` means the step performed work that the
    accompanying rollback hook can fully undo. ``"forward_only"`` means the
    step succeeded but its effect cannot be reversed by software (e.g.
    side-effects on external systems); the orchestrator will not roll it back
    automatically — callers must use ``--resume-from-step`` to retry.
    """

    step_name: str
    status: str  # "reversible" | "forward_only" | "skipped" | "dry_run" | "failed"
    details: str = ""
    artifacts: tuple[str, ...] = ()
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class PromotionContext:
    """Immutable execution context for a promotion attempt."""

    run_id: str
    target_state: str
    repo_root: Path
    study_report_path: Path
    raw_run_dir: Path
    spec_path: Path
    receipts_path: Path
    staging_dir: Path
    final_dir: Path
    registry_path: Path
    forensics_dir: Path
    dry_run: bool
    resume_from: int


@dataclass(frozen=True)
class PromotionReport:
    """Top-level outcome of an orchestrator invocation."""

    run_id: str
    target_state: str
    started_at: str
    finished_at: str
    succeeded: bool
    steps: tuple[StepOutcome, ...]
    forensics_path: Optional[str] = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "target_state": self.target_state,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "succeeded": self.succeeded,
            "forensics_path": self.forensics_path,
            "error": self.error,
            "steps": [asdict(s) for s in self.steps],
        }


# ---------------------------------------------------------------------------
# Step protocol
# ---------------------------------------------------------------------------


@dataclass
class Step:
    """A single step in the promotion pipeline.

    ``execute`` performs the work and is responsible for raising on failure.
    ``rollback`` is called by the orchestrator when a *later* step fails; it
    must be idempotent and tolerate being called even when the step never ran.

    ``reversible=False`` marks steps whose effect cannot be undone in
    software (currently none of the implemented steps need this, but the
    field is reserved for future external-system steps).
    """

    name: str
    execute: Callable[[PromotionContext], StepOutcome]
    rollback: Callable[[PromotionContext], None] = field(default=lambda _ctx: None)
    reversible: bool = True


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def _step_validate_inputs(ctx: PromotionContext) -> StepOutcome:
    """Validate the exact named Study Capsule that promotion will consume.

    No directory discovery occurs here or downstream. The spec must name the
    requested run, every receipt must validate against its hash, and every
    declared task/arm/repetition slot must have a comparable valid trial.
    """
    if not ctx.raw_run_dir.is_dir():
        raise FileNotFoundError(f"Raw run directory not found: {ctx.raw_run_dir}")

    try:
        spec = StudySpec.load(ctx.spec_path)
    except CapsuleError as exc:
        raise ValueError(f"invalid study spec: {exc}") from exc
    if spec.study_id != ctx.run_id:
        raise ValueError(
            f"study_id {spec.study_id!r} does not match promoted run {ctx.run_id!r}"
        )

    try:
        capsule = StudyCapsule.load(ctx.spec_path, ctx.receipts_path)
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


def _run_subprocess(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run a subprocess and return (rc, stdout, stderr) without raising."""
    proc = subprocess.run(  # noqa: S603 — args are constructed internally
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _step_validate_tasks_preflight(ctx: PromotionContext) -> StepOutcome:
    """Run the read-only preflight validator.

    Failure here means the underlying task definitions are not promotable;
    the orchestrator aborts before any artefact is written.
    """
    cmd = [
        sys.executable,
        str(ctx.repo_root / "scripts" / "validate_tasks_preflight.py"),
        "--json",
    ]
    rc, _stdout, stderr = _run_subprocess(cmd, ctx.repo_root)
    if rc != 0:
        raise RuntimeError(
            f"validate_tasks_preflight.py exited {rc}: {stderr[-MAX_ERROR_DETAIL_LEN:]}"
        )
    return StepOutcome(
        step_name="validate_tasks_preflight",
        status="reversible",
        details="preflight ok",
    )


def _step_validate_crnt(ctx: PromotionContext) -> StepOutcome:
    """Validate Cross-Repo Necessity Test for multi-repo tasks."""
    task_tomls = _declared_task_tomls(ctx)
    validator = ctx.repo_root / "scripts" / "validation" / "crnt_validator.py"
    for task_toml in task_tomls:
        cmd = [sys.executable, str(validator), str(task_toml), "--json"]
        rc, _stdout, stderr = _run_subprocess(cmd, ctx.repo_root)
        if rc != 0:
            raise RuntimeError(
                f"crnt_validator.py exited {rc} for {task_toml}: "
                f"{stderr[-MAX_ERROR_DETAIL_LEN:]}"
            )
    return StepOutcome(
        step_name="validate_crnt",
        status="reversible",
        details=f"crnt ok ({len(task_tomls)} declared tasks)",
    )


def _declared_task_tomls(ctx: PromotionContext) -> tuple[Path, ...]:
    """Resolve every spec task ID to exactly one benchmark task.toml."""

    spec = StudySpec.load(ctx.spec_path)
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


def _step_validate_expected_solutions(ctx: PromotionContext) -> StepOutcome:
    """Validate expected_solution.json files."""
    cmd = [
        sys.executable,
        str(
            ctx.repo_root / "scripts" / "validation" / "validate_expected_solutions.py"
        ),
        str(ctx.repo_root / "benchmarks"),
    ]
    rc, _stdout, stderr = _run_subprocess(cmd, ctx.repo_root)
    if rc != 0:
        raise RuntimeError(
            f"validate_expected_solutions.py exited {rc}: "
            f"{stderr[-MAX_ERROR_DETAIL_LEN:]}"
        )
    return StepOutcome(
        step_name="validate_expected_solutions",
        status="reversible",
        details="expected_solutions ok",
    )


def _step_stage_metrics(ctx: PromotionContext) -> StepOutcome:
    """Build the named capsule's report into staging.

    ``study_report.py`` accepts only an explicit spec and receipt log. It has no
    recursive discovery fallback, so historical, smoke, sibling, and
    quarantined result directories are outside the input boundary.
    """
    if ctx.dry_run:
        return StepOutcome(
            step_name="stage_metrics",
            status="dry_run",
            details="would aggregate metrics into staging",
        )

    ctx.staging_dir.mkdir(parents=True, exist_ok=True)
    output_path = ctx.staging_dir / "score_analysis.json"
    staged_spec = ctx.staging_dir / "study_spec.json"
    staged_receipts = ctx.staging_dir / "receipts.jsonl"
    shutil.copy2(ctx.spec_path, staged_spec)
    shutil.copy2(ctx.receipts_path, staged_receipts)
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
    rc, _stdout, stderr = _run_subprocess(cmd, ctx.repo_root)
    if rc != 0:
        raise RuntimeError(
            f"study_report.py exited {rc}: {stderr[-MAX_ERROR_DETAIL_LEN:]}"
        )
    if not output_path.is_file():
        raise RuntimeError(f"study_report.py did not write {output_path}")

    paired_tasks = _validate_study_analysis(output_path, ctx, staged_spec)

    return StepOutcome(
        step_name="stage_metrics",
        status="reversible",
        details=f"wrote {output_path.name} ({paired_tasks} paired tasks)",
        artifacts=(
            str(output_path),
            str(ctx.staging_dir / "study_spec.json"),
            str(ctx.staging_dir / "receipts.jsonl"),
        ),
    )


def _validate_study_analysis(
    analysis_path: Path,
    ctx: PromotionContext,
    spec_path: Path,
) -> int:
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
    spec = StudySpec.load(spec_path)
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


def _step_stage_charts(ctx: PromotionContext) -> StepOutcome:
    """Generate charts into the staging directory."""
    if ctx.dry_run:
        return StepOutcome(
            step_name="stage_charts",
            status="dry_run",
            details="would generate charts into staging",
        )

    charts_dir = ctx.staging_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = ctx.staging_dir / "score_analysis.json"
    if not analysis_path.is_file():
        raise RuntimeError(f"stage_charts: prerequisite missing: {analysis_path}")
    analysis = json.loads(analysis_path.read_text())
    if isinstance(analysis, dict) and "provenance" in analysis:
        return StepOutcome(
            step_name="stage_charts",
            status="skipped",
            details="capsule report is promoted as auditable JSON; legacy charts skipped",
        )
    cmd = [
        sys.executable,
        str(ctx.repo_root / "scripts" / "generate_charts.py"),
        "--analysis",
        str(analysis_path),
        "--output-dir",
        str(charts_dir),
    ]
    rc, _stdout, stderr = _run_subprocess(cmd, ctx.repo_root)
    if rc != 0:
        raise RuntimeError(
            f"generate_charts.py exited {rc}: {stderr[-MAX_ERROR_DETAIL_LEN:]}"
        )
    chart_files = sorted(p.name for p in charts_dir.glob("*.png"))
    return StepOutcome(
        step_name="stage_charts",
        status="reversible",
        details=f"generated {len(chart_files)} charts",
        artifacts=tuple(str(charts_dir / n) for n in chart_files),
    )


def _step_stage_report(ctx: PromotionContext) -> StepOutcome:
    """Generate the markdown report into the staging directory."""
    if ctx.dry_run:
        return StepOutcome(
            step_name="stage_report",
            status="dry_run",
            details="would generate report.md into staging",
        )

    report_path = ctx.staging_dir / "report.md"
    analysis_path = ctx.staging_dir / "score_analysis.json"
    charts_dir = ctx.staging_dir / "charts"
    if not analysis_path.is_file():
        raise RuntimeError("stage_report: prerequisite missing (analysis)")
    analysis = json.loads(analysis_path.read_text())
    if isinstance(analysis, dict) and "provenance" in analysis:
        return StepOutcome(
            step_name="stage_report",
            status="skipped",
            details="capsule report is promoted as auditable JSON; legacy markdown skipped",
        )
    if not charts_dir.is_dir():
        raise RuntimeError("stage_report: prerequisite missing (charts)")

    cmd = [
        sys.executable,
        str(ctx.repo_root / "scripts" / "generate_report.py"),
        "--analysis",
        str(analysis_path),
        "--charts-dir",
        str(charts_dir),
        "--output",
        str(report_path),
    ]
    rc, _stdout, stderr = _run_subprocess(cmd, ctx.repo_root)
    if rc != 0:
        raise RuntimeError(
            f"generate_report.py exited {rc}: {stderr[-MAX_ERROR_DETAIL_LEN:]}"
        )
    if not report_path.is_file():
        raise RuntimeError(f"generate_report.py did not write {report_path}")
    return StepOutcome(
        step_name="stage_report",
        status="reversible",
        details=f"wrote {report_path.name}",
        artifacts=(str(report_path),),
    )


def _step_atomic_publish(ctx: PromotionContext) -> StepOutcome:
    """Atomically rename the staging dir to its final location.

    Uses ``os.rename`` which is atomic on POSIX as long as both paths are
    on the same filesystem. The staging directory is created as a sibling
    of the final directory specifically to satisfy that invariant.
    """
    if ctx.dry_run:
        return StepOutcome(
            step_name="atomic_publish",
            status="dry_run",
            details=f"would rename {ctx.staging_dir} -> {ctx.final_dir}",
        )

    if not ctx.staging_dir.is_dir():
        raise RuntimeError(f"atomic_publish: staging dir missing: {ctx.staging_dir}")
    if ctx.final_dir.exists():
        raise RuntimeError(
            f"atomic_publish: final dir already exists (refusing to "
            f"overwrite): {ctx.final_dir}"
        )

    ctx.final_dir.parent.mkdir(parents=True, exist_ok=True)
    os.rename(ctx.staging_dir, ctx.final_dir)
    return StepOutcome(
        step_name="atomic_publish",
        status="reversible",
        details=f"published to {ctx.final_dir}",
        artifacts=(str(ctx.final_dir),),
    )


def _step_update_registry(ctx: PromotionContext) -> StepOutcome:
    """Append an entry to the official-runs registry atomically.

    The registry is a JSON file rewritten via tmp + rename. The previous
    contents are kept on disk as ``<registry>.bak`` only for the duration
    of this step so the rollback hook can restore them on failure of a
    later step (currently no later step exists, but the contract is
    preserved for future extension).
    """
    if ctx.dry_run:
        return StepOutcome(
            step_name="update_registry",
            status="dry_run",
            details=f"would update {ctx.registry_path.name}",
        )

    ctx.registry_path.parent.mkdir(parents=True, exist_ok=True)
    if ctx.registry_path.is_file():
        registry = json.loads(ctx.registry_path.read_text())
        if not isinstance(registry, dict):
            raise RuntimeError(f"Registry is not a JSON object: {ctx.registry_path}")
        backup = ctx.registry_path.with_suffix(ctx.registry_path.suffix + ".bak")
        backup.write_text(ctx.registry_path.read_text())
    else:
        registry = {
            "_description": ("Index of promoted EnterpriseBench official runs."),
            "entries": [],
        }

    entries = registry.get("entries", [])
    if not isinstance(entries, list):
        raise RuntimeError("Registry 'entries' is not a list")

    entry = {
        "run_id": ctx.run_id,
        "target_state": ctx.target_state,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "final_dir": str(ctx.final_dir.relative_to(ctx.repo_root)),
    }
    # Keep entries sorted by promoted_at ascending so the file diff is stable.
    entries = [e for e in entries if e.get("run_id") != ctx.run_id]
    entries.append(entry)
    registry["entries"] = entries

    tmp_path = ctx.registry_path.with_suffix(ctx.registry_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(registry, indent=2) + "\n")
    os.rename(tmp_path, ctx.registry_path)
    return StepOutcome(
        step_name="update_registry",
        status="reversible",
        details="appended registry entry",
        artifacts=(str(ctx.registry_path),),
    )


# ---------------------------------------------------------------------------
# Rollback hooks
# ---------------------------------------------------------------------------


def _rollback_noop(_ctx: PromotionContext) -> None:
    return None


def _rollback_staging(ctx: PromotionContext) -> None:
    """Remove the staging directory if it exists.

    Idempotent — safe to call when the step never ran or was already rolled
    back.
    """
    if ctx.staging_dir.is_dir():
        shutil.rmtree(ctx.staging_dir)


def _rollback_atomic_publish(ctx: PromotionContext) -> None:
    """Move the published directory back to staging, if still possible."""
    if ctx.final_dir.is_dir() and not ctx.staging_dir.exists():
        ctx.staging_dir.parent.mkdir(parents=True, exist_ok=True)
        os.rename(ctx.final_dir, ctx.staging_dir)


def _rollback_registry(ctx: PromotionContext) -> None:
    """Restore the registry from its ``.bak`` snapshot if present."""
    backup = ctx.registry_path.with_suffix(ctx.registry_path.suffix + ".bak")
    if backup.is_file():
        os.replace(backup, ctx.registry_path)


# ---------------------------------------------------------------------------
# Step pipeline registration
# ---------------------------------------------------------------------------


def build_default_pipeline() -> list[Step]:
    """Return the canonical ordered pipeline.

    The ordering matters: each later step depends on the artefacts produced
    by earlier steps. ``--resume-from-step`` indices line up with this list
    (1-based).
    """
    return [
        Step("validate_inputs", _step_validate_inputs, _rollback_noop),
        Step(
            "validate_tasks_preflight",
            _step_validate_tasks_preflight,
            _rollback_noop,
        ),
        Step("validate_crnt", _step_validate_crnt, _rollback_noop),
        Step(
            "validate_expected_solutions",
            _step_validate_expected_solutions,
            _rollback_noop,
        ),
        Step("stage_metrics", _step_stage_metrics, _rollback_staging),
        Step("stage_charts", _step_stage_charts, _rollback_staging),
        Step("stage_report", _step_stage_report, _rollback_staging),
        Step(
            "atomic_publish",
            _step_atomic_publish,
            _rollback_atomic_publish,
        ),
        Step("update_registry", _step_update_registry, _rollback_registry),
    ]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class RunPromotionOrchestrator:
    """Coordinate atomic promotion of a benchmark run.

    The orchestrator is intentionally thin: it sequences a list of
    :class:`Step` objects, captures their outcomes, and runs rollback hooks
    in LIFO order on failure. All policy lives in the steps themselves.
    """

    def __init__(
        self,
        ctx: PromotionContext,
        pipeline: Optional[list[Step]] = None,
    ) -> None:
        if ctx.target_state not in VALID_TARGET_STATES:
            raise ValueError(
                f"Invalid target_state {ctx.target_state!r}; "
                f"expected one of {sorted(VALID_TARGET_STATES)}"
            )
        if ctx.resume_from < 0:
            raise ValueError("resume_from must be >= 0")
        if ctx.resume_from > MAX_SAFE_RESUME_STEP:
            raise ValueError(
                f"resume_from must be <= {MAX_SAFE_RESUME_STEP}; later steps "
                "would skip capsule revalidation"
            )

        self._ctx = ctx
        self._pipeline = list(pipeline or build_default_pipeline())

    # ------------------------------------------------------------------ API

    @property
    def context(self) -> PromotionContext:
        return self._ctx

    @property
    def pipeline(self) -> list[Step]:
        return list(self._pipeline)

    def run(self, *, validate_only: bool = False) -> PromotionReport:
        """Execute the pipeline.

        ``validate_only`` short-circuits after the read-only validators
        (the first contiguous block of validation steps starting at the
        head of the pipeline). It never touches the staging or final
        directories.
        """
        started = datetime.now(timezone.utc).isoformat()
        completed: list[tuple[Step, StepOutcome]] = []

        try:
            for index, step in enumerate(self._pipeline, start=1):
                if index < self._ctx.resume_from:
                    completed.append(
                        (
                            step,
                            StepOutcome(
                                step_name=step.name,
                                status="skipped",
                                details=(
                                    f"skipped via --resume-from-step "
                                    f"{self._ctx.resume_from}"
                                ),
                            ),
                        )
                    )
                    continue

                if validate_only and not step.name.startswith("validate"):
                    # Stop the run after the read-only block; we are not
                    # going to mutate anything.
                    break

                logger.info(
                    "[%s] step %d/%d %s",
                    self._ctx.run_id,
                    index,
                    len(self._pipeline),
                    step.name,
                )
                start = time.monotonic()
                outcome = step.execute(self._ctx)
                duration = time.monotonic() - start
                outcome = StepOutcome(
                    step_name=outcome.step_name,
                    status=outcome.status,
                    details=outcome.details,
                    artifacts=outcome.artifacts,
                    duration_seconds=duration,
                )
                completed.append((step, outcome))

                # Persist progress after every step so a later --resume can
                # see where we got to.
                if not validate_only and not self._ctx.dry_run:
                    self._write_progress(completed)

            report = PromotionReport(
                run_id=self._ctx.run_id,
                target_state=self._ctx.target_state,
                started_at=started,
                finished_at=datetime.now(timezone.utc).isoformat(),
                succeeded=True,
                steps=tuple(o for _s, o in completed),
            )
            return report

        except Exception as exc:  # noqa: BLE001 — orchestrator catches all
            logger.error(
                "[%s] promotion failed during step execution: %s",
                self._ctx.run_id,
                exc,
            )
            forensics = None if validate_only else self._write_forensics(completed, exc)
            self._rollback_completed(completed)
            return PromotionReport(
                run_id=self._ctx.run_id,
                target_state=self._ctx.target_state,
                started_at=started,
                finished_at=datetime.now(timezone.utc).isoformat(),
                succeeded=False,
                steps=tuple(o for _s, o in completed),
                forensics_path=str(forensics) if forensics else None,
                error=str(exc)[:MAX_ERROR_DETAIL_LEN],
            )

    # -------------------------------------------------------------- helpers

    def _rollback_completed(self, completed: list[tuple[Step, StepOutcome]]) -> None:
        for step, outcome in reversed(completed):
            if outcome.status not in {"reversible", "forward_only"}:
                continue
            if not step.reversible:
                logger.warning(
                    "[%s] step %s marked non-reversible; skipping rollback",
                    self._ctx.run_id,
                    step.name,
                )
                continue
            try:
                step.rollback(self._ctx)
                logger.info("[%s] rolled back %s", self._ctx.run_id, step.name)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[%s] rollback of %s raised: %s",
                    self._ctx.run_id,
                    step.name,
                    exc,
                )

    def _write_progress(self, completed: list[tuple[Step, StepOutcome]]) -> None:
        if not self._ctx.staging_dir.is_dir():
            return
        progress_path = self._ctx.staging_dir / "_progress.json"
        payload = {
            "run_id": self._ctx.run_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "completed": [
                {
                    "step_name": o.step_name,
                    "status": o.status,
                    "duration_seconds": o.duration_seconds,
                }
                for _s, o in completed
            ],
        }
        tmp = progress_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        os.rename(tmp, progress_path)

    def _write_forensics(
        self,
        completed: list[tuple[Step, StepOutcome]],
        exc: BaseException,
    ) -> Optional[Path]:
        try:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            target = self._ctx.forensics_dir / f"{self._ctx.run_id}_{stamp}"
            target.mkdir(parents=True, exist_ok=True)

            (target / "context.json").write_text(
                json.dumps(
                    {
                        "run_id": self._ctx.run_id,
                        "target_state": self._ctx.target_state,
                        "raw_run_dir": str(self._ctx.raw_run_dir),
                        "staging_dir": str(self._ctx.staging_dir),
                        "final_dir": str(self._ctx.final_dir),
                        "registry_path": str(self._ctx.registry_path),
                        "dry_run": self._ctx.dry_run,
                        "resume_from": self._ctx.resume_from,
                    },
                    indent=2,
                )
                + "\n"
            )
            (target / "error.json").write_text(
                json.dumps(
                    {
                        "type": type(exc).__name__,
                        "message": str(exc)[:MAX_ERROR_DETAIL_LEN],
                    },
                    indent=2,
                )
                + "\n"
            )
            (target / "completed_steps.json").write_text(
                json.dumps(
                    [asdict(o) for _s, o in completed],
                    indent=2,
                )
                + "\n"
            )
            return target
        except Exception as forensic_exc:  # noqa: BLE001
            logger.error(
                "[%s] failed to write forensics: %s",
                self._ctx.run_id,
                forensic_exc,
            )
            return None


# ---------------------------------------------------------------------------
# Context construction helpers
# ---------------------------------------------------------------------------


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
    study_report_path: Optional[Path] = None,
) -> PromotionContext:
    repo_root = repo_root or REPO_ROOT
    if RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError(
            "run_id must be a single safe path component containing only "
            "letters, digits, '.', '_' or '-'"
        )
    raw_root = raw_runs_root or (repo_root / "results" / "runs")
    official_root = official_runs_root or (repo_root / "results" / "official_runs")
    raw_run_dir = raw_root / run_id
    return PromotionContext(
        run_id=run_id,
        target_state=target_state,
        repo_root=repo_root,
        study_report_path=(
            study_report_path
            or (repo_root / "scripts" / "analysis" / "study_report.py")
        ),
        raw_run_dir=raw_run_dir,
        spec_path=spec_path or (raw_run_dir / "study_spec.json"),
        receipts_path=receipts_path or (raw_run_dir / "receipts.jsonl"),
        staging_dir=official_root / "_staging" / run_id,
        final_dir=official_root / run_id,
        registry_path=official_root / "_registry.json",
        forensics_dir=official_root / "_failures",
        dry_run=dry_run,
        resume_from=resume_from,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
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
    parser.add_argument(
        "--run-id", required=True, help="Identifier of the run to promote"
    )
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
        "--target-state",
        default="official",
        choices=sorted(VALID_TARGET_STATES),
        help="State to promote to (default: official)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help=(
            "Run only the read-only validators; never write to the staging "
            "or final directory"
        ),
    )
    parser.add_argument(
        "--resume-from-step",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Skip steps with 1-based index < N. Use after a transient "
            "failure to pick up where the previous attempt stopped."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be executed without writing artefacts",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the promotion report as JSON to stdout",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

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
    )
    orchestrator = RunPromotionOrchestrator(ctx)
    report = orchestrator.run(validate_only=args.validate_only)

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


if __name__ == "__main__":
    sys.exit(main())
