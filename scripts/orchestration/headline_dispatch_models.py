"""Immutable value objects for headline dispatch planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from eb_study import StudySpec
from headline_dispatch_policy import V3DispatchControls


@dataclass(frozen=True)
class DispatchSlot:
    task_id: str
    arm: str
    repetition: int
    attempt: int
    agent_account: int
    judge_account: int
    task_toml: Path
    output_dir: Path


@dataclass(frozen=True)
class DispatchPlan:
    path: Path
    spec_path: Path
    manifest_path: Path
    preflight_evidence_path: Path
    receipts_path: Path
    spec: StudySpec
    slots: tuple[DispatchSlot, ...]
    execution: Mapping[str, Any]
    sample_attempts: int
    forecast_outer_spend_usd: float
    empirical_envelope_usd: float
    per_slot_envelope_usd: float
    study_authorization_ceiling_usd: float
    authorization_ceiling_usd: float
    paid_dispatch_authorized: bool
    authorization_reference: str | None
    v3_controls: V3DispatchControls | None
