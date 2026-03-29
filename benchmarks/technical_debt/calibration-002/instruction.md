# Task: Dead Code Necropsy -- Flask Legacy Exports

## Background
Flask has evolved significantly since its early versions. Some internal helpers, deprecated compatibility shims, and re-exports may no longer be used. Your job is to identify obviously dead or unused code.

## Objective
Analyze the Flask codebase and identify dead code. Specifically:
1. Functions in `helpers.py` that have zero internal callers
2. Exports in `__init__.py` that are not used internally
3. Deprecated functions or compatibility wrappers

## Output Format
Write your findings to `/workspace/agent_output/answer.json`:
```json
{
  "dead_code": [
    {
      "file": "path/to/file.py",
      "symbol": "function_or_export_name",
      "kind": "function|export|class",
      "confidence": "high|medium",
      "evidence": "explanation"
    }
  ]
}
```

## Success Criteria
- Precision >= 0.8 (avoid flagging live code)
- Each item must include evidence of zero callers

The repository is available at `/workspace/flask/`.
