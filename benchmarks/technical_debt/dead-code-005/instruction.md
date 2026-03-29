# Dead Code Necropsy: Angular ViewEngine Dead Code in Language Service

## Context

Angular transitioned from ViewEngine to Ivy as its compilation and rendering pipeline. The language service package (`packages/language-service/`) was originally built for ViewEngine and then an Ivy implementation was added in a separate `ivy/` subdirectory. Now that Ivy is the sole compiler, the ViewEngine-specific code in the language service is dead.

Your task is to identify all the dead ViewEngine code that can be safely removed.

## What to Look For

1. **Entire dead files** — ViewEngine-specific modules that have zero importers when Ivy is active
2. **Dead expression analysis** — ViewEngine template expression diagnostics and type checking
3. **Dead adapters** — ViewEngine language service adapters that are no longer used
4. **Dead HTML analysis** — ViewEngine-specific HTML info and hover providers
5. **Dead diagnostic messages** — diagnostic message definitions only used by ViewEngine code
6. **Duplicated ivy/ files** — files in `ivy/` that were copy-adapted from `src/` and should be merged

## Output

Write your findings to `/workspace/angular/dead_code_report.json` as a JSON array where each entry has:
- `file`: relative path from repo root
- `symbol`: function/class name (use `"default"` for entire file being dead)
- `kind`: one of `function`, `class`, `method`, `file`, `export`
- `confidence`: `high`, `medium`, or `low`
- `evidence`: brief explanation of why this code is dead

## Scoring

- **Precision matters most**: incorrectly flagging live code as dead is heavily penalized
- Must identify at least 8 dead files
- Evidence should reference ViewEngine vs Ivy architecture
