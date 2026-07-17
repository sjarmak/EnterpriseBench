# Refactor Orchestration: JS Compilation Pipeline (Babel/webpack/Next.js)

## Context

Babel is refactoring its parser to emit a new `DecoratorMetadata` AST node for
stage 3 decorators. Anything that parses JavaScript with Babel, or walks a Babel
AST, may have to handle the new node type.

We vendor three repos and need a rollout plan across them. Do not assume how they
relate to each other, or which of them a Babel parser change actually reaches.
Work out from the manifests which repos consume Babel, and cite the dependency
entry that establishes each edge.

## Repos in Workspace

- `/workspace/babel/`
- `/workspace/webpack/`
- `/workspace/nextjs/`

## Task

Produce a topologically sorted execution plan for propagating the Babel parser
AST change across the repos it actually reaches.

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. A numbered list of repos in the order they should be updated
2. Dependency graph: which repo depends on which, and the manifest entry that
   establishes each edge. If a repo you expected to be affected turns out not to
   be, say so and show what its manifest actually declares.
3. Parallelization annotations: which steps can proceed at the same time, and why
4. Breaking vs. compatible change annotations per step
5. Risk assessment for each change
