"""Prompt templates for EB checkpoint-level LLM judge.

Adapted from CSB's dimension-based scoring to EB's checkpoint model.
The judge evaluates whether the agent's output demonstrates actual
code navigation (found specific files, functions, variables) vs
domain knowledge (generic terms any developer would know).
"""

CHECKPOINT_EVAL_PROMPT = """\
You are an expert code evaluator for a benchmark that measures whether an AI \
agent can navigate and understand large codebases. Your task is to score the \
agent's output for a SINGLE checkpoint against the curated expected solution.

CRITICAL: The agent had access to specific source code repositories. A good \
answer must reference CODE-SPECIFIC details (exact file paths found in the \
repo, function/variable names unique to the codebase, specific line-level \
behavior). Generic domain knowledge that any experienced developer could \
produce WITHOUT reading the code should score LOW.

## Task Description
{task_description}

## Checkpoint Being Evaluated
Name: {checkpoint_name}
Description: {checkpoint_description}

## Expected Solution (curated ground truth)
{expected_solution}

## Evaluation Criteria
{evaluation_criteria}

## Agent Output
{agent_output}

## Scoring Instructions

Score on a 3-point scale:
- 1.0: Agent output matches expected solution with CODE-SPECIFIC details \
(file paths, function names, variable names, code structure) that could \
only come from reading the actual source code.
- 0.5: Agent output is partially correct but relies on generic domain \
knowledge or misses key code-specific details from the expected solution.
- 0.0: Agent output is incorrect, missing, or contains only generic \
domain knowledge without evidence of actual code navigation.

Respond with ONLY valid JSON:
{{
  "score": <float 0.0|0.5|1.0>,
  "passed": <bool>,
  "reasoning": "<1-2 sentences explaining the score>",
  "evidence": "<specific quotes from agent output that demonstrate code navigation OR generic domain knowledge>",
  "confidence": "<high|medium|low>"
}}
"""

CHECKPOINT_EVAL_SYSTEM = (
    "You are a precise code benchmark evaluator. "
    "You distinguish between answers derived from actual code navigation "
    "and answers derived from generic domain knowledge. "
    "Always respond with valid JSON only."
)
