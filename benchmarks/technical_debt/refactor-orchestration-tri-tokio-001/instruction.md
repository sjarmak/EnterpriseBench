# Refactor Orchestration: Async HTTP Handler Chain (tokio/hyper/axum)

## Context

The Rust async HTTP ecosystem has a strict dependency chain:

tokio (async runtime) -> hyper (HTTP implementation) -> axum (web framework)

A refactoring of tokio's runtime builder API to support configurable task
schedulers creates a cascade of required changes through hyper and axum. The
change affects how hyper spawns connection handlers and how axum bootstraps
its HTTP server.

## Task

Produce a topologically sorted execution plan for propagating the tokio
runtime builder refactoring through the HTTP stack.

## Repos in Workspace

- `/workspace/tokio/` -- tokio 1.29.1 (upstream runtime)
- `/workspace/hyper/` -- hyper 1.0.0-rc.4 (intermediary HTTP library)
- `/workspace/axum/` -- axum 0.6.19 (consumer web framework)

## Expected Output

Write `/workspace/REFACTOR_PLAN.md` containing:

1. A numbered list of repos in the order they should be updated
2. Dependency graph (who depends on whom)
3. Parallelization annotations
4. Breaking vs. compatible change annotations per step
5. Risk assessment for each change
