        # error-prov-dual-tokio-tower-001

        **Suite:** customer_escalation | **Type:** error_provenance | **Difficulty:** expert
        **Repos:** tokio + tower

        ## Context

        A production gRPC service is panicking inside a tokio::spawn'd task
within a tower service layer. The panic message surfaces as a generic
"task panicked" error, losing the original context.

Your task:
1. Find how tokio handles panics in spawned tasks (JoinError, panic hook)
2. Find how tower Service layers propagate errors from inner services
3. Trace the error path from a tokio task panic through tower layers
4. Identify where error context is lost and document a fix

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
