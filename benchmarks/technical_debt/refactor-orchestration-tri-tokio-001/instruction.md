# Refactor Orchestration: Async HTTP Stack (tokio/hyper/axum)

## Context

tokio is refactoring its runtime builder API to support configurable task
schedulers: `Runtime::new()` is gaining a required scheduler configuration
parameter. This is a breaking change for any crate that builds a tokio runtime
or spawns onto one.

We vendor three repos and need a rollout plan across them. Do not assume how
they relate to each other. Derive every dependency edge from the manifests as
they are checked out in this workspace, and cite the version requirement that
establishes each one.

## Repos in Workspace

- `/workspace/tokio/`
- `/workspace/hyper/`
- `/workspace/axum/`

## Task

Produce a topologically sorted execution plan for propagating the tokio runtime
builder refactoring across these repos.

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. A numbered list of repos in the order they should be updated
2. Dependency graph: which repo depends on which, and for each edge the manifest
   and the version requirement that establishes it. If a dependency you expected
   is not present at these revisions, say so and show what the manifest actually
   requires instead.
3. Parallelization annotations: which repos can be updated at the same time, and why
4. Breaking vs. compatible change annotations per step
5. Risk assessment for each change
