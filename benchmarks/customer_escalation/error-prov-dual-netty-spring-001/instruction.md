        # error-prov-dual-netty-spring-001

        **Suite:** customer_escalation | **Type:** error_provenance | **Difficulty:** expert
        **Repos:** netty + spring-framework

        ## Context

        A Spring WebFlux application is experiencing intermittent connection
reset errors. The errors originate in Netty's channel pipeline but
surface as generic 500 errors in Spring WebFlux.

Your task:
1. Find how Netty handles channel pipeline exceptions
2. Find how Spring WebFlux wraps Netty's reactor-netty in its server
3. Trace an exception from Netty's channel handler through reactor-netty
   into Spring WebFlux's error handling
4. Identify where error context is lost in the translation

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
