# Refactor Orchestration: JS Compilation Pipeline (Babel/webpack/Next.js)

## Context

The JavaScript compilation pipeline has a strict dependency chain:

babel (parser/compiler) -> webpack (bundler) -> next.js (framework)

Babel is refactoring its parser to support a new DecoratorMetadata AST node
for stage 3 decorators. This change cascades through webpack (which uses Babel
via babel-loader for JS compilation and needs to understand decorator side
effects for tree-shaking) and Next.js (which configures both Babel and SWC
for its build pipeline).

## Task

Produce a topologically sorted execution plan for propagating the Babel parser
AST change through the JS build pipeline.

## Repos in Workspace

- `/workspace/babel/` -- Babel v7.22.9 (upstream parser/compiler)
- `/workspace/webpack/` -- webpack v5.88.2 (intermediary bundler)
- `/workspace/nextjs/` -- Next.js v13.4.12 (consumer framework)

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. A numbered list of repos in the order they should be updated
2. Dependency graph (who depends on whom)
3. Parallelization annotations
4. Breaking vs. compatible change annotations per step
5. Risk assessment for each change
