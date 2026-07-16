        # error-prov-dual-urllib3-requests-001

        **Suite:** customer_escalation | **Type:** error_provenance | **Difficulty:** hard
        **Repos:** urllib3 + requests

        ## Context

        After upgrading urllib3 to 2.0, requests is raising different SSL
exceptions than expected. The error messages have changed and some
error types were restructured.

Your task:
1. Find how urllib3 2.0 restructured its exception hierarchy for SSL errors
2. Find where requests catches and wraps urllib3 exceptions
3. Trace an SSL connection error from urllib3 through requests' adapter layer
4. Identify where error context is transformed or lost

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
