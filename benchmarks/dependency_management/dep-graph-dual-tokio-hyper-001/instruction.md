        # dep-graph-dual-tokio-hyper-001

        **Suite:** dependency_management | **Type:** dependency_graph | **Difficulty:** hard
        **Repos:** tokio + hyper

        ## Context

        The tokio async runtime released v1.0, which reworked the Cargo
feature flags that gate the runtime and changed how a runtime is
constructed. The hyper HTTP library depends on tokio for its server
implementation, and its dependency declarations and runtime usage predate
this release.

Your task:
1. Identify where hyper depends on tokio runtime features in Cargo.toml
2. Find all files in hyper that create or reference tokio runtimes
3. Trace the dependency chain from hyper's server module to tokio's
   runtime builder API
4. Document which tokio API changes affect hyper and how

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
