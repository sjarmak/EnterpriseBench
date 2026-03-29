# GCC Optimization Pass Registration and Execution Chain

## Your Task

A team member is onboarding to the GCC compiler internals and needs to understand how optimization passes are structured and executed. Trace the optimization pass pipeline in `gcc-mirror/gcc`:

1. Where is the master list that defines the ordering and registration of all optimization passes?
2. Which source file implements the pass manager that orchestrates pass execution?
3. Where is the base class for optimization passes and the pass manager interface defined?
4. Find an example of a concrete GIMPLE optimization pass — specifically one that performs dead code elimination on the tree-SSA representation.
5. Where are the pass registration macros and tree-SSA pass declarations defined?

Report the repo, file path, and key struct/function name for each file you identify.

## Context

You are working on a codebase task involving repos from the crossrepo domain. The GCC source tree is large; focus your investigation on the `gcc/` subdirectory where the compiler core lives.

## Available Resources

## Output Format

Use the published task contract:

- `TASK_WORKDIR=/workspace`
- `TASK_REPO_ROOT=/workspace`
- `TASK_OUTPUT=/workspace/answer.json`

Create a file at `TASK_OUTPUT` (`/workspace/answer.json`) with your findings in the following structure:

```json
{
  "files": [{ "repo": "repo-name", "path": "relative/path/to/file.go" }],
  "symbols": [
    {
      "repo": "repo-name",
      "path": "relative/path/to/file.go",
      "symbol": "SymbolName"
    }
  ],
  "chain": [
    {
      "repo": "repo-name",
      "path": "relative/path/to/file.go",
      "symbol": "FunctionName"
    }
  ],
  "text": "Narrative explanation of your findings, citing repos and file paths."
}
```

Include only the fields relevant to this task. Your answer is evaluated against a closed-world oracle — completeness matters.

## Evaluation

Your answer will be scored on:

- **File recall and precision**: Did you find all relevant files?
