        # dep-graph-dual-spring-hibernate-001

        **Suite:** dependency_management | **Type:** dependency_graph | **Difficulty:** hard
        **Repos:** hibernate-orm + spring-boot

        ## Context

        Hibernate 6 restructured the SessionFactory and removed several
deprecated configuration properties. Spring Data JPA relies on
Hibernate as its default JPA provider.

Your task:
1. Find where Hibernate 6 changed SessionFactory configuration API
2. Find where Spring Data JPA configures the Hibernate SessionFactory
3. Map the dependency chain from Spring Boot auto-config to Hibernate
4. Document deprecated configuration properties and their replacements

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
