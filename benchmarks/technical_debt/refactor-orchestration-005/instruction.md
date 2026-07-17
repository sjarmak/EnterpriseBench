# Refactor Orchestration: Babel 8 Plugin Removal Cascade

## Context

Babel 8 removes four deprecated plugin packages from the monorepo:

- `@babel/plugin-transform-react-jsx-compat` (babel/babel PR #17620)
- `@babel/plugin-transform-react-jsx-self` (PR #17620)
- `@babel/plugin-transform-react-jsx-source` (PR #17620)
- `@babel/plugin-transform-property-mutators` (PR #17882)

Our Babel 8 tracking notes claim the removals cascade through `@babel/preset-env`
and `@babel/preset-react`, which are said to re-export or depend on the removed
plugins, and that the affected packages form a diamond through the two presets.
Do not take that as given. Work out from the manifests under `packages/` which
workspace packages actually reference each removal target, and cite the entry
that establishes each edge. If a package the notes call affected turns out not to
be, say so and show what its manifest actually declares.

## Repos in Workspace

- `/workspace/babel/` — babel monorepo at v7.25.0

## Task

Produce an ordered execution plan for the four removals. Order the steps so the
workspace still builds after every step: a package cannot be deleted while
another workspace package still references it.

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. Under an `## Order` heading, a flat numbered list — `1. <package>` — naming
   one package per line, in the order the steps should land
2. Internal dependency graph: which package references which removal target, and
   the manifest entry behind each edge
3. Parallelization annotations: which steps can proceed at the same time, and why
4. Breaking change impact per package

## Reference

- babel/babel PR #17620: Remove `plugin-transform-react-{compat,source,self}`
- babel/babel PR #17882: Remove `@babel/plugin-transform-property-mutators`
