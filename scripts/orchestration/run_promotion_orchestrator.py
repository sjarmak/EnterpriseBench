#!/usr/bin/env python3
"""Atomically promote one validated benchmark capsule.

The pipeline validates, stages, and publishes a named capsule with LIFO
rollback and failure forensics. Validation-only mode performs no writes, and
resume mode always re-runs the read-only validation gates.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

if __package__:
    from .promotion_cli import VALID_TARGET_STATES, build_context, main  # noqa: F401
    from .promotion_capsule import (
        PUBLICATION_FILES,
        assert_analysis_tools_unchanged as _assert_analysis_tools_unchanged,
        assert_capsule_source_unchanged as _assert_capsule_source_unchanged,
        capsule_snapshot as _capsule_snapshot,
        declared_task_tomls as _declared_task_tomls,
        stage_markdown_report as _stage_markdown_report,
        stage_metrics as _stage_capsule_metrics,
        validate_declared_input_provenance as _validate_declared_input_provenance,
        validate_staged_study_analysis as _validate_staged_study_analysis,
        validate_staged_publication as _validate_staged_publication,
        validate_promotion_seal as _validate_promotion_seal,
        validate_inputs as _step_validate_inputs,
    )
    from .publication_fs import (
        ensure_staging_directory as _ensure_safe_staging_dir,
        final_publication_exists as _final_publication_exists,
        freeze_staged_publication as _freeze_staged_publication,
        lock_final_publication_directory as _lock_final_publication_directory,
        quarantine_staging_publication as _quarantine_staging_publication,
        read_publication_artifact as _read_publication_artifact,
        read_registry_source as _read_registry_source,
        rename_final_to_staging as _rename_final_to_staging,
        rename_staging_to_final as _rename_staging_to_final,
        staging_publication_exists as _staging_publication_exists,
        thaw_publication as _thaw_publication,
        validate_frozen_publication as _validate_frozen_publication,
        validate_publication_identity as _validate_publication_identity,
        write_forensics_artifacts as _write_forensics_artifacts,
        write_registry_source as _write_registry_source,
        write_staged_artifact as _write_staged_artifact,
    )
    from .promotion_types import (
        CapsuleSnapshot,
        PromotionContext,
        PromotionReport,
        Step,
        StepOutcome,
    )
else:
    from promotion_cli import (  # noqa: E402, F401
        VALID_TARGET_STATES,
        build_context,
        main,
    )
    from promotion_capsule import (  # noqa: E402
        PUBLICATION_FILES,
        assert_analysis_tools_unchanged as _assert_analysis_tools_unchanged,
        assert_capsule_source_unchanged as _assert_capsule_source_unchanged,
        capsule_snapshot as _capsule_snapshot,
        declared_task_tomls as _declared_task_tomls,
        stage_markdown_report as _stage_markdown_report,
        stage_metrics as _stage_capsule_metrics,
        validate_declared_input_provenance as _validate_declared_input_provenance,
        validate_staged_study_analysis as _validate_staged_study_analysis,
        validate_staged_publication as _validate_staged_publication,
        validate_promotion_seal as _validate_promotion_seal,
        validate_inputs as _step_validate_inputs,
    )
    from publication_fs import (  # noqa: E402
        ensure_staging_directory as _ensure_safe_staging_dir,
        final_publication_exists as _final_publication_exists,
        freeze_staged_publication as _freeze_staged_publication,
        lock_final_publication_directory as _lock_final_publication_directory,
        quarantine_staging_publication as _quarantine_staging_publication,
        read_publication_artifact as _read_publication_artifact,
        read_registry_source as _read_registry_source,
        rename_final_to_staging as _rename_final_to_staging,
        rename_staging_to_final as _rename_staging_to_final,
        staging_publication_exists as _staging_publication_exists,
        thaw_publication as _thaw_publication,
        validate_frozen_publication as _validate_frozen_publication,
        validate_publication_identity as _validate_publication_identity,
        write_forensics_artifacts as _write_forensics_artifacts,
        write_registry_source as _write_registry_source,
        write_staged_artifact as _write_staged_artifact,
    )
    from promotion_types import (  # noqa: E402
        CapsuleSnapshot,
        PromotionContext,
        PromotionReport,
        Step,
        StepOutcome,
    )

from eb_verify.redact import redact as _redact, safe_detail as _safe_detail  # noqa: E402

# Maximum failure-class string length retained for forensics; trimming keeps
# the forensics JSON readable when callers attach long stderr blobs.
MAX_ERROR_DETAIL_LEN = 4_000

MAX_SAFE_RESUME_STEP = 5


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
    """Build the exact validated named capsule's report into staging."""

    return _stage_capsule_metrics(ctx)


