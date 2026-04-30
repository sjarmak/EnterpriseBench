"""
eb_verify — EnterpriseBench centralized verification library.

Single source of truth for all task verification. No per-task copies.
"""

__version__ = "0.2.0"

from eb_verify.task_parser import TaskDefinition, parse_task
from eb_verify.runner import CheckpointRunner
from eb_verify.scoring import (
    ScoreDiagnostics,
    ScoreResult,
    compute_score,
    write_reward,
    write_score_result,
)

__all__ = [
    "TaskDefinition",
    "parse_task",
    "CheckpointRunner",
    "compute_score",
    "write_reward",
    "write_score_result",
    "ScoreResult",
    "ScoreDiagnostics",
]
