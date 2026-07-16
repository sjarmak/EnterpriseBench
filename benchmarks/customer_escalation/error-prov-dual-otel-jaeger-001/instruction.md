        # error-prov-dual-otel-jaeger-001

        **Suite:** customer_escalation | **Type:** error_provenance | **Difficulty:** hard
        **Repos:** otel-go + jaeger

        ## Context

        An application using OpenTelemetry SDK to export traces to Jaeger is
silently dropping spans. The export errors are being swallowed somewhere
in the pipeline between OTel SDK and Jaeger collector.

Your task:
1. Find how OTel SDK handles span export errors in the batch processor
2. Find how Jaeger exporter reports errors back to OTel SDK
3. Trace the error path from Jaeger collector rejection to OTel SDK
4. Identify where errors are silently swallowed

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
