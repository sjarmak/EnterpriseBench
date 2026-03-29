"""
Weighted score computation and reward.txt generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class CheckpointResult:
    name: str
    weight: float
    passed: bool
    score: float  # 0.0–1.0 (partial credit possible)
    detail: str = ""


@dataclass
class VerificationResult:
    task_id: str
    checkpoint_results: List[CheckpointResult] = field(default_factory=list)
    artifact_results: List[dict] = field(default_factory=list)
    total_score: float = 0.0

    def summary(self) -> str:
        lines = [f"task: {self.task_id}", f"total_score: {self.total_score:.4f}", ""]
        lines.append("checkpoints:")
        for cr in self.checkpoint_results:
            status = "PASS" if cr.passed else "FAIL"
            lines.append(
                f"  - {cr.name}: {status} (score={cr.score:.2f}, weight={cr.weight:.2f})"
            )
            if cr.detail:
                lines.append(f"    detail: {cr.detail}")
        if self.artifact_results:
            lines.append("")
            lines.append("artifacts:")
            for ar in self.artifact_results:
                status = "VALID" if ar.get("valid") else "INVALID"
                lines.append(f"  - {ar.get('type', '?')}: {status}")
                if ar.get("detail"):
                    lines.append(f"    detail: {ar['detail']}")
        return "\n".join(lines) + "\n"


def compute_score(results: List[CheckpointResult]) -> float:
    """Compute weighted total from checkpoint results. Weights should sum to 1.0."""
    if not results:
        return 0.0
    total_weight = sum(r.weight for r in results)
    if total_weight == 0.0:
        return 0.0
    raw = sum(r.score * r.weight for r in results)
    return raw / total_weight


def write_reward(result: VerificationResult, output_path: str | Path = "reward.txt") -> Path:
    """Write reward.txt with per-checkpoint and total scores."""
    output_path = Path(output_path)
    output_path.write_text(result.summary())
    return output_path
