        # api-contract-dual-jackson-spring-001

        **Suite:** dependency_management | **Type:** api_contract | **Difficulty:** hard
        **Repos:** jackson-databind + spring-boot

        ## Context

        A Spring Boot service team bumped their Jackson dependency and, with no
code changes of their own, started seeing two things happen in production:

- An endpoint that used to reject requests containing unrecognized JSON
  fields (returning a 400) now accepts them silently.
- A date field in a JSON response now renders in a different textual
  format than clients expect, breaking a downstream consumer's parser.

Spring Boot auto-configures Jackson's ObjectMapper as its default JSON
serializer, so the team suspects the root cause sits at the seam between
the two projects rather than in their own application code.

Your task:
1. Find where Jackson's ObjectMapper defines its default settings and
   feature flags, and identify what changed between the pinned versions.
2. Find where Spring Boot auto-configures the Jackson ObjectMapper for its
   applications.
3. Explain how the Jackson-level default change propagates into observable
   behavior at Spring REST endpoints.
4. Document the migration path for Spring Boot applications that need to
   restore the old semantics (or adapt to the new ones).

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
