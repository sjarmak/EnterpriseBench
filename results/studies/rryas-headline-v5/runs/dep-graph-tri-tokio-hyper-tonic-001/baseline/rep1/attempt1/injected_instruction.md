        # dep-graph-tri-tokio-hyper-tonic-001

        **Suite:** dependency_management | **Type:** dependency_graph | **Difficulty:** expert
        **Repos:** tokio + hyper + tonic

        ## Context

        The Rust gRPC stack uses tonic (gRPC) → hyper (HTTP/2) → tokio (async
runtime). A tokio version bump can cascade through hyper into tonic.

Your task:
1. Map the full dependency chain: tonic → hyper → tokio with exact
   version constraints from each Cargo.toml
2. Identify which tokio APIs hyper uses that tonic depends on transitively
3. Find any version pinning conflicts across the three repos
4. Document the upgrade coordination strategy

Write your analysis to /workspace/analysis/IMPACT_REPORT.md

        ## Expected Output

        Write your analysis to `/workspace/analysis/IMPACT_REPORT.md`.

        Your report should include:
        - File paths from each repository that are relevant
        - Specific code symbols, functions, or types involved
        - The nature of each change (removal, rename, signature change, behavioral)
        - Migration recommendations

        ## Hints

        - All repos are cloned under `/workspace/`
        - Focus on import/dependency declarations first, then trace into implementation
        - Check version constraints in dependency manifests (Cargo.toml, go.mod, pom.xml, requirements.txt)


---

## Output Requirements

The grader reads only `/workspace/analysis/IMPACT_REPORT.md`. This exact path supersedes any other output path mentioned earlier.

Create its parent directory first: `mkdir -p /workspace/analysis`
Write the complete report as Markdown, following the task's requested structure.

Do not create secondary or legacy deliverables. After validating the graded artifact, stop immediately instead of starting another reasoning step.

All cited source-file paths MUST be absolute and anchored at `/workspace/<repo>/...` (the repo roots are the directories under `/workspace`). Repo-relative source paths will not match the oracle and score 0.

Your answer is evaluated against a closed-world oracle — completeness matters.
