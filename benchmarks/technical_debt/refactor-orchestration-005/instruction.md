# Refactor Orchestration: Babel 8 Plugin Removal Cascade

## Context

Babel 8 removes several deprecated plugin-transform packages. These removals
must be orchestrated carefully due to internal dependency relationships within
the monorepo:

- `@babel/plugin-transform-react-compat` (PR #17620)
- `@babel/plugin-transform-react-source` (PR #17620)
- `@babel/plugin-transform-react-self` (PR #17620)
- `@babel/plugin-transform-property-mutators` (PR #17882)

The affected packages form a diamond dependency through `@babel/preset-env`
and `@babel/preset-react`.

## Task

Given the Babel monorepo at its pre-removal state, produce a topologically
sorted execution plan for the plugin removals.

## Repos in Workspace

- `/workspace/babel/` — babel monorepo at v7.25.0

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. A numbered list of packages in the order they should be updated
2. Internal dependency graph
3. Parallelization annotations (which removals are independent)
4. Breaking change impact per package

## Reference

- babel/babel PR #17620: Remove plugin-transform-react-{compat,source,self}
- babel/babel PR #17882: Remove plugin-transform-property-mutators
- babel/babel PR #17670: Remove isPluginRequired from preset-env
