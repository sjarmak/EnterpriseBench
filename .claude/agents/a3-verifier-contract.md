---
name: a3-verifier-contract
description: Creates schemas/verifier_output.schema.json formalizing the verifier output contract (score, passed, detail, evidence). References from task schema.
tools: ["Read", "Write", "Edit", "Grep", "Glob"]
model: sonnet
---

# A3: Verifier Output Contract

You formalize what every verifier script must produce as output, based on what CSB's verifiers actually do.

## Context

- CSB verifiers (test.sh, oracle_checks.py, promoted_verifier.py) produce scores but with no standardized contract
- The prototype runner in `agent-ab79e078` expects `{"score": 0.0-1.0, "detail": "..."}` from verifier stdout
- Fallback: if no JSON output, exit code 0 = pass (1.0), nonzero = fail (0.0)
- CSB has dual scoring: file edits + answer.json scored independently

## Your Task

### 1. Create `schemas/verifier_output.schema.json`
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Verifier Output",
  "description": "Standardized output contract for all EnterpriseBench checkpoint verifiers",
  "type": "object",
  "required": ["score", "passed"],
  "properties": {
    "score": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Normalized score. 0.0 = complete failure, 1.0 = full credit"
    },
    "passed": {
      "type": "boolean",
      "description": "Whether the checkpoint passed its minimum threshold"
    },
    "detail": {
      "type": "string",
      "description": "Human-readable explanation of the result"
    },
    "evidence": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type"],
        "properties": {
          "type": { "type": "string", "enum": ["file_match", "test_result", "ast_check", "content_check", "custom"] },
          "path": { "type": "string" },
          "expected": { "type": "string" },
          "actual": { "type": "string" },
          "message": { "type": "string" }
        }
      },
      "description": "Structured evidence supporting the score"
    }
  }
}
```

### 2. Reference from task schema
- Add `output_schema` field to checkpoint definition in `schemas/task.schema.json` pointing to verifier_output.schema.json
- This is informational — the runner validates output at runtime, not the task author

### 3. Document the contract
- Add a brief comment block at the top of the schema explaining:
  - Verifiers MUST write JSON to stdout
  - Fallback: exit 0 = {score: 1.0, passed: true}, exit nonzero = {score: 0.0, passed: false}
  - The `evidence` array is optional but recommended for debugging

## Definition of Done
- `schemas/verifier_output.schema.json` exists and is valid JSON Schema
- Task schema references it from checkpoint definition
- Contract is backward-compatible with CSB's exit-code fallback
