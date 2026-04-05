"""Core LLM judge engine for EnterpriseBench checkpoint verification.

Evaluates agent outputs against curated ground truth per checkpoint.
Uses a different model family (or Haiku for cost) to avoid self-evaluation
bias when the agent is Claude.
"""

from __future__ import annotations

from typing import Optional

from .backends import JudgeBackendError, create_backend
from .models import CheckpointJudgeInput, CheckpointJudgeResult, normalize_score
from .prompts import CHECKPOINT_EVAL_PROMPT, CHECKPOINT_EVAL_SYSTEM


class LLMJudge:
    """LLM-based judge for per-checkpoint verification.

    Args:
        model: Model identifier (e.g. 'claude-haiku-4-5-20251001', 'cc:haiku').
        temperature: Sampling temperature (0.0 = deterministic).
        pass_threshold: Minimum score for a checkpoint to pass.
    """

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        temperature: float = 0.0,
        pass_threshold: float = 0.5,
    ):
        self.model = model
        self.temperature = temperature
        self.pass_threshold = pass_threshold
        self._backend = create_backend(model=model, temperature=temperature)

    def evaluate_checkpoint(
        self,
        judge_input: CheckpointJudgeInput,
        task_description: str = "",
        checkpoint_description: str = "",
    ) -> CheckpointJudgeResult:
        """Score a single checkpoint against curated ground truth.

        Args:
            judge_input: Checkpoint-level input with agent output and expected solution.
            task_description: Human-readable task description for context.
            checkpoint_description: What this checkpoint tests.

        Returns:
            CheckpointJudgeResult with score, passed, reasoning, evidence.
        """
        criteria_text = (
            "\n".join(f"- {c}" for c in judge_input.evaluation_criteria)
            if judge_input.evaluation_criteria
            else "(none provided)"
        )

        user_prompt = CHECKPOINT_EVAL_PROMPT.format(
            task_description=task_description,
            checkpoint_name=judge_input.checkpoint_name,
            checkpoint_description=checkpoint_description,
            expected_solution=judge_input.expected_solution,
            evaluation_criteria=criteria_text,
            agent_output=judge_input.agent_output[:12000],  # truncate to fit context
        )

        try:
            response = self._backend.call(CHECKPOINT_EVAL_SYSTEM, user_prompt)
        except JudgeBackendError as exc:
            return CheckpointJudgeResult(
                checkpoint_name=judge_input.checkpoint_name,
                score=0.0,
                passed=False,
                reasoning=f"Judge backend error: {exc}",
                confidence="low",
                model=self.model,
            )

        score = normalize_score(response.get("score", 0.0))
        passed = score >= self.pass_threshold

        return CheckpointJudgeResult(
            checkpoint_name=judge_input.checkpoint_name,
            score=score,
            passed=passed,
            reasoning=response.get("reasoning", ""),
            evidence=response.get("evidence", ""),
            confidence=response.get("confidence", "medium"),
            model=self.model,
            raw_response=response,
        )