def _step_stage_charts(ctx: PromotionContext) -> StepOutcome:
    """Confirm capsule charts are intentionally omitted."""
    if ctx.dry_run:
        return StepOutcome(
            step_name="stage_charts",
            status="dry_run",
            details="would generate charts into staging",
        )

    _ensure_safe_staging_dir(ctx, create=False)
    try:
        analysis = json.loads(
            _read_publication_artifact(ctx, "score_analysis.json").decode()
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("stage_charts: staged analysis is unreadable") from exc
    if isinstance(analysis, dict) and "provenance" in analysis:
        return StepOutcome(
            step_name="stage_charts",
            status="skipped",
            details="capsule report is promoted as auditable JSON; legacy charts skipped",
        )
    raise RuntimeError(
        "stage_charts: legacy unsealed analysis is not publication eligible"
    )


def _step_stage_report(ctx: PromotionContext) -> StepOutcome:
    """Generate the markdown report into the staging directory."""
    if ctx.dry_run:
        return StepOutcome(
            step_name="stage_report",
            status="dry_run",
            details="would generate report.md into staging",
        )

    _ensure_safe_staging_dir(ctx, create=False)
    snapshot = _capsule_snapshot(ctx)
    report_path = _stage_markdown_report(
        ctx,
        snapshot,
        console_url="../../../rootcause_console.html",
    )
    return StepOutcome(
        step_name="stage_report",
        status="reversible",
        details=f"wrote and sealed {report_path.name}",
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

    _ensure_safe_staging_dir(ctx, create=False)
    if _final_publication_exists(ctx):
        raise RuntimeError(
            "atomic_publish: final dir already exists "
            f"(refusing to overwrite): {ctx.final_dir}"
        )

    snapshot = _capsule_snapshot(ctx)
    _validate_staging_for_publish(ctx, snapshot)
    frozen_identity = _freeze_staged_publication(ctx, PUBLICATION_FILES)
    try:
        _rename_staging_to_final(ctx, frozen_identity, os.rename)
    except BaseException as exc:
        _thaw_publication(ctx, location="staging")
        raise RuntimeError("atomic publication rename failed") from exc
    try:
        _validate_final_publication(ctx, snapshot, frozen_identity)
    except BaseException:
        rollback_path = _rename_final_to_staging(ctx)
        if rollback_path == ctx.staging_dir:
            _thaw_publication(ctx, location="staging")
        raise
    return StepOutcome(
        step_name="atomic_publish",
        status="reversible",
        details=f"published to {ctx.final_dir}",
        artifacts=(str(ctx.final_dir),),
    )


def _validate_staging_for_publish(
    ctx: PromotionContext,
    snapshot: CapsuleSnapshot,
) -> None:
    """Revalidate all immutable staging inputs immediately before rename."""

    _assert_capsule_source_unchanged(ctx, snapshot)
    _assert_analysis_tools_unchanged(ctx, snapshot)
    _validate_declared_input_provenance(ctx, snapshot)
    staged_sources = {
        "study_spec.json": snapshot.spec_source,
        "receipts.jsonl": snapshot.receipts_source,
        "final_manifest.json": snapshot.task_manifest_source,
        "analysis_plan.json": snapshot.analysis_plan_source,
    }
    try:
        staged_unchanged = all(
            _read_publication_artifact(ctx, name) == expected
            for name, expected in staged_sources.items()
        )
    except RuntimeError as exc:
        raise RuntimeError(f"staged capsule seal is unreadable: {exc}") from exc
    if not staged_unchanged:
        raise RuntimeError("staged capsule seal does not match validated inputs")
    _validate_staged_publication(ctx)
    _validate_staged_study_analysis(
        ctx,
        snapshot.spec,
        snapshot.analysis_contract,
    )
    _validate_promotion_seal(ctx, snapshot)


def _validate_final_publication(
    ctx: PromotionContext,
    snapshot: CapsuleSnapshot,
    frozen_identity: tuple[int, int],
) -> None:
    """Lock and revalidate the renamed tree before returning success."""

    _validate_publication_identity(
        ctx,
        frozen_identity,
        location="final",
    )
    _lock_final_publication_directory(ctx)
    _validate_frozen_publication(
        ctx,
        PUBLICATION_FILES,
        location="final",
    )
    _validate_staged_study_analysis(
        ctx,
        snapshot.spec,
        snapshot.analysis_contract,
        location="final",
    )
    _validate_promotion_seal(ctx, snapshot, location="final")
    _validate_publication_identity(
        ctx,
        frozen_identity,
        location="final",
    )


def _step_update_registry(ctx: PromotionContext) -> StepOutcome:
    """Append an entry to the official-runs registry atomically."""
    if ctx.dry_run:
        return StepOutcome(
            step_name="update_registry",
            status="dry_run",
            details=f"would update {ctx.registry_path.name}",
        )

    source = _read_registry_source(ctx)
    if source is not None:
        try:
            registry = json.loads(source)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Registry is not valid UTF-8 JSON") from exc
        if not isinstance(registry, dict):
            raise RuntimeError(f"Registry is not a JSON object: {ctx.registry_path}")
    else:
        registry = {
            "_description": ("Index of promoted EnterpriseBench official runs."),
            "entries": [],
        }

    entries = registry.get("entries", [])
    if not isinstance(entries, list) or any(
        not isinstance(value, dict) for value in entries
    ):
        raise RuntimeError("Registry 'entries' is not an object list")

    entry = {
        "run_id": ctx.run_id,
        "target_state": ctx.target_state,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "final_dir": str(ctx.final_dir.relative_to(ctx.repo_root)),
    }
    # Keep entries sorted by promoted_at ascending so the file diff is stable.
    entries = [e for e in entries if e.get("run_id") != ctx.run_id]
    entries.append(entry)
    updated = {**registry, "entries": entries}
    _write_registry_source(
        ctx,
        (json.dumps(updated, indent=2) + "\n").encode(),
    )
    return StepOutcome(
        step_name="update_registry",
        status="forward_only",
        details="appended registry entry",
        artifacts=(str(ctx.registry_path),),
    )


# ---------------------------------------------------------------------------
# Rollback hooks
# ---------------------------------------------------------------------------


def _rollback_noop(_ctx: PromotionContext) -> None:
    return None


def _rollback_staging(ctx: PromotionContext) -> None:
    """Quarantine the staging directory if it exists.

    Idempotent — safe to call when the step never ran or was already rolled
    back.
    """
    if _staging_publication_exists(ctx):
        _thaw_publication(ctx, location="staging")
        _quarantine_staging_publication(ctx)


def _rollback_atomic_publish(ctx: PromotionContext) -> None:
    """Move the published directory back to staging, if still possible."""
    if _final_publication_exists(ctx):
        rollback_path = _rename_final_to_staging(ctx)
        if rollback_path == ctx.staging_dir:
            _thaw_publication(ctx, location="staging")


def build_default_pipeline() -> list[Step]:
    """Return the canonical ordered pipeline.

    The ordering matters: each later step depends on the artefacts produced
    by earlier steps. ``--resume-from-step`` indices line up with this list
    (1-based).
    """
    return [
        Step(
            "validate_inputs",
            _step_validate_inputs,
            _rollback_noop,
            bind_capsule=True,
        ),
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
        Step(
            "update_registry",
            _step_update_registry,
            _rollback_noop,
            reversible=False,
        ),
    ]


def _forensics_sources(
    ctx: PromotionContext,
    completed: list[tuple[Step, StepOutcome]],
    exc: BaseException,
) -> dict[str, bytes]:
    context = {
        "run_id": ctx.run_id,
        "target_state": ctx.target_state,
        "raw_run_dir": str(ctx.raw_run_dir),
        "staging_dir": str(ctx.staging_dir),
        "final_dir": str(ctx.final_dir),
        "registry_path": str(ctx.registry_path),
        "dry_run": ctx.dry_run,
        "resume_from": ctx.resume_from,
    }
    error = {
        "type": type(exc).__name__,
        "message": _safe_detail(exc)[:MAX_ERROR_DETAIL_LEN],
    }
    outcomes = [asdict(outcome) for _step, outcome in completed]
    return {
        "context.json": _safe_json_bytes(context),
        "error.json": _safe_json_bytes(error),
        "completed_steps.json": _safe_json_bytes(outcomes),
    }


def _safe_json_bytes(value: object) -> bytes:
    return (json.dumps(_redact_json_value(value), indent=2) + "\n").encode()


def _redact_json_value(value: object) -> object:
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, dict):
        return {
            _redact(str(key)): _redact_json_value(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_json_value(item) for item in value]
    return value


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
                if index < self._ctx.resume_from and not step.name.startswith(
                    "validate"
                ):
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
                if step.bind_capsule and self._ctx.capsule_snapshot is None:
                    self._ctx = replace(
                        self._ctx,
                        capsule_snapshot=_capsule_snapshot(self._ctx),
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
            safe_error = _safe_detail(exc)
            logger.error(
                "[%s] promotion failed during step execution: %s",
                self._ctx.run_id,
                safe_error,
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
                error=safe_error[:MAX_ERROR_DETAIL_LEN],
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
                    _safe_detail(exc),
                )

    def _write_progress(self, completed: list[tuple[Step, StepOutcome]]) -> None:
        completed_names = {outcome.step_name for _step, outcome in completed}
        if (
            "stage_metrics" not in completed_names
            or "atomic_publish" in completed_names
            or not self._ctx.staging_dir.exists()
        ):
            return
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
        _write_staged_artifact(
            self._ctx,
            "_progress.json",
            (json.dumps(payload, indent=2) + "\n").encode(),
            replace=True,
        )

    def _write_forensics(
        self,
        completed: list[tuple[Step, StepOutcome]],
        exc: BaseException,
    ) -> Optional[Path]:
        try:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            return _write_forensics_artifacts(
                self._ctx,
                f"{self._ctx.run_id}_{stamp}",
                _forensics_sources(self._ctx, completed, exc),
            )
        except Exception as forensic_exc:  # noqa: BLE001
            logger.error(
                "[%s] failed to write forensics: %s",
                self._ctx.run_id,
                _safe_detail(forensic_exc),
            )
            return None


if __name__ == "__main__":
    sys.exit(main())
