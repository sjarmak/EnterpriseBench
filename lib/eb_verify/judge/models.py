"""Data models for the EB LLM Judge."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CheckpointJudgeInput:
    """Input for evaluating a single checkpoint via LLM judge."""

    task_id: str
    checkpoint_name: str
    agent_output: str  # full agent answer (answer.json or INCIDENT_REPORT.md)
    expected_solution: str  # curated ground truth for this checkpoint
    evaluation_criteria: list[str] = field(default_factory=list)
    checkpoint_weight: float = 1.0


@dataclass
class CheckpointJudgeResult:
    """Output from LLM judge for a single checkpoint."""

    checkpoint_name: str
    score: float  # 0.0 - 1.0
    passed: bool  # score >= pass_threshold
    reasoning: str = ""
    evidence: str = ""  # specific quotes from agent output that matched/missed
    confidence: str = "medium"  # high | medium | low
    model: str = ""
    raw_response: dict = field(default_factory=dict)


def normalize_score(val: object) -> float:
    """Clamp a value to [0.0, 1.0]."""
    try:
        f = float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, f))
