# Dead Code Necropsy: TypeScript Compiler Dead Exports

## Context

The TypeScript compiler is a large codebase (~900K lines of code) that has accumulated unused exports and dead utility functions over years of development. Functions that were once used by other modules have become orphaned as the codebase evolved.

Your task is to systematically identify exported functions, types, and utilities that are no longer imported or used anywhere in the codebase.

## What to Look For

1. **Dead exports** — functions exported from a module but never imported elsewhere
2. **Dead utility functions** — helpers in `core.ts`, `utilities.ts` that no module calls
3. **Dead type definitions** — interfaces and types that are never referenced
4. **Dead factory helpers** — emit helpers and factory utilities no longer used by any transform

## Output

Write your findings to `/workspace/TypeScript/dead_code_report.json` as a JSON array where each entry has:
- `file`: relative path from repo root
- `symbol`: function/type/export name
- `kind`: one of `function`, `class`, `method`, `file`, `export`, `type`
- `confidence`: `high`, `medium`, or `low`
- `evidence`: brief explanation of why this code is dead

## Scoring

- **Precision matters most**: incorrectly flagging live code as dead is heavily penalized
- Must find dead exports in at least 5 different files
- This is a large codebase — exhaustive reference search is required
