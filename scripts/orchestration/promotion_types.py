"""Immutable data contracts for the run-promotion pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from eb_study import StudyCapsule, StudySpec


@dataclass(frozen=True)
class StepOutcome:
    """Immutable record of a single step execution."""

    step_name: str
    status: str
    details: str = ""
    artifacts: tuple[str, ...] = ()
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class CapsuleSnapshot:
    """The exact capsule bytes validated by one promotion invocation."""

    spec_source: str
    receipts_source: str
    spec: StudySpec
    capsule: StudyCapsule


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
    capsule_snapshot: Optional[CapsuleSnapshot] = None


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
            "steps": [asdict(step) for step in self.steps],
        }


@dataclass
class Step:
    """One executable pipeline step and its rollback contract."""

    name: str
    execute: Callable[[PromotionContext], StepOutcome]
    rollback: Callable[[PromotionContext], None] = field(default=lambda _ctx: None)
    reversible: bool = True
    bind_capsule: bool = False
