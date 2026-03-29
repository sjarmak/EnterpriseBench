# Task: Dead Code Necropsy -- Click Legacy Exports

## Background
Click has evolved over many major versions. Some exports in `__init__.py` and helper functions in utility modules are no longer used internally or by the documented public API. Your job is to identify obviously dead exports and functions.

## Objective
Analyze the Click codebase and identify dead code. Specifically:
1. Exports in `__init__.py` that are not imported by any internal module
2. Helper functions in `utils.py` that have zero internal callers
3. Any compatibility shims for Python 2 that are no longer needed

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

The repository is available at `/workspace/click/`.
